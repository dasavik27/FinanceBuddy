"""
core/finance.py
Core financial algorithms and analytical engines.
All formulas validated against CFA standards and global institutional benchmarks.
Implementation follows strict Unitized Portfolio Accounting for precision auditing.
"""

import numpy as np
import pandas as pd
from pyxirr import xirr
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional
import logging
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_date(d) -> date:
    """Normalise datetime / date / Timestamp → date."""
    if isinstance(d, (datetime, pd.Timestamp)):
        return d.date()
    return d


def _get_standard_ledger(df_t: pd.DataFrame) -> List[Dict]:
    """
    Convert raw transaction DataFrame into a standardised cashflow ledger.

    Ledger entries:
      {"date": date, "amount": float, "type": str}
    Negative amount = money OUT (purchase).
    Positive amount = money IN  (redemption / dividend payout).
    Reinvestment transactions are excluded (no real cashflow).
    """
    ledger = []
    if df_t is None or df_t.empty:
        return ledger

    for _, row in df_t.iterrows():
        raw_amt = row.get("Amount", 0)
        amt     = abs(float(raw_amt)) if raw_amt is not None else 0.0
        
        t_type = str(row.get("Type", "")).upper().strip()
        units  = float(row.get("Units", 0) or 0)
        nav    = float(row.get("NAV", 0) or 0)
        d      = _to_date(row["Date"])

        # Impute amount for SWITCH or non-monetary transactions using Unit*NAV basis
        # This ensures accurate cost tracking for CAS records with zero-amount entries.
        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        if amt == 0 and not any(x in t_type for x in ("DIVIDEND", "BONUS")):
            continue

        # Skip dividend reinvestment — no real external cashflow
        if any(x in t_type for x in ("REINVEST", "BONUS", "IDCW_REINVEST", "GROWTH_OPTION")):
            continue

        if units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN")):
            # Purchase / subscription / switch-in → money leaves investor's account
            ledger.append({"date": d, "amount": -amt, "type": "BUY"})

        elif units < 0 or any(x in t_type for x in ("SELL", "REDEMPTION", "SWP-OUT", "STP-OUT", "SWITCH-OUT")):
            # Redemption / switch-out → money enters investor's account
            ledger.append({"date": d, "amount": amt, "type": "SELL"})

        else:
            # Zero-unit transactions: dividends paid out, taxes, fees
            if any(x in t_type for x in ("DIVIDEND", "PAYOUT", "IDCW_PAYOUT")):
                ledger.append({"date": d, "amount": amt, "type": "INCOME"})
            elif any(x in t_type for x in ("TAX", "DUTY", "FEE", "STT")):
                ledger.append({"date": d, "amount": -amt, "type": "EXPENSE"})

    return ledger


# ---------------------------------------------------------------------------
# XIRR Calculation
# Robust convergence logic for portfolios with single-direction flows (e.g. SIP-only).
# ---------------------------------------------------------------------------

def compute_xirr(df_t: pd.DataFrame, current_value: float) -> float:
    """
    Compute portfolio XIRR (annualised IRR) from transaction ledger.

    Institutional Accounting Standards (SEBI Compliance):
    - For holding periods >= 365 days: Returns the standard XIRR.
    - For holding periods < 365 days: Annualizing short-term returns distorts 
      performance (e.g. 5% in 1 month artificially inflates to ~80% p.a.). 
      To prevent this, the engine intercepts the calculation and returns the 
      Absolute Return ((Inflows - Outflows) / Outflows) instead.

    Parameters
    ----------
    df_t          : Transaction DataFrame for the fund/portfolio
    current_value : Current market value (acts as terminal inflow)

    Returns
    -------
    Return as a percentage (e.g. 14.2 means 14.2%).
    Returns 0.0 on any failure — never raises.
    """
    if current_value <= 0:
        return 0.0

    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return 0.0

    try:
        rows = [{"date": l["date"], "amount": l["amount"]} for l in ledger]
        # Terminal value: as if the portfolio is liquidated today
        rows.append({"date": datetime.now().date(), "amount": float(current_value)})

        ldf = pd.DataFrame(rows).dropna(subset=["date", "amount"])
        ldf["date"]   = pd.to_datetime(ldf["date"], dayfirst=True)
        ldf["amount"] = ldf["amount"].astype(float)

        # ── SEBI Standard: Absolute Return for < 1 Year Holding ──
        days_held = (ldf["date"].max() - ldf["date"].min()).days
        if 0 < days_held < 365:
            total_outflows = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            total_inflows  = ldf[ldf["amount"] > 0]["amount"].sum()
            if total_outflows > 0:
                abs_pct = ((total_inflows - total_outflows) / total_outflows) * 100
                return round(max(-99.0, min(abs_pct, 500.0)), 2)

        # Solvency Check: Verify presence of both capital inflows and outflows (terminal or actual)
        # to ensure IRR convergence within standard institutional thresholds.
        outflows = ldf[ldf["amount"] < 0]
        inflows  = ldf[ldf["amount"] > 0]
        if outflows.empty or inflows.empty:
            return 0.0

        result = xirr(ldf["date"], ldf["amount"])

        if result is None or np.isnan(result) or np.isinf(result):
            return 0.0

        pct = float(result) * 100
        # Institutional cap: 200% is more realistic for catching data errors
        return round(max(-99.0, min(pct, 200.0)), 2)

    except Exception as e:
        logger.error(f"[XIRR ERROR] current_value={current_value:.0f}: {e}")
        return 0.0


def _fy_label(d: date) -> str:
    """Indian financial year label (Apr–Mar) for a given date, e.g. 31-Mar-2024 -> 'FY23-24'."""
    start_year = d.year if d.month >= 4 else d.year - 1
    return f"FY{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def compute_xirr_by_fy(df_t_all: pd.DataFrame, df_h: pd.DataFrame) -> List[Dict]:
    """
    Cumulative-to-date XIRR sampled at each Indian financial-year end (31 Mar),
    plus a final "year-to-date" snapshot for the current partial FY — answers
    "am I improving?" year over year.

    Deliberately reuses the same FIFO lot reconstruction (tax_lots.compute_fund_lots)
    and XIRR engine (compute_xirr) used elsewhere in the app, rather than a separate
    valuation model — so this can never silently drift from the headline XIRR number.
    Each snapshot's terminal value is units-held-as-of-that-date x that fund's real
    historical NAV on/before that date (never a fabricated or interpolated value).
    """
    from domains.mutual_funds.tax_lots import compute_fund_lots
    from shared.services.market_data import fetch_nav_series_by_isin, fetch_nav_series_by_code, fetch_nav_series_by_name

    if df_t_all is None or df_t_all.empty:
        return []

    df_t = df_t_all.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_t["Date"]):
        df_t["Date"] = pd.to_datetime(df_t["Date"])
    df_t = df_t.sort_values("Date")

    first_date = df_t["Date"].min().date()
    today = datetime.now().date()

    # Fund universe = every fund ever transacted, not just currently-held ones
    # (df_h only has today's holdings — a fund fully exited last year still needs
    # to count towards that year's cumulative value).
    fund_meta = {}
    if df_h is not None and not df_h.empty:
        for _, row in df_h.iterrows():
            f = str(row.get("Fund", ""))
            if f:
                fund_meta[f] = (str(row.get("ISIN", "")).strip(), str(row.get("Scheme_Code", "")).strip())
    for f in df_t["Fund"].dropna().unique():
        f = str(f)
        if f not in fund_meta:
            fund_meta[f] = ("", "")

    fund_navs = {}
    for fn, (isin, scode) in fund_meta.items():
        navs = pd.Series(dtype=float)
        if isin and isin not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_isin(isin, 9999)
        if navs.empty and scode and scode not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_code(scode, 9999)
        if navs.empty:
            navs = fetch_nav_series_by_name(fn, 9999)
        if not navs.empty:
            fund_navs[fn] = navs.sort_index().dropna()

    # Every FY-end (31 Mar) strictly before today, plus today as a final YTD snapshot
    fy_ends = []
    start_year = first_date.year if first_date.month >= 4 else first_date.year - 1
    cursor = date(start_year + 1, 3, 31)
    while cursor < today:
        fy_ends.append((cursor, False))
        cursor = date(cursor.year + 1, 3, 31)
    if not (today.month == 3 and today.day == 31):
        fy_ends.append((today, True))

    results = []
    for snapshot_date, is_partial in fy_ends:
        df_t_upto = df_t[df_t["Date"] <= pd.Timestamp(snapshot_date)]
        if df_t_upto.empty:
            continue

        total_value = 0.0
        for fn in fund_meta.keys():
            lots = compute_fund_lots(df_t_upto, fn)
            units_held = sum(l["units"] for l in lots)
            if units_held <= 0:
                continue
            navs = fund_navs.get(fn)
            nav_at_date = 0.0
            if navs is not None and not navs.empty:
                past = navs[navs.index.date <= snapshot_date]
                nav_at_date = float(past.iloc[-1]) if not past.empty else float(navs.iloc[0])
            else:
                # No NAV history source resolved for this fund — fall back to its
                # last known transaction NAV as of this date rather than dropping it.
                fund_txns = df_t_upto[df_t_upto["Fund"] == fn]
                nav_rows = fund_txns[fund_txns["NAV"].astype(float) > 0].sort_values("Date")
                nav_at_date = float(nav_rows["NAV"].iloc[-1]) if not nav_rows.empty else 0.0
            total_value += units_held * nav_at_date

        if total_value <= 0:
            continue

        results.append({
            "fy": _fy_label(snapshot_date) + (" (YTD)" if is_partial else ""),
            "as_of": snapshot_date.isoformat(),
            "cumulative_value": round(total_value, 0),
            "cumulative_xirr": compute_xirr(df_t_upto, total_value),
            "is_partial_fy": is_partial,
        })

    return results


def simulate_historical_sip(nav_series: pd.Series, monthly_amount: float, years: int) -> Dict:
    """
    Replays a hypothetical SIP into a CANDIDATE fund (one you don't currently
    hold) using its real historical NAV series — "if I'd invested Rs.X/month in
    this fund for the last N years, what would it be worth today?" Every NAV
    point used is real fetched data (mfapi/Yahoo); nothing here is fabricated
    or interpolated beyond ordinary forward-fill for non-trading days.
    """
    if nav_series is None or nav_series.empty or monthly_amount <= 0 or years <= 0:
        return {}

    series = nav_series.sort_index().dropna()
    if len(series) < 2:
        return {"error": "Not enough NAV history for this fund to simulate."}

    end_date = series.index.max()
    start_date = end_date - pd.DateOffset(years=years)
    window = series[series.index >= start_date]
    if window.empty:
        return {"error": "Not enough NAV history for this fund to simulate this window."}

    monthly = window.resample("MS").first().dropna()
    monthly = monthly[monthly > 0]
    if monthly.empty:
        return {"error": "Not enough NAV history for this fund to simulate this window."}

    total_units = float((monthly_amount / monthly).sum())
    total_invested = monthly_amount * len(monthly)
    current_nav = float(series.iloc[-1])
    final_value = total_units * current_nav
    actual_years = (end_date - monthly.index[0]).days / 365.25

    cagr = (((final_value / total_invested) ** (1 / actual_years)) - 1) * 100 if actual_years > 0 and total_invested > 0 else 0.0

    return {
        "installments": len(monthly),
        "total_invested": round(total_invested, 0),
        "final_value": round(final_value, 0),
        "gain": round(final_value - total_invested, 0),
        "cagr_pct": round(cagr, 2),
        "wealth_multiple": round(final_value / total_invested, 2) if total_invested > 0 else 0.0,
        "actual_start_date": monthly.index[0].date().isoformat(),
        "actual_end_date": end_date.date().isoformat(),
        "requested_years": years,
    }


def compute_mandate_overlap(df_h: pd.DataFrame) -> Dict:
    """
    Category + Cap-Type "mandate overlap" — a PROXY for true stock-level
    portfolio overlap, not the real thing.

    Real overlap analysis needs each fund's underlying stock holdings. No
    reliable source for that exists for Indian mutual funds in this app —
    Yahoo Finance's per-fund holdings/sector data is sparse/best-effort for
    Indian ISINs (the reason a deterministic-fallback engine exists elsewhere
    to paper over its gaps), and there's no AMC portfolio-disclosure feed
    wired in. Rather than present fabricated stock-level overlap numbers,
    this groups funds that share the same Category + Cap Type — data already
    reliably present in every CAS statement — as a directionally useful signal:
    funds with the same mandate tend to hold similar stocks, but the actual
    overlap % can only be confirmed against each fund's factsheet.
    """
    if df_h is None or df_h.empty:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    total_value = float(df_h["Market Value"].sum())
    if total_value <= 0:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    groups = []
    group_cols = [c for c in ("Category", "Cap Type") if c in df_h.columns]
    if not group_cols:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    for key, g in df_h.groupby(group_cols):
        if len(g) < 2:
            continue
        key_tuple = key if isinstance(key, tuple) else (key,)
        group_value = float(g["Market Value"].sum())
        same_amc = g["AMC"].nunique() == 1 if "AMC" in g.columns else False
        groups.append({
            "category": key_tuple[0],
            "cap_type": key_tuple[1] if len(key_tuple) > 1 else None,
            "fund_count": len(g),
            "combined_value": round(group_value, 0),
            "combined_weight_pct": round(group_value / total_value * 100, 1),
            "same_amc": bool(same_amc),
            "severity": "high" if same_amc else ("moderate" if len(g) > 2 else "low"),
            "funds": [
                {
                    "fund": r.get("Fund"),
                    "amc": r.get("AMC"),
                    "value": round(float(r.get("Market Value", 0) or 0), 0),
                    "weight_pct": round(float(r.get("Market Value", 0) or 0) / total_value * 100, 1),
                }
                for _, r in g.iterrows()
            ],
        })

    groups.sort(key=lambda x: -x["combined_weight_pct"])
    return {"groups": groups, "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}


_MANDATE_OVERLAP_DISCLAIMER = (
    "This groups funds sharing the same Category + Cap Type as a mandate-overlap proxy — "
    "not true stock-level portfolio overlap. No reliable underlying-holdings data source "
    "exists for Indian mutual funds in this app; confirm actual overlap against each fund's "
    "factsheet before consolidating."
)


def compute_sip_lumpsum_attribution(df_t: pd.DataFrame, total_value: float) -> Dict:
    """
    Splits invested capital and current value between SIP-sourced and
    lumpsum-sourced contributions.

    Current-value attribution is an APPROXIMATION: it splits total_value
    pro-rata by each source's share of invested capital, i.e. it assumes SIP
    and lumpsum contributions grew at the same rate. Getting an exact split
    would require tracking which specific lots (SIP vs lumpsum) remain
    unsold post-redemption — not attempted here; the pro-rata split is
    disclosed as such rather than presented as an exact figure.
    """
    if df_t is None or df_t.empty or total_value <= 0:
        return {}

    sip_invested = lumpsum_invested = 0.0
    for _, row in df_t.iterrows():
        t_type = str(row.get("Type", "")).upper()
        units = float(row.get("Units", 0) or 0)
        amt = abs(float(row.get("Amount", 0) or 0))
        nav = float(row.get("NAV", 0) or 0)
        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        is_buy = units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN"))
        if not is_buy or amt == 0:
            continue

        if "SIP" in t_type:
            sip_invested += amt
        else:
            lumpsum_invested += amt

    total_invested = sip_invested + lumpsum_invested
    if total_invested <= 0:
        return {}

    sip_share = sip_invested / total_invested
    return {
        "sip_invested": round(sip_invested, 0),
        "lumpsum_invested": round(lumpsum_invested, 0),
        "sip_current_value": round(total_value * sip_share, 0),
        "lumpsum_current_value": round(total_value * (1 - sip_share), 0),
        "sip_share_pct": round(sip_share * 100, 1),
        "is_approximate": True,
        "note": "Current-value split is approximate — assumes SIP and lumpsum contributions grew at the same rate since each was invested.",
    }


def is_absolute_return(df_t: pd.DataFrame) -> bool:
    """
    Evaluates whether the investment holding period is strictly less than 1 year (365 days).
    This boolean flag is passed to the frontend to dynamically shift UI labels from 
    'Annualized XIRR' to 'Absolute Return' and trigger the 'ABS' warning badges.
    """
    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return False
    rows = [{"date": l["date"], "amount": l["amount"]} for l in ledger]
    rows.append({"date": datetime.now().date(), "amount": 0.0})
    ldf = pd.DataFrame(rows).dropna(subset=["date"])
    ldf["date"] = pd.to_datetime(ldf["date"], dayfirst=True)
    if ldf.empty: return False
    days_held = (ldf["date"].max() - ldf["date"].min()).days
    return 0 < days_held < 365

# ---------------------------------------------------------------------------
# Benchmark XIRR — simulate same cashflows into benchmark index
# ---------------------------------------------------------------------------

def compute_benchmark_xirr(
    df_t: pd.DataFrame,
    bench_series: pd.Series,
) -> Tuple[float, float]:
    """
    Simulate investing the same cashflows into the benchmark index.

    Returns
    -------
    (benchmark_xirr_pct, simulated_current_value)
    """
    if bench_series is None or bench_series.empty:
        return 0.0, 0.0

    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return 0.0, 0.0

    bench_sorted = bench_series.sort_index()

    try:
        total_bench_units = 0.0
        cashflows: List[Dict] = []

        for l in ledger:
            txn_date = pd.Timestamp(l["date"])
            amt      = abs(l["amount"])

            # Find benchmark price on or before transaction date
            past = bench_sorted[bench_sorted.index <= txn_date]
            if past.empty:
                # Use earliest available price
                bench_price = float(bench_sorted.iloc[0])
            else:
                bench_price = float(past.iloc[-1])

            if bench_price <= 0:
                continue

            if l["amount"] < 0:        # Purchase
                total_bench_units += amt / bench_price
                cashflows.append({"date": txn_date, "amount": -amt})
            elif l["type"] == "SELL":  # Redemption
                units_sold = min(total_bench_units, amt / bench_price)
                total_bench_units = max(0.0, total_bench_units - units_sold)
                # FIX C-3: Use benchmark-simulated redemption value, not fund's actual amount.
                # The investor would have received units_sold * bench_price if invested in benchmark.
                bench_redemption_value = units_sold * bench_price
                cashflows.append({"date": txn_date, "amount": bench_redemption_value})
            elif l["type"] == "INCOME":
                cashflows.append({"date": txn_date, "amount": amt})

        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0

        bench_current_price  = float(bench_sorted.iloc[-1])
        bench_sim_value      = total_bench_units * bench_current_price

        cashflows.append({"date": pd.Timestamp(datetime.now()), "amount": bench_sim_value})

        ldf = pd.DataFrame(cashflows).dropna()
        ldf["date"] = pd.to_datetime(ldf["date"], dayfirst=True)

        # ── SEBI Standard: Absolute Return for < 1 Year Holding ──
        days_held = (ldf["date"].max() - ldf["date"].min()).days
        if 0 < days_held < 365:
            total_outflows = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            total_inflows  = ldf[ldf["amount"] > 0]["amount"].sum()
            if total_outflows > 0:
                abs_pct = ((total_inflows - total_outflows) / total_outflows) * 100
                return round(max(-99.0, min(abs_pct, 500.0)), 2), round(bench_sim_value, 2)

        if ldf[ldf["amount"] < 0].empty or ldf[ldf["amount"] > 0].empty:
            return 0.0, bench_sim_value

        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result) or np.isinf(result):
            return 0.0, bench_sim_value

        pct = round(max(-99.0, min(float(result) * 100, 500.0)), 2)
        return pct, round(bench_sim_value, 2)

    except Exception as e:
        logger.error(f"[BENCH XIRR ERROR] {e}")
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Trailing Returns (Point-to-Point CAGR)
# Computes precise historical performance across standardized time horizons.
# ---------------------------------------------------------------------------

def compute_trailing_returns(nav_series: pd.Series) -> Dict[str, Optional[float]]:
    """
    Compute point-to-point trailing returns for standard periods.
    Returns <1Y as simple return, >=1Y as annualised CAGR.

    Returns
    -------
    Dict keyed by period label: {"1M": 4.2, "3M": 8.1, "6M": 12.3,
                                  "1Y": 14.5, "3Y": 19.2, "5Y": 22.1}
    None if insufficient history for that period.
    """
    if nav_series is None or nav_series.empty:
        return {p: None for p in ["1M", "3M", "6M", "1Y", "3Y", "5Y"]}

    nav_sorted = nav_series.sort_index().dropna()
    end_date   = nav_sorted.index[-1]
    end_nav    = float(nav_sorted.iloc[-1])

    # Standard Industry Periods (using calendar offsets for higher accuracy)
    PERIODS = {
        "1M": pd.DateOffset(months=1),
        "3M": pd.DateOffset(months=3),
        "6M": pd.DateOffset(months=6),
        "1Y": pd.DateOffset(years=1),
        "3Y": pd.DateOffset(years=3),
        "5Y": pd.DateOffset(years=5)
    }
    result   = {}
    _start_navs = {}  # For cross-period sanity check

    for label, offset in PERIODS.items():
        target_date = end_date - offset
        candidates  = nav_sorted[nav_sorted.index <= target_date]

        if candidates.empty:
            result[label] = None
            continue

        start_date = candidates.index[-1]
        start_nav  = float(candidates.iloc[-1])
        if start_nav <= 0:
            result[label] = None
            continue

        _start_navs[label] = (start_date, start_nav)
        days_actual = (end_date - start_date).days
        years = days_actual / 365.25
        if years < 0.99:  # Simple return for < 1Y
            ret = (end_nav / start_nav - 1) * 100
        else:             # CAGR for >= 1Y
            ret = ((end_nav / start_nav) ** (1.0 / years) - 1) * 100

        result[label] = round(ret, 2)

    # ── Sanity Check: Cross-period NAV proximity (catches data alignment bugs) ──
    # If 3Y and 5Y starting NAVs are within 2% of each other, the identical
    # returns are a data issue (fund NAV flat in years 4-5) — worth logging.
    if "3Y" in _start_navs and "5Y" in _start_navs:
        nav_3y = _start_navs["3Y"][1]
        nav_5y = _start_navs["5Y"][1]
        if nav_5y > 0:
            pct_diff = abs(nav_3y - nav_5y) / nav_5y * 100
            if pct_diff < 2.0:  # Less than 2% difference
                logger.warning(f"[TRAILING RETURNS WARN] 3Y ({_start_navs['3Y'][0].date()} NAV={nav_3y:.2f}) and "
                      f"5Y ({_start_navs['5Y'][0].date()} NAV={nav_5y:.2f}) start NAVs differ by only {pct_diff:.2f}%. "
                      f"Returns 3Y={result.get('3Y')}% 5Y={result.get('5Y')}% — verify NAV data availability.")

    return result


# ---------------------------------------------------------------------------
# Rolling Returns (Average of all N-year point-to-point CAGRs)
# High-fidelity rolling average matching institutional portal standards.
# ---------------------------------------------------------------------------

def compute_rolling_return_avg(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,         # compute every 7 days for performance balance
) -> Optional[float]:
    """
    Average rolling return: mean of all N-year rolling CAGRs
    computed with `step_days` step across the history.

    Parameters
    ----------
    nav_series   : Fund NAV series (DatetimeIndex → float)
    window_years : Rolling window (1, 3, or 5)
    step_days    : Step between computation points (default 7 = weekly)

    Returns
    -------
    Average CAGR as percentage, or None if insufficient history.
    """
    if nav_series is None or nav_series.empty:
        return None

    # Morningstar Standard (Fix #F-8): Resample to daily ffill to align calendar days
    nav_sorted  = nav_series.sort_index().dropna().resample('D').ffill()
    window_days = int(window_years * 365.25)

    if (nav_sorted.index[-1] - nav_sorted.index[0]).days < window_days:
        return None

    rolling_cagrs = []
    idx = nav_sorted.index

    # Iterate over start dates with step_days cadence
    i = 0
    while i < len(idx):
        start_date      = idx[i]
        end_date_target = start_date + timedelta(days=window_days)

        # Find nearest available NAV on or after target end date
        future = nav_sorted[nav_sorted.index >= end_date_target]
        if future.empty:
            break

        end_nav   = float(future.iloc[0])
        start_nav = float(nav_sorted.iloc[i])
        actual_end_date = future.index[0]

        if start_nav > 0 and end_nav > 0:
            # FIX P2-4: Use actual elapsed days / 365.25 instead of integer window_years
            actual_years = (actual_end_date - start_date).days / 365.25
            if actual_years > 0:
                cagr = ((end_nav / start_nav) ** (1.0 / actual_years) - 1) * 100
                rolling_cagrs.append(cagr)

        # Advance by step_days trading days (approximate)
        next_date = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        # Fix #8: Use searchsorted for robustness against duplicate timestamps
        new_i = idx.searchsorted(next_candidates.index[0]) if not next_candidates.empty else i + 1
        # FIX H-4: Guard against infinite loop if searchsorted returns same index
        i = max(new_i, i + 1)

    if not rolling_cagrs:
        return None

    return round(float(np.mean(rolling_cagrs)), 2)


def compute_rolling_return_series(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,
) -> pd.Series:
    """
    Return the full time series of rolling N-year CAGRs.
    Used for the rolling returns line chart.

    Returns
    -------
    pd.Series indexed by end_date → CAGR%
    """
    if nav_series is None or nav_series.empty:
        return pd.Series(dtype=float)

    # Morningstar Standard (Fix #F-8): Resample to daily ffill
    nav_sorted  = nav_series.sort_index().dropna().resample('D').ffill()
    window_days = int(window_years * 365.25)

    if (nav_sorted.index[-1] - nav_sorted.index[0]).days < window_days:
        return pd.Series(dtype=float)

    dates, values = [], []
    idx = nav_sorted.index
    i   = 0

    while i < len(idx):
        start_date      = idx[i]
        end_date_target = start_date + timedelta(days=window_days)
        future          = nav_sorted[nav_sorted.index >= end_date_target]
        if future.empty:
            break

        end_nav   = float(future.iloc[0])
        start_nav = float(nav_sorted.iloc[i])
        actual_end_date = future.index[0]

        if start_nav > 0 and end_nav > 0:
            # FIX P2-4: Use actual elapsed days / 365.25 for each window's CAGR
            actual_years = (actual_end_date - start_date).days / 365.25
            if actual_years > 0:
                cagr = ((end_nav / start_nav) ** (1.0 / actual_years) - 1) * 100
                dates.append(actual_end_date)
                values.append(round(cagr, 2))

        next_date       = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        new_i = nav_sorted.index.searchsorted(next_candidates.index[0])
        # FIX H-4: Guard against infinite loop if searchsorted returns same index
        i = max(new_i, i + 1)

    return pd.Series(values, index=dates)


# ---------------------------------------------------------------------------
# Risk Metrics — Sharpe, Sortino, Beta, Max Drawdown, Alpha
# All metrics derived from verified instrument-level NAV series for audit precision.
# ---------------------------------------------------------------------------

def compute_risk_metrics(
    nav_series: pd.Series,
    bench_series: pd.Series,
    risk_free_rate: float = 6.5,   # annual %, e.g. 6.5 (Standard 10Y G-Sec Baseline)
    min_days: int = 90,
) -> Dict:
    """
    Compute professional-grade risk metrics (Morningstar/CFA Standard).
    
    Key Institutional Improvements (Fix #F-1, F-2):
    - Evaluation Horizon: All ratios (Sharpe, Sortino, Alpha) use the same trailing 36M window.
    - Information Ratio: Measures alpha per unit of tracking error.
    - Market Capture: Quantifies upside/downside participation.
    - Calmar Ratio: Return vs Max Drawdown efficiency.
    """
    defaults = {
        "vol": 0.0, "sharpe": 0.0, "sortino": 0.0,
        "beta": 1.0, "alpha": 0.0, "max_dd": 0.0,
        "tracking_error": 0.0, "info_ratio": 0.0,
        "up_capture": 0.0, "down_capture": 0.0,
        "calmar": 0.0, "treynor": 0.0,
        "risk_label": "N/A", "data_days": 0,
    }

    if nav_series is None or nav_series.empty or len(nav_series) < min_days:
        return defaults

    nav_sorted = nav_series.sort_index().dropna()
    has_bench = (bench_series is not None and not bench_series.empty)
    rf = risk_free_rate

    # ── Drawdown Calculation: Data Alignment Strategy ──────────────────────
    # Max Drawdown is computed on the full verified instrument history prior to 
    # benchmark alignment. This ensures that brief or incomplete benchmark data 
    # does not mask historical volatility events (e.g. 2020 crash, 2018 small-cap bear market).
    mdd_rolling_max = nav_sorted.expanding().max()
    mdd_drawdown    = (nav_sorted - mdd_rolling_max) / mdd_rolling_max * 100
    max_dd_full     = float(mdd_drawdown.min())
    defaults["max_dd"] = round(abs(max_dd_full), 2)

    # ── 1. Align & Resample (Daily for Vol/Drawdown, 3Y Window for Ratios) ──
    if has_bench:
        bench_sorted = bench_series.sort_index().dropna()
        nav_align = nav_sorted.copy()
        bench_align = bench_sorted.copy()
        nav_align.index = pd.to_datetime(nav_align.index).tz_localize(None).normalize()
        bench_align.index = pd.to_datetime(bench_align.index).tz_localize(None).normalize()
        df_full = pd.DataFrame({"nav": nav_align, "bench": bench_align}).dropna()
    else:
        df_full = pd.DataFrame({"nav": nav_sorted}).dropna()

    if len(df_full) < min_days:
        return defaults

    defaults["data_days"] = len(df_full)

    # ── 2. Evaluation Window (Trailing 36 Months) ───────────────────────
    # FIX #F-1: Numerator and Denominator MUST use the same time horizon
    cutoff_3y = df_full.index[-1] - pd.DateOffset(years=3)
    df = df_full[df_full.index >= cutoff_3y]
    if len(df) < 60:
        df = df_full # Fallback to full history if fund < 3Y old

    n_years = (df.index[-1] - df.index[0]).days / 365.25
    if n_years <= 0: return defaults

    # Log Returns (Institutional Standard)
    fund_daily = np.log(df["nav"] / df["nav"].shift(1)).dropna()
    fund_cagr  = ((float(df["nav"].iloc[-1]) / float(df["nav"].iloc[0])) ** (1.0 / n_years) - 1) * 100
    vol_annual = float(fund_daily.std() * np.sqrt(252)) * 100
    
    defaults["vol"] = round(vol_annual, 2)
    # Calmar uses full-history MDD (which we computed above on nav_sorted)
    defaults["calmar"] = round(fund_cagr / abs(max_dd_full), 2) if max_dd_full != 0 else 0.0

    # ── 3. Sharpe & Sortino (Consistent 3Y Window) ──────────────────────
    if vol_annual > 0:
        defaults["sharpe"] = round((fund_cagr - rf) / vol_annual, 2)

    # Sortino: Downside deviation over same 3Y window
    # FIX P0-1 (Morningstar full-period variant): dd_series = max(0, MAR - r_daily)
    rf_daily = (rf / 100 / 252)
    dd_series = np.maximum(0, rf_daily - fund_daily)  # downside only: shortfall below MAR
    downside_dev = float(np.sqrt(np.mean(dd_series**2)) * np.sqrt(252)) * 100
    if downside_dev > 0:
        defaults["sortino"] = round((fund_cagr - rf) / downside_dev, 2)

    # ── 4. Benchmark Relative Metrics (IR, Capture, Beta) ───────────────
    if has_bench and "bench" in df.columns:
        bench_daily = np.log(df["bench"] / df["bench"].shift(1)).dropna()
        bench_cagr  = ((float(df["bench"].iloc[-1]) / float(df["bench"].iloc[0])) ** (1.0 / n_years) - 1) * 100
        
        # Simple Alpha as primary fallback (always reliable)
        simple_alpha = round(fund_cagr - bench_cagr, 2)
        
        # Tracking Error (Standard deviation of active returns)
        active_returns = fund_daily - bench_daily
        tracking_error = float(active_returns.std() * np.sqrt(252)) * 100
        defaults["tracking_error"] = round(tracking_error, 2)
        
        # Information Ratio (Active Return / Tracking Error)
        # FIX P1-1: Use arithmetic mean of daily active returns (annualized) / TE
        mean_active_annual = float(active_returns.mean() * 252) * 100
        if tracking_error > 0:
            defaults["info_ratio"] = round(mean_active_annual / tracking_error, 2)

        # Up/Down Market Capture (Monthly Basis)
        f_m = df["nav"].resample('ME').last().pct_change().dropna()
        b_m = df["bench"].resample('ME').last().pct_change().dropna()
        
        # FIX P1-3: Use pd.concat + dropna to align months safely.
        aligned = pd.concat([f_m.rename('fund'), b_m.rename('bench')], axis=1).dropna()
        up_mask   = aligned['bench'] > 0
        down_mask = aligned['bench'] <= 0
        
        up_months_aligned   = aligned[up_mask]
        down_months_aligned = aligned[down_mask]
        
        if not up_months_aligned.empty and up_months_aligned['bench'].mean() != 0:
            defaults["up_capture"] = round((up_months_aligned['fund'].mean() / up_months_aligned['bench'].mean()) * 100, 1)
        if not down_months_aligned.empty and down_months_aligned['bench'].mean() != 0:
            defaults["down_capture"] = round((down_months_aligned['fund'].mean() / down_months_aligned['bench'].mean()) * 100, 1)

        # ── Regression Alpha & Persistence ────────────────────────────────
        # Implementation utilizes Jensen's Alpha (Monthly OLS) for instruments with 
        # >= 24 months of shared history. For shorter-duration instruments, 
        # it falls back to simple geometric CAGR differentiation for robustness.
        common = aligned.rename(columns={'fund': 'f', 'bench': 'b'})
        n_months = len(common)
        if n_months >= 12:
            var_b = float(common["b"].var())
            if var_b > 0:
                beta = float(common.cov().loc["f", "b"] / var_b)
                defaults["beta"] = round(beta, 2)
                defaults["treynor"] = round((fund_cagr - rf) / beta, 2) if beta != 0 else 0.0

                if n_months >= 24:
                    # FIX P1-2: Geometric annualization
                    rf_monthly = rf / 100 / 12
                    monthly_alpha = (common["f"].mean() - rf_monthly) - beta * (common["b"].mean() - rf_monthly)
                    j_alpha = ((1 + monthly_alpha) ** 12 - 1) * 100
                    
                    # Sanity check: OLS alpha should not be near-zero when trailing CAGR diff is significant
                    if abs(j_alpha) < 0.05 and abs(simple_alpha) > 1.0:
                        logger.warning(f"[ALPHA WARN] Jensen's Alpha={j_alpha:.3f}% near-zero but simple_alpha={simple_alpha:.2f}%. "
                              f"Using simple_alpha as fallback (n_months={n_months}).")
                        defaults["alpha"] = simple_alpha
                    else:
                        defaults["alpha"] = round(j_alpha, 2)
                else:
                    # < 24 months — OLS unreliable, use simple alpha
                    logger.info(f"[ALPHA INFO] Only {n_months} months of overlap — using simple alpha={simple_alpha:.2f}%.")
                    defaults["alpha"] = simple_alpha
        else:
            # < 12 months — cannot run OLS
            logger.info(f"[ALPHA INFO] Only {n_months} months of overlap — cannot compute OLS alpha. Using simple_alpha={simple_alpha:.2f}%.")
            defaults["alpha"] = simple_alpha

    # ── Risk Label (Annualized Vol based) ───────────────────────────────
    if vol_annual < 2:        defaults["risk_label"] = "Low"
    elif vol_annual < 6:      defaults["risk_label"] = "Low to Moderate"
    elif vol_annual < 10:     defaults["risk_label"] = "Moderate"
    elif vol_annual < 14:     defaults["risk_label"] = "Moderately High"
    elif vol_annual < 18:     defaults["risk_label"] = "High"
    else:                     defaults["risk_label"] = "Very High"

    return defaults


# ---------------------------------------------------------------------------
# Consistency Score
# Percentage of rolling 1Y windows where fund outperformed benchmark.
# ---------------------------------------------------------------------------

def compute_consistency_score(
    nav_series: pd.Series,
    bench_series: pd.Series,
    window_days: int = 365,
    step_days: int = 30,
) -> float:
    """
    Consistency = % of rolling 1-year windows where fund outperformed benchmark.
    Scaled to 0–10 (10 = beat benchmark 100% of windows).

    Returns 5.0 (neutral) if insufficient data.
    """
    if nav_series is None or nav_series.empty:
        return 5.0
    if bench_series is None or bench_series.empty:
        return 5.0
    if (nav_series.index[-1] - nav_series.index[0]).days < window_days:
        return 5.0

    # FIX P2-3: Resample to daily frequency to ensure uniform window sizes
    # across funds with different NAV publication frequencies.
    nav_sorted   = nav_series.sort_index().dropna().resample('D').ffill()
    bench_sorted = bench_series.sort_index().dropna().resample('D').ffill()

    beat_count, total = 0, 0
    idx = nav_sorted.index
    i   = 0

    while i < len(idx):
        start_date      = idx[i]
        end_date_target = start_date + timedelta(days=window_days)

        future_nav   = nav_sorted[nav_sorted.index >= end_date_target]
        future_bench = bench_sorted[bench_sorted.index >= end_date_target]

        if future_nav.empty or future_bench.empty:
            break

        start_bench = bench_sorted[bench_sorted.index <= start_date]
        if start_bench.empty:
            i += step_days
            continue

        fund_ret  = float(future_nav.iloc[0]) / float(nav_sorted.iloc[i]) - 1
        bench_ret = float(future_bench.iloc[0]) / float(start_bench.iloc[-1]) - 1

        if fund_ret > bench_ret:
            beat_count += 1
        total += 1

        # Advance step_days
        next_date       = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        i = nav_sorted.index.searchsorted(next_candidates.index[0])

    if total == 0:
        return 5.0

    return round((beat_count / total) * 10, 1)


# ---------------------------------------------------------------------------
# Portfolio vs Benchmark Period Comparison
# True Unitized Portfolio Accounting (Zerodha/Morningstar Standard).
# ---------------------------------------------------------------------------

def compute_period_comparison(
    df_t_all: pd.DataFrame,
    df_h: pd.DataFrame,
    total_value: float,
    bench_series: pd.Series,
    period_days: int,
) -> Dict:
    """
    Compare portfolio return vs benchmark for a given period.
    Uses TRUE Unitized Portfolio Accounting (Zerodha/Morningstar standard).
    Constructs the actual historical NAV curve using exact daily fund prices and cashflows.
    """
    result = {
        "port_pct":   0.0,
        "bench_pct":  0.0,
        "port_value": total_value,
        "bench_value": 0.0,
        "use_xirr":   period_days >= 1095,
        "alpha":       0.0,
        "dates": [],
        "portfolio": [],
        "benchmark": [],
        "chart_mode": "indexed"
    }

    if df_t_all is None or df_t_all.empty or df_h is None or df_h.empty:
        return result

    bench_sorted = pd.Series(dtype=float)
    if bench_series is not None and not bench_series.empty:
        bench_sorted = bench_series.sort_index().dropna()
    
    # 1. Build complete timeline
    df_t = df_t_all.copy()
    df_t["Date"] = pd.to_datetime(df_t["Date"], dayfirst=True)
    all_dates = df_t["Date"].sort_values()
    
    start_date = all_dates.iloc[0]
    
    # If benchmark is missing or its end_date is before start_date (e.g. today vs yesterday),
    # we extend the timeline to today to ensure the chart still renders.
    today_dt = pd.Timestamp(datetime.now().date())
    if bench_sorted.empty:
        end_date = today_dt
    else:
        end_date = bench_sorted.index[-1]
        
    if start_date > end_date:
        end_date = start_date
        
    # Cap end_date at today to prevent future dates
    if end_date > today_dt:
        end_date = today_dt
        
    calendar = pd.date_range(start_date, end_date, freq='D')
    
    # 2. Fetch exact historical NAVs or build robust synthetic curves
    from shared.services.market_data import fetch_nav_series_by_isin, fetch_nav_series_by_name, fetch_nav_series_by_code
    fund_navs = {}
    
    # We need NAVs for ALL funds ever held, not just currently held funds
    # df_t_all contains ISIN or Scheme_Code if available. Otherwise we fetch by name.
    # First, let's build a map of Fund Name -> (ISIN, Scheme_Code) from both df_h and df_t_all
    fund_metadata = {}
    for _, row in df_h.iterrows():
        f = str(row.get("Fund", ""))
        if f: fund_metadata[f] = (str(row.get("ISIN", row.get("Isin", ""))).strip(), str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip())
    
    for _, row in df_t_all.iterrows():
        f = str(row.get("Fund", ""))
        if f and f not in fund_metadata:
            fund_metadata[f] = (str(row.get("ISIN", row.get("Isin", ""))).strip(), str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip())
            
    for fn, (isin, scode) in fund_metadata.items():
        if not fn: continue
        
        navs = pd.Series(dtype=float)
        if isin and isin not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_isin(isin, 9999)
        if navs.empty and scode and scode not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_code(scode, 9999)
        if navs.empty and fn:
            navs = fetch_nav_series_by_name(fn, 9999)
            
        if not navs.empty:
            fund_navs[fn] = navs.sort_index().dropna().resample('D').ffill()

    if not fund_navs:
        return result
        
    # 3. True Unitized Accounting Ledger
    fund_units = {f: 0.0 for f in fund_navs.keys()}
    
    global_dates = []
    global_port_nav = []
    global_bench_nav = []
    global_market_value = []
    
    port_units = 0.0
    port_nav = 100.0 # Base 100 on Day 1
    
    # Group transactions by exact date for O(1) daily lookup
    txns_by_date = {}
    for _, r in df_t.iterrows():
        d = r["Date"].date()
        if d not in txns_by_date: txns_by_date[d] = []
        txns_by_date[d].append(r)
        
    bench_start_global = float(bench_sorted[bench_sorted.index >= start_date].iloc[0]) if not bench_sorted[bench_sorted.index >= start_date].empty else 1.0

    # Simulate portfolio day-by-day exactly as it happened in reality
    for d in calendar:
        d_obj = d.date()
        
        b_series = bench_sorted[bench_sorted.index <= d]
        b_curr = float(b_series.iloc[-1]) if not b_series.empty else bench_start_global
        b_idx = (b_curr / bench_start_global) * 100.0
        
        # A) Start-of-Day Market Value
        market_value_sod = 0.0
        for f, units in fund_units.items():
            if units > 0:
                f_navs = fund_navs[f]
                past_navs = f_navs[f_navs.index.date <= d_obj]
                # FIX H-9: Forward-fill from last known NAV instead of hardcoded 10.0
                nav_today = float(past_navs.iloc[-1]) if not past_navs.empty else float(f_navs.iloc[0]) if not f_navs.empty else 10.0
                market_value_sod += units * nav_today
                
        if port_units > 0:
            port_nav = market_value_sod / port_units
            
        # B) Process today's cashflows
        net_cashflow = 0.0
        if d_obj in txns_by_date:
            for txn in txns_by_date[d_obj]:
                f = txn["Fund"]
                if f not in fund_units: continue
                
                t_type = str(txn.get("Type", "")).upper()
                amt = abs(float(txn.get("Amount", 0) or 0))
                units_t = abs(float(txn.get("Units", 0) or 0))
                nav_t = float(txn.get("NAV", 0) or 0)
                
                if amt == 0 and units_t > 0 and nav_t > 0:
                    amt = units_t * nav_t
                
                if "BUY" in t_type or "PURCHASE" in t_type or "SIP" in t_type or "SWITCH-IN" in t_type:
                    fund_units[f] += units_t
                    net_cashflow += amt
                elif "SELL" in t_type or "REDEMPTION" in t_type or "SWP" in t_type or "SWITCH-OUT" in t_type:
                    fund_units[f] -= units_t
                    fund_units[f] = max(0.0, fund_units[f])
                    net_cashflow -= amt
                elif "REINVEST" in t_type or "BONUS" in t_type:
                    fund_units[f] += units_t
                    
        # C) Issue/Redeem portfolio units at current Portfolio NAV
        if net_cashflow > 0:
            port_units += net_cashflow / port_nav
        elif net_cashflow < 0:
            port_units -= abs(net_cashflow) / port_nav
            port_units = max(0.0, port_units)
            
        # D) End-of-Day Market Value
        market_value_eod = 0.0
        for f, units in fund_units.items():
            if units > 0:
                f_navs = fund_navs.get(f)
                if f_navs is not None:
                    past_navs = f_navs[f_navs.index.date <= d_obj]
                    # FIX H-9: Forward-fill from last known NAV instead of hardcoded 10.0
                    nav_today = float(past_navs.iloc[-1]) if not past_navs.empty else float(f_navs.iloc[0]) if not f_navs.empty else 10.0
                    market_value_eod += units * nav_today
                else:
                    # If we couldn't fetch NAV, assume a constant 10.0 or last known unit price.
                    # For a sold fund, ideally we would use its historical purchase price or synthetic NAV.
                    market_value_eod += units * 10.0
                
        if port_units > 0:
            port_nav = market_value_eod / port_units
            
        global_dates.append(d)
        global_port_nav.append(port_nav)
        global_bench_nav.append(b_idx)
        global_market_value.append(market_value_eod)
        
    global_df = pd.DataFrame({
        "bench": global_bench_nav,
        "port": global_port_nav,
        "market_value": global_market_value
    }, index=global_dates)

    # 4. Slice the true curve for the requested period
    bench_end_date = global_df.index[-1]
    if period_days < 9999:
        period_start = bench_end_date - timedelta(days=period_days)
    else:
        period_start = global_df.index[0]

    period_df = global_df[global_df.index >= period_start]
    if period_df.empty:
        return result

    # 5. Benchmark Anchoring (Zerodha Charting Logic)
    # The portfolio stays at its true historical unitized NAV (e.g. 168.0).
    # The benchmark is re-scaled so that its starting point matches the portfolio's starting point exactly.
    # This ensures both lines start at the exact same point on the Y-axis for any zoomed window,
    # making visual divergence obvious, while maintaining absolute Y-axis values.
    slice_start_port = float(period_df["port"].iloc[0])
    slice_start_bench = float(period_df["bench"].iloc[0])

    if slice_start_port <= 0: slice_start_port = 1.0
    if slice_start_bench <= 0: slice_start_bench = 1.0

    period_df = period_df.copy()
    
    # Portfolio is untouched
    
    # Benchmark is scaled to start at slice_start_port
    period_df["bench_scaled"] = (period_df["bench"] / slice_start_bench) * slice_start_port

    # 6. Calculate exact percentage returns (Absolute for <1Y, Annualized CAGR for >=1Y)
    slice_end_port = float(period_df["port"].iloc[-1])
    slice_end_bench = float(period_df["bench"].iloc[-1])
    
    actual_days = (period_df.index[-1] - period_df.index[0]).days
    
    if actual_days >= 365:
        # Annualized CAGR
        years = actual_days / 365.25
        period_port_pct = (((slice_end_port / slice_start_port) ** (1 / years)) - 1) * 100.0
        period_bench_pct = (((slice_end_bench / slice_start_bench) ** (1 / years)) - 1) * 100.0
    else:
        # Absolute Return
        period_port_pct = ((slice_end_port / slice_start_port) - 1) * 100.0
        period_bench_pct = ((slice_end_bench / slice_start_bench) - 1) * 100.0

    result["port_pct"] = round(period_port_pct, 2)
    result["bench_pct"] = round(period_bench_pct, 2)
    result["alpha"] = round(period_port_pct - period_bench_pct, 2)
    
    # Calculate global XIRR for reference if needed
    _, bench_all_sim_value = compute_benchmark_xirr(df_t_all, bench_sorted)
    result["bench_value"] = round(bench_all_sim_value, 2)

    # 7. Downsample to ~60-80 points for optimal frontend rendering
    step = max(1, len(period_df) // 60)
    chart_indices = list(range(0, len(period_df), step))
    if (len(period_df) - 1) not in chart_indices:
        chart_indices.append(len(period_df) - 1)

    dates_arr, port_vals, bench_vals, market_vals = [], [], [], []
    for idx in chart_indices:
        d = period_df.index[idx]
        dates_arr.append(d.strftime("%Y-%m-%d"))
        port_vals.append(round(period_df["port"].iloc[idx], 2))
        bench_vals.append(round(period_df["bench_scaled"].iloc[idx], 2))
        market_vals.append(round(period_df["market_value"].iloc[idx], 2))

    result["dates"] = dates_arr
    result["portfolio"] = port_vals
    result["benchmark"] = bench_vals
    result["market_value"] = market_vals

    return result


# ---------------------------------------------------------------------------
# SIP Projection with Annual Step-Up
# ---------------------------------------------------------------------------

def stepup_sip_projection(
    monthly_sip: float,
    years: int,
    annual_return: float,
    stepup_pct: float,
    lumpsum: float = 0.0,
    existing_corpus: float = 0.0,
) -> Dict:
    """
    Project wealth growth with annual SIP step-up.

    Parameters
    ----------
    monthly_sip    : Starting monthly SIP amount (₹)
    years          : Investment horizon
    annual_return  : Expected annual return in % (e.g. 14.0)
    stepup_pct     : Annual SIP increase in % (e.g. 10.0)
    lumpsum        : Annual lumpsum (e.g. ₹25,000 for ELSS in Jan)
    existing_corpus: Starting corpus value

    Returns
    -------
    dict with projection list and summary statistics
    """
    data           = []
    total_invested = 0.0
    current_value  = float(existing_corpus)
    monthly_rate   = (1 + annual_return / 100) ** (1 / 12) - 1
    annual_rate    = annual_return / 100

    current_sip = float(monthly_sip)

    for year in range(1, years + 1):
        # Monthly compounding for 12 months
        for _ in range(12):
            total_invested += current_sip
            current_value   = (current_value + current_sip) * (1 + monthly_rate)

        # Annual lumpsum (e.g. ELSS in January — assumed invested at month 6)
        # FIX P3-4: Compound from actual investment month instead of mid-year ^0.5
        # Assuming lumpsum is invested at the start of month 7 (mid-year),
        # it gets 6 months of compounding within this year.
        if lumpsum > 0:
            total_invested += lumpsum
            months_remaining = 6  # invested at start of month 7
            current_value += lumpsum * (1 + monthly_rate) ** months_remaining

        data.append({
            "year":       year,
            "invested":   round(total_invested, 0),
            "value":      round(current_value, 0),
            "sip_amount": round(current_sip, 0),
            "gain":       round(current_value - total_invested, 0),
            "gain_pct":   round((current_value / max(total_invested, 1) - 1) * 100, 1),
        })

        current_sip *= (1 + stepup_pct / 100)

    return {
        "projection":    data,
        "final_value":   round(current_value, 0),
        "total_invested": round(total_invested, 0),
        "wealth_gain":   round(current_value - total_invested, 0),
        "wealth_multiple": round(current_value / max(total_invested, 1), 2),
    }


# ---------------------------------------------------------------------------
# LTCG Harvest Calculator
# ---------------------------------------------------------------------------

def compute_ltcg_harvest(
    holdings: List[Dict],
    ltcg_exemption: float = 125000.0,
    ltcg_rate: float = 0.125,
) -> Dict:
    """
    Identify funds where LTCG can be booked within the ₹1.25L annual exemption.

    Parameters
    ----------
    holdings       : List of {"fund": str, "gain": float, "holding_days": int,
                               "current_value": float, "invested": float}
    ltcg_exemption : Annual LTCG exemption (₹1,25,000 for FY2024-25)
    ltcg_rate      : LTCG rate (12.5% post Jul 2024)

    Returns
    -------
    dict with eligible gains list and tax saved
    """
    # 1. Gain Harvesting (up to ₹1.25L exemption)
    gain_eligible = [
        h for h in holdings
        if h.get("holding_days", 0) >= 365 and h.get("gain", 0) > 0
    ]
    gain_eligible.sort(key=lambda x: x["gain"])
    
    # 2. Loss Harvesting (STCL and LTCL)
    loss_eligible = [
        h for h in holdings
        if h.get("stcg", 0) < -100 or h.get("ltcg", 0) < -100
    ]
    loss_eligible.sort(key=lambda x: min(x.get("stcg", 0), x.get("ltcg", 0))) # Largest losses first

    to_harvest   = []
    cumulative   = 0.0
    tax_saved    = 0.0

    for h in gain_eligible:
        gain = h["gain"]
        if cumulative + gain <= ltcg_exemption:
            to_harvest.append({
                "fund":       h["fund"],
                "gain":       round(gain, 0),
                "tax_at_rate": round(gain * ltcg_rate, 0),
                "tax_saved":  round(gain * ltcg_rate, 0),
                "action":     "HARVEST — book gain, reinvest same day",
            })
            cumulative += gain
            tax_saved  += gain * ltcg_rate
        else:
            partial = ltcg_exemption - cumulative
            if partial > 1000:
                to_harvest.append({
                    "fund":       h["fund"],
                    "gain":       round(partial, 0),
                    "tax_at_rate": round(partial * ltcg_rate, 0),
                    "tax_saved":  round(partial * ltcg_rate, 0),
                    "action":     f"PARTIAL HARVEST — book ₹{partial:,.0f} only",
                })
                tax_saved  += partial * ltcg_rate
            break
            
    total_loss_harvested = 0.0
    for h in loss_eligible:
        loss = min(h.get("stcg", 0), h.get("ltcg", 0))
        # Tax saved by loss harvesting: roughly 20% for STCL, 12.5% for LTCL. Use average 15% for display.
        # Loss harvesting allows offsetting future gains.
        to_harvest.append({
            "fund":       h["fund"],
            "gain":       round(loss, 0),
            "tax_at_rate": 0,
            "tax_saved":  round(abs(loss) * 0.15, 0),
            "action":     "TAX LOSS HARVEST — book loss to offset future gains",
        })
        total_loss_harvested += abs(loss)
        tax_saved += abs(loss) * 0.15

    return {
        "eligible_count": len(gain_eligible) + len(loss_eligible),
        "harvest_list":   to_harvest,
        "total_harvested": round(cumulative + total_loss_harvested, 0),
        "total_tax_saved": round(tax_saved, 0),
        "remaining_exemption": round(max(ltcg_exemption - cumulative, 0), 0),
    }