"""
domains/mutual_funds/tax_lots.py

Lot-Level Tax Engine
====================
FIFO acquisition-lot reconstruction per fund, feeding STCG/LTCG classification,
ELSS lock-in detection, and tax-aware rebalancing sell-candidate selection.

This closes two gaps in the rebalancer: it previously ignored capital-gains tax
and could suggest selling ELSS units still inside their 3-year lock-in.

Indicative planning estimates only — not tax-filing advice. Tax treatment for
Hybrid schemes is approximated as equity-taxed (accurate only for equity-oriented
i.e. >65% equity hybrid funds; debt-oriented/Conservative Hybrid funds are
actually taxed under the debt regime below).

All rates, exemptions, and holding-period thresholds are sourced from the Tax
Expert domain's tax_rules.json (via shared.config.TAX_RATES) — the single rule
file both domains read, so a Budget change only needs editing there.
"""

import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional

from shared.config import TAX_RATES, get_standard_category

ELSS_LOCKIN_DAYS = TAX_RATES["ELSS_LOCKIN_DAYS"]
EQUITY_LTCG_DAYS = TAX_RATES["EQUITY_LTCG_DAYS"]
DEBT_LTCG_DAYS = TAX_RATES["DEBT_LTCG_DAYS"]          # Pre-Apr-2023 debt units: LTCG applies after this many days
DEBT_REGIME_CUTOFF = datetime.strptime(TAX_RATES["DEBT_REGIME_CUTOFF"], "%Y-%m-%d").date()  # Finance Act 2023, Section 50AA

# No per-scheme exit-load data is available anywhere in this app (not in the CAS PDF, not from
# any market-data provider). This is the near-universal SEBI-era convention for open-ended
# equity/hybrid schemes — 1% exit load if redeemed within 1 year of purchase, nil after — used
# ONLY as a disclosed assumption to flag likely exit-load exposure, never presented as an exact
# figure. Deliberately NOT applied to debt/liquid funds, whose exit-load terms vary far more
# (nil to graded-over-days) and would be too unreliable to assume.
EXIT_LOAD_EQUITY_ASSUMED_RATE = 0.01
EXIT_LOAD_ASSUMED_WINDOW_DAYS = 365


def _to_date(d) -> date:
    if isinstance(d, (datetime, pd.Timestamp)):
        return d.date()
    return d


def compute_fund_lots(df_t: pd.DataFrame, fund_name: str) -> List[Dict]:
    """
    FIFO-reconstruct the acquisition lots still held for one fund from its
    transaction ledger. Mirrors the cost-basis logic in parser._estimate_invested
    but retains per-lot acquisition dates, required for STCG/LTCG classification.
    """
    if df_t is None or df_t.empty:
        return []
    ft = df_t[df_t["Fund"] == fund_name].copy()
    if ft.empty:
        return []
    if not pd.api.types.is_datetime64_any_dtype(ft["Date"]):
        # Sessions restored from disk come back from SQLite as ISO (year-first) strings —
        # dayfirst=True would misparse them, so only apply it to raw CAS dd-mm-yyyy strings,
        # which never reach this function in the normal (in-memory) flow.
        ft["Date"] = pd.to_datetime(ft["Date"])
    ft = ft.sort_values("Date")

    lots: List[Dict] = []  # {"units": float, "cost_per_unit": float, "date": date}

    for _, row in ft.iterrows():
        t_type = str(row.get("Type", "")).upper()
        units = float(row.get("Units", 0) or 0)
        amt = abs(float(row.get("Amount", 0) or 0))
        nav = float(row.get("NAV", 0) or 0)
        d = _to_date(row["Date"])

        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        if any(x in t_type for x in ("REINVEST", "BONUS", "IDCW_REINVEST", "GROWTH_OPTION")):
            if units > 0:
                lots.append({"units": units, "cost_per_unit": nav if nav > 0 else 0.0, "date": d})
            continue

        is_buy = units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN"))
        is_sell = units < 0 or any(x in t_type for x in ("SELL", "REDEMPTION", "SWP-OUT", "STP-OUT", "SWITCH-OUT"))

        if is_buy and not is_sell:
            buy_units = units if units > 0 else (amt / nav if nav > 0 else 0.0)
            if buy_units > 0:
                cost_per_unit = (amt / buy_units) if buy_units > 0 else nav
                lots.append({"units": buy_units, "cost_per_unit": cost_per_unit, "date": d})
        elif is_sell:
            sell_units = abs(units) if units < 0 else (amt / nav if nav > 0 else 0.0)
            while sell_units > 1e-6 and lots:
                oldest = lots[0]
                if oldest["units"] <= sell_units + 1e-9:
                    sell_units -= oldest["units"]
                    lots.pop(0)
                else:
                    oldest["units"] -= sell_units
                    sell_units = 0.0

    return [l for l in lots if l["units"] > 1e-6]


def tax_treatment(category: str) -> str:
    """Returns 'debt' or 'equity' — the two broad capital-gains regimes."""
    return "debt" if get_standard_category(category) == "Debt" else "equity"


def holding_tax_breakdown(lots: List[Dict], current_nav: float, category: str,
                           today: Optional[date] = None) -> Dict:
    """
    Splits a fund's held lots into STCG / LTCG buckets under the applicable
    regime, and flags ELSS lock-in (units locked for 3 years from purchase).
    """
    today = today or datetime.now().date()
    treatment = tax_treatment(category)
    is_elss = "ELSS" in str(category).upper()

    stcg_gain = ltcg_gain = 0.0
    stcg_value = ltcg_value = 0.0
    locked_units = locked_value = 0.0
    slab_taxed_value = 0.0
    min_holding_days = None
    oldest_lot_date = None

    for lot in lots:
        units = lot["units"]
        if units <= 0 or current_nav <= 0:
            continue
        cost = lot["cost_per_unit"] * units
        value = units * current_nav
        gain = value - cost
        days_held = (today - lot["date"]).days
        min_holding_days = days_held if min_holding_days is None else min(min_holding_days, days_held)
        oldest_lot_date = lot["date"] if oldest_lot_date is None else min(oldest_lot_date, lot["date"])

        if is_elss and days_held < ELSS_LOCKIN_DAYS:
            locked_units += units
            locked_value += value

        if treatment == "debt":
            if lot["date"] >= DEBT_REGIME_CUTOFF:
                # Section 50AA — always slab-taxed, no LTCG concept regardless of holding period
                slab_taxed_value += value
                stcg_gain += gain
                stcg_value += value
            elif days_held >= DEBT_LTCG_DAYS:
                ltcg_gain += gain
                ltcg_value += value
            else:
                stcg_gain += gain
                stcg_value += value
        else:
            if days_held >= EQUITY_LTCG_DAYS:
                ltcg_gain += gain
                ltcg_value += value
            else:
                stcg_gain += gain
                stcg_value += value

    return {
        "treatment": treatment,
        "is_elss": is_elss,
        "stcg_gain": round(stcg_gain, 2),
        "ltcg_gain": round(ltcg_gain, 2),
        "stcg_value": round(stcg_value, 2),
        "ltcg_value": round(ltcg_value, 2),
        "locked_units": round(locked_units, 4),
        "locked_value": round(locked_value, 2),
        "slab_taxed_value": round(slab_taxed_value, 2),
        "holding_days_min": min_holding_days or 0,
        "oldest_lot_date": oldest_lot_date.isoformat() if oldest_lot_date else None,
    }


def portfolio_tax_summary(df_h: pd.DataFrame, df_t: pd.DataFrame) -> Dict:
    """
    Portfolio-wide LTCG-harvest opportunity scan (equity/ELSS) plus a
    slab-tax exposure summary for debt/liquid holdings.
    """
    if df_h is None or df_h.empty:
        return {"harvest": {}, "debt_summary": {}, "per_fund": [],
                "disclaimer": "Indicative tax planning estimate only — not tax advice."}

    from domains.mutual_funds.finance import compute_ltcg_harvest

    per_fund = []
    for _, row in df_h.iterrows():
        fund = row.get("Fund")
        category = row.get("Category", "Equity")
        current_nav = float(row.get("NAV", 0) or 0)
        lots = compute_fund_lots(df_t, fund)
        bd = holding_tax_breakdown(lots, current_nav, category)
        bd["fund"] = fund
        bd["market_value"] = float(row.get("Market Value", 0) or 0)
        per_fund.append(bd)

    harvest_inputs = []
    for f in per_fund:
        if f["treatment"] != "equity":
            continue
        total_val = f["ltcg_value"] + f["stcg_value"]
        unlocked_frac = 1.0
        if f["is_elss"] and total_val > 0:
            unlocked_frac = max(0.0, 1 - (f["locked_value"] / total_val))
        unlocked_ltcg_gain = f["ltcg_gain"] * unlocked_frac
        harvest_inputs.append({
            "fund": f["fund"],
            "gain": unlocked_ltcg_gain,
            "holding_days": 365 if unlocked_ltcg_gain > 0 else 0,
            "stcg": f["stcg_gain"] if f["stcg_gain"] < 0 else 0,
            "ltcg": f["ltcg_gain"] if f["ltcg_gain"] < 0 else 0,
        })

    harvest = compute_ltcg_harvest(
        harvest_inputs,
        ltcg_exemption=TAX_RATES["LTCG_EXEMPTION"],
        ltcg_rate=TAX_RATES["LTCG_EQUITY"],
    )

    debt_stcg_gain = sum(f["stcg_gain"] for f in per_fund if f["treatment"] == "debt")
    debt_ltcg_gain = sum(f["ltcg_gain"] for f in per_fund if f["treatment"] == "debt")
    slab_rate = TAX_RATES["STCG_DEBT"]

    debt_summary = {
        "slab_taxed_gain": round(debt_stcg_gain, 2),
        "estimated_tax_at_slab": round(max(debt_stcg_gain, 0) * slab_rate, 2),
        "ltcg_gain_pre_2023_units": round(debt_ltcg_gain, 2),
        "note": (
            "Debt/liquid fund gains on units bought on/after 1-Apr-2023 are taxed entirely "
            "at your income slab rate (Section 50AA) — there's no LTCG concept for these. "
            f"Estimated here at a {slab_rate * 100:.0f}% proxy slab rate; substitute your actual bracket."
        ),
    }

    elss_locked_value = round(sum(f["locked_value"] for f in per_fund if f["is_elss"]), 2)

    return {
        "harvest": harvest,
        "debt_summary": debt_summary,
        "elss_locked_value": elss_locked_value,
        "per_fund": per_fund,
        "disclaimer": "Indicative tax planning estimate only — not tax/investment advice. Consult a CA before acting.",
    }


def select_sell_candidate(df_h: pd.DataFrame, df_t: pd.DataFrame, category_mask, sell_amount: float) -> Dict:
    """
    Pick the most tax-efficient fund(s) to trim within an overweight category
    for the rebalancer, respecting ELSS lock-in and preferring LTCG-eligible
    (lower-tax) unlocked value over STCG-eligible value.

    Replaces the naive "largest holding in category" heuristic, which could
    suggest selling ELSS units still inside their 3-year lock-in.
    """
    cat_funds = df_h[category_mask]
    if cat_funds.empty or sell_amount <= 0:
        return {}

    candidates = []
    for _, row in cat_funds.iterrows():
        fund = row["Fund"]
        category = row.get("Category", "Equity")
        current_nav = float(row.get("NAV", 0) or 0)
        lots = compute_fund_lots(df_t, fund)
        bd = holding_tax_breakdown(lots, current_nav, category)
        total_val = bd["ltcg_value"] + bd["stcg_value"]
        unlocked_val = max(0.0, total_val - bd["locked_value"])
        if unlocked_val <= 0:
            continue
        ltcg_share = (bd["ltcg_value"] / total_val) if total_val > 0 else 0.0
        candidates.append({"fund": fund, "breakdown": bd, "unlocked_val": unlocked_val, "ltcg_share": ltcg_share})

    total_locked = sum(
        row_bd["breakdown"]["locked_value"]
        for row_bd in candidates
        if row_bd["breakdown"]["is_elss"]
    )
    # Also count funds that were entirely excluded (fully locked, so never made it into `candidates`)
    for _, row in cat_funds.iterrows():
        category = row.get("Category", "Equity")
        if "ELSS" in str(category).upper() and not any(c["fund"] == row["Fund"] for c in candidates):
            lots = compute_fund_lots(df_t, row["Fund"])
            bd = holding_tax_breakdown(lots, float(row.get("NAV", 0) or 0), category)
            total_locked += bd["locked_value"]

    if not candidates:
        return {"note": "All funds in this category are ELSS-locked (3-yr lock-in) — no sellable candidate available.",
                "locked_note": f"₹{total_locked:,.0f} is ELSS-locked and cannot be redeemed yet." if total_locked > 0 else None}

    candidates.sort(key=lambda c: (-c["ltcg_share"], -c["unlocked_val"]))

    remaining = sell_amount
    picks = []
    total_ltcg_gain = total_stcg_gain = 0.0
    assumed_exit_load = 0.0
    treatment = candidates[0]["breakdown"]["treatment"]

    for c in candidates:
        if remaining <= 0:
            break
        take = min(remaining, c["unlocked_val"])
        bd = c["breakdown"]
        tv = bd["ltcg_value"] + bd["stcg_value"]
        ltcg_val_frac = (bd["ltcg_value"] / tv) if tv > 0 else 0.0
        stcg_val_frac = 1 - ltcg_val_frac

        # Redemption value is assumed pro-rata across the LTCG/STCG lot buckets by value share.
        # Only the GAIN embedded in each slice is taxable — not the principal being returned.
        take_ltcg_value = take * ltcg_val_frac
        take_stcg_value = take * stcg_val_frac
        ltcg_gain_rate = (bd["ltcg_gain"] / bd["ltcg_value"]) if bd["ltcg_value"] > 0 else 0.0
        stcg_gain_rate = (bd["stcg_gain"] / bd["stcg_value"]) if bd["stcg_value"] > 0 else 0.0
        total_ltcg_gain += take_ltcg_value * ltcg_gain_rate
        total_stcg_gain += take_stcg_value * stcg_gain_rate

        # The equity STCG bucket (held < 1Y) is exactly the population a standard 1% exit
        # load would apply to — reuse it rather than reclassifying lots a second time.
        if bd["treatment"] == "equity":
            assumed_exit_load += take_stcg_value * EXIT_LOAD_EQUITY_ASSUMED_RATE

        picks.append({"fund": c["fund"], "amount": round(take, 0)})
        remaining -= take

    if treatment == "equity":
        est_tax = max(total_ltcg_gain, 0) * TAX_RATES["LTCG_EQUITY"] + max(total_stcg_gain, 0) * TAX_RATES["STCG_EQUITY"]
    else:
        # Simplification: tax the whole realized debt gain at the slab proxy rate. Exact for
        # post-Apr-2023 units (Section 50AA — always slab-taxed); an approximation for any
        # pre-2023 debt lots pulled in, which technically get 20% LTCG after 36 months.
        est_tax = max(total_ltcg_gain + total_stcg_gain, 0) * TAX_RATES["STCG_DEBT"]

    shortfall = round(remaining, 0)
    return {
        "picks": picks,
        "fund_suggestion": picks[0]["fund"] if picks else None,
        "estimated_tax": round(est_tax, 0),
        "ltcg_pulled": round(total_ltcg_gain, 0),
        "stcg_pulled": round(total_stcg_gain, 0),
        "locked_note": f"₹{total_locked:,.0f} is ELSS-locked (3-yr lock-in) and excluded from this suggestion." if total_locked > 0 else None,
        "estimated_exit_load": round(assumed_exit_load, 0),
        "exit_load_note": (
            f"~₹{assumed_exit_load:,.0f} of this may carry a 1% exit load — assumes the standard "
            "SEBI-era 1-year exit-load window (no per-scheme exit-load data is available; check "
            "your fund's factsheet for the exact terms)."
        ) if assumed_exit_load > 1 else None,
        "shortfall": shortfall if shortfall > 1 else 0,
    }
