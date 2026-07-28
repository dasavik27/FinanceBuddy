"""
core/tax_engine.py

Indian Income Tax Computation Engine (AY 2026-27 / FY 2025-26)
===============================================================
Implements both Old and New Regime tax computation including:
- Slab-based income tax on normal income
- Special rate capital gains tax (LTCG/STCG)
- Standard deductions, 80C/80D/80TTA deductions (Old Regime)
- Rebate u/s 87A
- Health & Education Cess (4%)
- Surcharge computation
- ITR type determination
"""

import json
import os
from typing import Optional
from datetime import datetime

# Load Tax Rules Configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "tax_rules.json")
with open(CONFIG_PATH, "r") as f:
    TAX_RULES = json.load(f)

def _convert_slabs(slabs_list):
    return [(limit if limit is not None else float('inf'), rate) for limit, rate in slabs_list]

NEW_REGIME_SLABS = _convert_slabs(TAX_RULES["slabs"]["new_regime"])
OLD_REGIME_SLABS = _convert_slabs(TAX_RULES["slabs"]["old_regime"])
OLD_REGIME_SENIOR_SLABS = _convert_slabs(TAX_RULES["slabs"]["old_regime_senior"])
OLD_REGIME_SUPER_SENIOR_SLABS = _convert_slabs(TAX_RULES["slabs"]["old_regime_super_senior"])
SURCHARGE_SLABS = _convert_slabs(TAX_RULES["surcharge_slabs"])

LTCG_EQUITY_RATE = TAX_RULES["capital_gains"]["ltcg_equity_rate"]
STCG_EQUITY_RATE = TAX_RULES["capital_gains"]["stcg_equity_rate"]
LTCG_OTHER_RATE = TAX_RULES["capital_gains"]["ltcg_other_rate"]
LTCG_EQUITY_EXEMPTION = TAX_RULES["capital_gains"]["ltcg_equity_exemption"]

CRYPTO_RATE = TAX_RULES["special_rates"]["crypto_rate"]
GAMING_RATE = TAX_RULES["special_rates"]["gaming_rate"]

CESS_RATE = TAX_RULES["cess_rate"]

NEW_REGIME_STD_DEDUCTION = TAX_RULES["deductions"]["std_deduction_new"]
OLD_REGIME_STD_DEDUCTION = TAX_RULES["deductions"]["std_deduction_old"]
DEDUCTION_80C_LIMIT = TAX_RULES["deductions"]["limit_80c"]
DEDUCTION_80CCD1B_LIMIT = TAX_RULES["deductions"]["limit_80ccd1b"]
DEDUCTION_80D_LIMIT_SELF = TAX_RULES["deductions"]["limit_80d_self"]
DEDUCTION_80D_LIMIT_PARENTS = TAX_RULES["deductions"]["limit_80d_parents"]
DEDUCTION_80TTA_LIMIT = TAX_RULES["deductions"]["limit_80tta"]
DEDUCTION_80TTB_LIMIT = TAX_RULES["deductions"]["limit_80ttb"]
DEDUCTION_PTAX_LIMIT = TAX_RULES["deductions"]["limit_ptax"]


NEW_REGIME_REBATE_LIMIT = TAX_RULES["rebates"]["new_regime_limit"]
NEW_REGIME_MAX_REBATE = TAX_RULES["rebates"]["new_regime_max_rebate"]
OLD_REGIME_REBATE_LIMIT = TAX_RULES["rebates"]["old_regime_limit"]
OLD_REGIME_MAX_REBATE = TAX_RULES["rebates"]["old_regime_max_rebate"]
# Current ITD position: 87A rebate is NOT allowed against special-rate income
# (111A STCG, 112/112A LTCG). Configurable for users who wish to model the older stance.
REBATE_ALLOW_ON_SPECIAL = TAX_RULES["rebates"].get("allow_on_special_income", False)
NEW_REGIME_MARGINAL_RELIEF = TAX_RULES["rebates"].get("new_regime_marginal_relief", True)

# Surcharge caps (Finance Act): surcharge on 111A/112/112A gains is capped at 15%,
# and the New Regime caps the overall surcharge at 25% (the 37% band does not apply).
SURCHARGE_CG_CAP_RATE = TAX_RULES.get("surcharge_cg_cap_rate", 0.15)
SURCHARGE_NEW_REGIME_MAX_RATE = TAX_RULES.get("surcharge_new_regime_max_rate", 0.25)
SURCHARGE_MARGINAL_RELIEF = TAX_RULES.get("surcharge_marginal_relief", True)

# Grandfathering cut-off for Section 112A (FMV as on 31 Jan 2018).
GRANDFATHER_DATE = TAX_RULES["capital_gains"].get("grandfather_date", "2018-01-31")

# Section 50AA specified-fund cut-off: units purchased on/after this date are always
# taxed at slab rates regardless of holding period.
DEBT_REGIME_CUTOFF = TAX_RULES["capital_gains"].get("debt_regime_cutoff", "2023-04-01")

# 80D sub-limits and 80CCD(1) salary cap
DEDUCTION_80D_LIMIT_SELF_SENIOR = TAX_RULES["deductions"].get("limit_80d_self_senior", 50000)
DEDUCTION_80D_LIMIT_PREVENTIVE = TAX_RULES["deductions"].get("limit_80d_preventive", 5000)
DEDUCTION_80CCD1_SALARY_PCT = TAX_RULES["deductions"].get("limit_80ccd1_salary_pct", 0.10)

INTEREST_234 = TAX_RULES.get("interest_234", {})


def _safe_float(val) -> float:
    """Safely convert a value to float, returning 0.0 on failure."""
    try:
        return float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _compute_slab_tax(income: float, slabs: list) -> float:
    """Compute tax using progressive slab rates."""
    tax = 0.0
    prev_limit = 0
    for limit, rate in slabs:
        if income <= prev_limit:
            break
        taxable_in_slab = min(income, limit) - prev_limit
        tax += taxable_in_slab * rate
        prev_limit = limit
    return tax


def _compute_surcharge(tax: float, total_income: float) -> float:
    """Compute surcharge based on total income (flat, no caps — kept for callers/tests)."""
    for limit, rate in SURCHARGE_SLABS:
        if total_income <= limit:
            return tax * rate
    return tax * SURCHARGE_SLABS[-1][1]


def _surcharge_rate(total_income: float, regime: str) -> float:
    """Applicable surcharge rate for a given total income, honouring the New Regime 25% cap."""
    rate = SURCHARGE_SLABS[-1][1]
    for limit, r in SURCHARGE_SLABS:
        if total_income <= limit:
            rate = r
            break
    if regime == "new":
        rate = min(rate, SURCHARGE_NEW_REGIME_MAX_RATE)
    return rate


def _surcharge_threshold_below(total_income: float) -> float:
    """Highest surcharge threshold (50L/1cr/2cr/5cr) strictly below total_income."""
    below = 0.0
    for limit, _ in SURCHARGE_SLABS:
        if limit is not None and total_income > limit:
            below = limit
    return below


def _compute_surcharge_with_caps(normal_and_special_tax: float, cg_capped_tax: float,
                                 total_income: float, regime: str) -> dict:
    """
    Surcharge with the 15% cap on 111A/112/112A gains and marginal relief.

    Args:
        normal_and_special_tax: tax on income surcharged at the full applicable rate
            (slab tax + crypto/gaming flat tax).
        cg_capped_tax: tax on 111A/112/112A gains, surcharged at min(rate, 15%).
        total_income: income used to pick the surcharge slab.
        regime: "old" or "new".
    """
    base_rate = _surcharge_rate(total_income, regime)
    if base_rate <= 0:
        return {"surcharge": 0.0, "rate": 0.0, "cg_rate": 0.0, "marginal_relief": 0.0}

    cg_rate = min(base_rate, SURCHARGE_CG_CAP_RATE)
    surcharge = normal_and_special_tax * base_rate + cg_capped_tax * cg_rate

    marginal_relief = 0.0
    if SURCHARGE_MARGINAL_RELIEF:
        threshold = _surcharge_threshold_below(total_income)
        excess = max(0.0, total_income - threshold)
        total_tax_pre = normal_and_special_tax + cg_capped_tax
        # Approximate the pre-surcharge tax at the threshold by removing tax on the
        # marginal income above it (taxed at the 30% top slab — conservative: least relief).
        tax_on_excess = excess * 0.30
        tax_at_threshold = max(0.0, total_tax_pre - tax_on_excess)
        liability_with_surcharge = total_tax_pre + surcharge
        max_liability = tax_at_threshold + excess
        if liability_with_surcharge > max_liability:
            marginal_relief = liability_with_surcharge - max_liability
            surcharge = max(0.0, surcharge - marginal_relief)

    return {"surcharge": surcharge, "rate": base_rate, "cg_rate": cg_rate,
            "marginal_relief": marginal_relief}


def _parse_iso(val) -> Optional[datetime]:
    """Parse an ISO (YYYY-MM-DD) or DD/MM/YYYY date string; return None on failure."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            continue
    return None


def _months_ceil(start: datetime, end: datetime) -> int:
    """Whole months between two dates, counting any part-month as a full month (Sec 234 convention)."""
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day > start.day:
        months += 1
    return max(0, months)


def _round_down_100(amount: float) -> float:
    """Interest u/s 234 is charged on tax rounded down to the nearest ₹100."""
    return (int(amount) // 100) * 100


def _grandfathered_gain(trade: dict) -> float:
    """
    Effective LTCG for a Section 112A trade, applying 31-Jan-2018 grandfathering
    ONLY when the acquisition date is known to be before the cut-off. Otherwise the
    already-computed gain is returned unchanged (conservative — never understates gain
    for post-2018 lots where AIS may still carry an FMV figure).
    """
    if trade.get("type") != "LTCG":
        return _safe_float(trade.get("gain", 0))

    fmv = _safe_float(trade.get("fmv_31jan2018", trade.get("fair_market_value", 0)))
    acq = _parse_iso(trade.get("acquired_date") or trade.get("purchase_date"))
    cutoff = _parse_iso(GRANDFATHER_DATE)

    if fmv > 0 and acq is not None and cutoff is not None and acq <= cutoff:
        sale = _safe_float(trade.get("consideration", 0))
        cost = _safe_float(trade.get("cost", 0))
        # Cost of acquisition = higher of (actual cost) and (lower of FMV and sale value).
        gf_cost = max(cost, min(fmv, sale))
        return sale - gf_cost
    return _safe_float(trade.get("gain", 0))


def _compute_80d(deductions: dict, age: int) -> float:
    """
    Section 80D with sub-limits. If the caller supplies a structured '80d_detail'
    dict, the ₹5,000 preventive-checkup sub-cap and the self/parents & senior limits
    are enforced. Otherwise falls back to a flat cap (backward compatible).
    """
    detail = deductions.get("80d_detail")
    if not isinstance(detail, dict):
        # Backward-compatible flat cap.
        self_cap = DEDUCTION_80D_LIMIT_SELF_SENIOR if age >= 60 else DEDUCTION_80D_LIMIT_SELF
        return min(_safe_float(deductions.get("80d", 0)), self_cap + DEDUCTION_80D_LIMIT_PARENTS)

    def _bucket(premium, preventive, medical, senior):
        cap = DEDUCTION_80D_LIMIT_SELF_SENIOR if senior else DEDUCTION_80D_LIMIT_SELF
        # Preventive checkup is capped at ₹5,000 within the overall bucket cap.
        prev = min(_safe_float(preventive), DEDUCTION_80D_LIMIT_PREVENTIVE)
        # Medical expenditure allowed only for senior citizens (in lieu of insurance).
        med = _safe_float(medical) if senior else 0.0
        return min(_safe_float(premium) + prev + med, cap)

    self_senior = age >= 60 or bool(detail.get("self_senior"))
    parents_senior = bool(detail.get("parents_senior"))

    self_amt = _bucket(detail.get("self_premium", 0), detail.get("self_preventive", 0),
                       detail.get("self_medical", 0), self_senior)
    parents_amt = _bucket(detail.get("parents_premium", 0), detail.get("parents_preventive", 0),
                          detail.get("parents_medical", 0), parents_senior)
    return self_amt + parents_amt


def _compute_234_interest(total_tax: float, tds: float, advance_tax: float,
                          overrides: dict, age: int, has_business: bool) -> dict:
    """
    Interest u/s 234A (late filing), 234B (advance-tax default) and a simplified 234C
    (deferment of advance-tax instalments). All amounts default to 0 when tax is fully
    covered by TDS or the return is filed on time.
    """
    rules = INTEREST_234
    if not rules:
        return {"i234a": 0.0, "i234b": 0.0, "i234c": 0.0, "total": 0.0}

    monthly = rules.get("monthly_rate", 0.01)
    threshold_pct = rules.get("advance_tax_threshold_pct", 0.90)
    min_liability = rules.get("min_liability_for_advance_tax", 10000)

    due_date = _parse_iso(overrides.get("filing_due_date") or rules.get("due_date"))
    ay_start = _parse_iso(rules.get("ay_start"))
    filing_date = _parse_iso(overrides.get("filing_date")) or due_date

    assessed_tax = max(0.0, total_tax - tds)          # tax net of TDS/TCS
    net_payable = max(0.0, total_tax - tds - advance_tax)

    i234a = i234b = i234c = 0.0

    # 234A — return filed after the due date with tax still payable.
    if due_date and filing_date and filing_date > due_date and net_payable > 0:
        months = _months_ceil(due_date, filing_date)
        i234a = _round_down_100(net_payable) * monthly * months

    # Senior citizens with no business income are exempt from 234B/234C advance-tax interest.
    senior_exempt = (rules.get("senior_no_business_exempt_234b_234c", True)
                     and age >= 60 and not has_business)

    if assessed_tax >= min_liability and not senior_exempt:
        # 234B — advance tax paid is less than 90% of assessed tax.
        if advance_tax < threshold_pct * assessed_tax and ay_start and filing_date:
            shortfall = max(0.0, assessed_tax - advance_tax)
            months = _months_ceil(ay_start, filing_date)
            i234b = _round_down_100(shortfall) * monthly * months

        # 234C — deferment of instalments. Uses per-instalment data when provided,
        # otherwise assumes nothing was paid by each due date (worst case).
        installments = overrides.get("advance_tax_installments") or {}
        schedule = [("q1", 0.15, 3), ("q2", 0.45, 3), ("q3", 0.75, 3), ("q4", 1.00, 1)]
        base = assessed_tax
        for key, due_pct, months in schedule:
            paid = _safe_float(installments.get(key, 0))
            required = due_pct * base
            shortfall = max(0.0, required - paid)
            i234c += _round_down_100(shortfall) * monthly * months

    total = i234a + i234b + i234c
    return {"i234a": round(i234a, 0), "i234b": round(i234b, 0),
            "i234c": round(i234c, 0), "total": round(total, 0)}


def compute_tax(ais_data: dict, regime: str = "new", overrides: Optional[dict] = None) -> dict:
    """
    Compute complete income tax based on parsed AIS data.
    
    Args:
        ais_data: Parsed AIS data from ais_parser.parse_ais_pdf()
        regime: "new" or "old"
        overrides: User-provided overrides (deductions, bf_losses, etc)
    
    Returns:
        Complete tax computation result
    """
    if overrides is None:
        overrides = {}
        
    deductions = overrides.get("deductions", {})
    bf_losses = overrides.get("bf_losses", {})
    
    # ── 0. Determine Age & Senior Citizen Status ───────────────────────
    personal_info = ais_data.get("personal", {})
    dob_str = personal_info.get("dob")
    age = 30 # default
    if dob_str:
        try:
            dob_date = datetime.strptime(dob_str, "%d/%m/%Y")
            # Calculate age as of March 31, 2026 (end of FY 2025-26)
            fy_end = datetime(2026, 3, 31)
            age = fy_end.year - dob_date.year - ((fy_end.month, fy_end.day) < (dob_date.month, dob_date.day))
        except ValueError:
            pass
            
    # Dynamically adjust OLD_REGIME_SLABS based on age
    effective_old_slabs = list(OLD_REGIME_SLABS)
    if regime == "old":
        if age >= 80:
            effective_old_slabs = OLD_REGIME_SUPER_SENIOR_SLABS
        elif age >= 60:
            effective_old_slabs = OLD_REGIME_SENIOR_SLABS
    
    # ── 1. Income from Salary ──────────────────────────────────────────
    salary_annexure = ais_data.get("salary_annexure", {})
    salary_data = ais_data.get("salary", {})
    
    gross_salary = salary_annexure.get("gross_salary", 0) or salary_data.get("gross", 0)
    std_deduction = NEW_REGIME_STD_DEDUCTION if regime == "new" else OLD_REGIME_STD_DEDUCTION
    
    # Sec 10 Allowance Exemptions & Sec 16 deductions (applied within the Salary head, NOT Chapter VI-A)
    # These reduce Gross Salary to arrive at "Income chargeable under Salaries" — matching Schedule S in ITR.
    if regime == "old":
        sec10_hra    = _safe_float(deductions.get("hra", 0))
        sec10_lta    = _safe_float(deductions.get("lta", 0))
        sec10_other  = _safe_float(deductions.get("sec10_other", 0))
        sec16_ptax   = min(_safe_float(deductions.get("ptax", 0)), DEDUCTION_PTAX_LIMIT)
    else:
        # In New Regime, these exemptions are not allowed
        sec10_hra = sec10_lta = sec10_other = sec16_ptax = 0.0
    
    total_sec10_sec16 = sec10_hra + sec10_lta + sec10_other + sec16_ptax
    net_salary = max(0, gross_salary - std_deduction - total_sec10_sec16)
    
    # ── 2. Income from Other Sources ───────────────────────────────────
    dividends = ais_data.get("dividends", [])
    total_dividends = sum(d.get("amount", 0) for d in dividends)
    
    interest_savings = ais_data.get("interest_savings", [])
    total_savings_interest = sum(i.get("amount", 0) for i in interest_savings)
    
    interest_deposits = ais_data.get("interest_deposits", [])
    total_fd_interest = sum(i.get("amount", 0) for i in interest_deposits)
    
    interest_others = ais_data.get("interest_others", [])
    total_other_interest = sum(i.get("amount", 0) for i in interest_others)
    
    foreign_interest = _safe_float(overrides.get("foreign_interest", 0))
    
    total_other_sources = total_dividends + total_savings_interest + total_fd_interest + total_other_interest + foreign_interest
    
    misc_income = ais_data.get("misc_income", [])
    total_misc_income = sum(i.get("amount", 0) for i in misc_income)
    
    business_income = overrides.get("business_income", {})
    revenue_44ada = _safe_float(business_income.get("revenue_44ada", 0))
    revenue_44ad = _safe_float(business_income.get("revenue_44ad", 0))
    
    # Presumptive profits
    profit_44ada = revenue_44ada * TAX_RULES["presumptive_business"]["section_44ada_profit_rate"]
    profit_44ad = revenue_44ad * TAX_RULES["presumptive_business"]["section_44ad_profit_rate"]
    total_business_profit = profit_44ada + profit_44ad
    
    crypto_income = _safe_float(overrides.get("crypto_income", 0))
    gaming_income = _safe_float(overrides.get("gaming_income", 0))
    
    # ── 3. Capital Gains Computation ───────────────────────────────────
    cg_equity = ais_data.get("capital_gains_equity", [])
    cg_mf_equity = ais_data.get("capital_gains_mf_equity", [])
    cg_mf_other = ais_data.get("capital_gains_mf_other", [])
    
    cg_real_estate = ais_data.get("cg_real_estate", [])
    cg_unlisted = ais_data.get("cg_unlisted", [])
    cg_bonds_gold = ais_data.get("cg_bonds_gold", [])
    
    # Equity LTCG (Listed shares + Equity MF) — apply Section 112A grandfathering
    # (FMV as on 31-Jan-2018) per-trade where the acquisition date is known.
    equity_ltcg_trades = [t for t in cg_equity if t.get("type") == "LTCG"] + \
                         [t for t in cg_mf_equity if t.get("type") == "LTCG"]
    ltcg_equity_raw = sum(_safe_float(t.get("gain", 0)) for t in equity_ltcg_trades)
    ltcg_equity = sum(_grandfathered_gain(t) for t in equity_ltcg_trades)
    grandfather_benefit = ltcg_equity_raw - ltcg_equity  # >0 when grandfathering reduces gain

    # Equity STCG
    stcg_equity = sum(t.get("gain", 0) for t in cg_equity if t.get("type") == "STCG")
    stcg_equity += sum(t.get("gain", 0) for t in cg_mf_equity if t.get("type") == "STCG")

    # Other (Debt/Non-Equity/RealEstate/Unlisted/Bonds/Gold) LTCG/STCG — treated differently
    # LTCG on these is usually 12.5% (Budget 2024 for all assets without indexation)
    # STCG on these is added to normal income (slab rates)

    # Let's combine all "Other" assets
    other_assets = cg_mf_other + cg_real_estate + cg_unlisted + cg_bonds_gold

    # Section 50AA: units of a "specified mutual fund" (debt-oriented) acquired on/after
    # 01-Apr-2023 are ALWAYS taxed at slab rates, regardless of holding period. Such trades
    # are flagged (by the broker parser or by acquisition date) and pulled out here so they
    # never receive the 12.5% LTCG treatment.
    def _is_slab_fund(t):
        if t.get("slab_taxed"):
            return True
        acq = _parse_iso(t.get("acquired_date") or t.get("purchase_date"))
        cutoff = _parse_iso(DEBT_REGIME_CUTOFF)
        return bool(t.get("is_debt") and acq is not None and cutoff is not None and acq >= cutoff)

    slab_fund_assets = [t for t in other_assets if _is_slab_fund(t)]
    non_slab_assets = [t for t in other_assets if not _is_slab_fund(t)]

    ltcg_other = sum(t.get("gain", 0) for t in non_slab_assets if t.get("type") == "LTCG")
    stcg_other = sum(t.get("gain", 0) for t in non_slab_assets if t.get("type") == "STCG")
    # Specified-fund gains flow into normal income at slab rates (losses are not netted
    # against salary here — only positive gains are added).
    slab_taxed_cg = max(0.0, sum(_safe_float(t.get("gain", 0)) for t in slab_fund_assets))

    # Direct capital gains overrides (e.g. when AIS lacks cost basis or user overrides)
    cg_overrides = overrides.get("capital_gains", {})
    if "ltcg_other" in cg_overrides and cg_overrides["ltcg_other"] is not None:
        ltcg_other = _safe_float(cg_overrides["ltcg_other"])
    if "stcg_equity" in cg_overrides and cg_overrides["stcg_equity"] is not None:
        stcg_equity = _safe_float(cg_overrides["stcg_equity"])
    if "ltcg_equity" in cg_overrides and cg_overrides["ltcg_equity"] is not None:
        ltcg_equity = _safe_float(cg_overrides["ltcg_equity"])
    if "stcg_other" in cg_overrides and cg_overrides["stcg_other"] is not None:
        stcg_other = _safe_float(cg_overrides["stcg_other"])
    
    # Apply Brought Forward (B/F) Losses
    # STCL can offset STCG or LTCG. LTCL can only offset LTCG.
    bf_stcl = abs(_safe_float(bf_losses.get("stcl", 0)))
    bf_ltcl = abs(_safe_float(bf_losses.get("ltcl", 0)))
    
    # Offset LTCL against LTCG (starting with equity, then other)
    if bf_ltcl > 0:
        if ltcg_equity >= bf_ltcl:
            ltcg_equity -= bf_ltcl
            bf_ltcl = 0
        else:
            bf_ltcl -= ltcg_equity
            ltcg_equity = 0
            ltcg_other = max(0, ltcg_other - bf_ltcl)
            
    # Offset STCL against STCG, then LTCG
    if bf_stcl > 0:
        if stcg_equity >= bf_stcl:
            stcg_equity -= bf_stcl
            bf_stcl = 0
        else:
            bf_stcl -= stcg_equity
            stcg_equity = 0
            if stcg_other >= bf_stcl:
                stcg_other -= bf_stcl
                bf_stcl = 0
            else:
                bf_stcl -= stcg_other
                stcg_other = 0
                if ltcg_equity >= bf_stcl:
                    ltcg_equity -= bf_stcl
                    bf_stcl = 0
                else:
                    bf_stcl -= ltcg_equity
                    ltcg_equity = 0
                    ltcg_other = max(0, ltcg_other - bf_stcl)
    
    total_capital_gains = ltcg_equity + stcg_equity + ltcg_other + stcg_other + slab_taxed_cg
    # total_special_rate excludes stcg_other and slab-taxed gains (which flow via slab into normal income)
    total_cg_special_rate = ltcg_equity + stcg_equity + ltcg_other
    
    # ── 4. Tax on Capital Gains (Special Rates) ────────────────────────
    # LTCG Equity: 12.5% above ₹1.25L exemption
    ltcg_equity_taxable = max(0, ltcg_equity - LTCG_EQUITY_EXEMPTION)
    tax_ltcg_equity = ltcg_equity_taxable * LTCG_EQUITY_RATE
    
    # STCG Equity: 20%
    stcg_equity_taxable = max(0, stcg_equity)
    tax_stcg_equity = stcg_equity_taxable * STCG_EQUITY_RATE
    
    # Other LTCG (Real Estate, Gold, Bonds, Unlisted): 12.5% without exemption
    tax_ltcg_other = max(0, ltcg_other) * LTCG_OTHER_RATE
    
    # Other STCG + Section 50AA specified-fund gains: taxed at slab rate (included in normal income)
    slab_rate_cg = max(0, stcg_other) + slab_taxed_cg
    
    total_cg_tax = tax_ltcg_equity + tax_stcg_equity + tax_ltcg_other
    
    # ── 5. Gross Total Income ──────────────────────────────────────────
    # Normal income (taxed at slab rates)
    normal_income = net_salary + total_other_sources + slab_rate_cg + total_misc_income + total_business_profit
    
    # Gross total income (for display)
    gross_income = net_salary + total_other_sources + total_capital_gains + total_misc_income + total_business_profit + crypto_income + gaming_income
    
    # ── 6. Deductions (Old Regime Only) ────────────────────────────────
    total_deductions = 0
    deduction_details = {}
    
    if regime == "old":
        # 80C, 80CCC and 80CCD(1) are subject to combined limit of 1.5L under Sec 80CCE
        val_80c = _safe_float(deductions.get("80c", 0))
        val_80ccc = _safe_float(deductions.get("80ccc", 0))
        val_80ccd1 = _safe_float(deductions.get("80ccd1", 0))

        # Section 80CCD(1) is separately capped at 10% of salary for the salaried
        # (before the combined 80CCE ceiling). Gross salary is used as an upper bound
        # in the absence of the basic+DA breakup.
        ccd1_salary_cap = DEDUCTION_80CCD1_SALARY_PCT * _safe_float(gross_salary)
        if ccd1_salary_cap > 0:
            val_80ccd1 = min(val_80ccd1, ccd1_salary_cap)

        # Apply combined Section 80CCE limit
        total_80cce = min(val_80c + val_80ccc + val_80ccd1, DEDUCTION_80C_LIMIT)
        
        # Pro-rata attribution for detailed view if combined limit hits
        total_vals = val_80c + val_80ccc + val_80ccd1
        if total_vals > 0:
            deduction_details["80c"] = total_80cce * (val_80c / total_vals)
            deduction_details["80ccc"] = total_80cce * (val_80ccc / total_vals)
            deduction_details["80ccd1"] = total_80cce * (val_80ccd1 / total_vals)
        else:
            deduction_details["80c"] = 0.0
            deduction_details["80ccc"] = 0.0
            deduction_details["80ccd1"] = 0.0
            
        total_deductions += total_80cce
        
        # 80CCD(1B) - Additional NPS
        ded_80ccd1b = min(_safe_float(deductions.get("80ccd1b", 0)), DEDUCTION_80CCD1B_LIMIT)
        deduction_details["80ccd1b"] = ded_80ccd1b
        total_deductions += ded_80ccd1b
        
    # 80CCD(2) - Employer NPS (Allowed in BOTH Old and New Regimes)
    ded_80ccd2 = _safe_float(deductions.get("80ccd2", 0)) # Limit usually 10% basic salary
    deduction_details["80ccd2"] = ded_80ccd2  # always output, even if 0
    if ded_80ccd2 > 0:
        total_deductions += ded_80ccd2
        
    if regime == "old":
        
        # 80D - Medical Insurance (with preventive/senior sub-limits when detail supplied)
        ded_80d = _compute_80d(deductions, age)
        deduction_details["80d"] = ded_80d
        total_deductions += ded_80d
        
        # 80TTA/80TTB - Savings / FD Interest (auto-computed)
        if age >= 60:
            ded_80ttb = min(total_savings_interest + total_fd_interest, DEDUCTION_80TTB_LIMIT)
            deduction_details["80ttb"] = ded_80ttb
            total_deductions += ded_80ttb
        else:
            ded_80tta = min(total_savings_interest, DEDUCTION_80TTA_LIMIT)
            deduction_details["80tta"] = ded_80tta
            total_deductions += ded_80tta
        
        # Professional Tax (Sec 16(iii)) — now handled in salary head above
        # HRA, LTA, Sec10 other — now handled in salary head above
        # (kept as pass-through so deduction_details keys remain backward-compatible)
        pass
            
    # Other Sec 10 Exemptions (Gratuity, Leave Encashment, VRS)
    # NOTE: Only applied in Old Regime via the block above. In New Regime these are generally taxable.
        
    if regime == "old":
        
        # Home Loan Interest (Sec 24b)
        ded_24b = _safe_float(deductions.get("24b", 0))
        deduction_details["24b"] = ded_24b
        total_deductions += ded_24b
        
        # Donations (Sec 80G, 80GGA, 80GGC)
        ded_80g = _safe_float(deductions.get("80g", 0))
        deduction_details["80g"] = ded_80g
        total_deductions += ded_80g
        
        ded_80gga = _safe_float(deductions.get("80gga", 0))
        deduction_details["80gga"] = ded_80gga
        total_deductions += ded_80gga
        
        ded_80ggc = _safe_float(deductions.get("80ggc", 0))
        deduction_details["80ggc"] = ded_80ggc
        total_deductions += ded_80ggc

        # Medical & Disabilities (80DD, 80U)
        ded_80dd = _safe_float(deductions.get("80dd", 0))
        deduction_details["80dd"] = ded_80dd
        total_deductions += ded_80dd
        
        ded_80u = _safe_float(deductions.get("80u", 0))
        deduction_details["80u"] = ded_80u
        total_deductions += ded_80u

        # Education Loan (80E)
        ded_80e = _safe_float(deductions.get("80e", 0))
        deduction_details["80e"] = ded_80e
        total_deductions += ded_80e
        
        # Other deductions
        ded_other = _safe_float(deductions.get("other", 0))
        deduction_details["other"] = ded_other
        total_deductions += ded_other
    
    # ── 7. Taxable Income ──────────────────────────────────────────────
    taxable_normal_income = max(0, normal_income - total_deductions)
    
    # ── 8. Tax on Normal Income ────────────────────────────────────────
    slabs = NEW_REGIME_SLABS if regime == "new" else effective_old_slabs
    tax_on_normal = _compute_slab_tax(taxable_normal_income, slabs)
    
    # ── 9. Rebate u/s 87A ─────────────────────────────────────────────
    # Rebate is checked against TOTAL income, not just normal income.
    total_taxable_income = taxable_normal_income + ltcg_equity + stcg_equity + ltcg_other
    rebate = 0
    rebate_limit = 0
    
    if regime == "new" and total_taxable_income <= NEW_REGIME_REBATE_LIMIT:
        rebate_limit = NEW_REGIME_MAX_REBATE
    elif regime == "old" and total_taxable_income <= OLD_REGIME_REBATE_LIMIT:
        rebate_limit = OLD_REGIME_MAX_REBATE
        
    # Rebate can be applied against Normal Tax, STCG, and LTCG Other (Sec 112). 
    # It CANNOT be applied against LTCG Equity (Sec 112A).
    tax_after_rebate = tax_on_normal
    tax_ltcg_other_after_rebate = tax_ltcg_other
    tax_stcg_equity_after_rebate = tax_stcg_equity
    
    if rebate_limit > 0:
        # 1. Offset against Normal Tax
        used_rebate = min(tax_after_rebate, rebate_limit)
        tax_after_rebate -= used_rebate
        rebate += used_rebate
        rebate_limit -= used_rebate

        # 2 & 3. Offset against special-rate income (STCG 111A / LTCG 112 Other).
        # Current ITD position DISALLOWS rebate against special-rate income; this is
        # gated behind REBATE_ALLOW_ON_SPECIAL and only ever applied in the Old Regime.
        if REBATE_ALLOW_ON_SPECIAL and regime == "old":
            if rebate_limit > 0:
                used_rebate = min(tax_stcg_equity_after_rebate, rebate_limit)
                tax_stcg_equity_after_rebate -= used_rebate
                rebate += used_rebate
                rebate_limit -= used_rebate

            if rebate_limit > 0:
                used_rebate = min(tax_ltcg_other_after_rebate, rebate_limit)
                tax_ltcg_other_after_rebate -= used_rebate
                rebate += used_rebate
                rebate_limit -= used_rebate

    # New Regime marginal relief near the ₹12L rebate threshold: total tax on normal income
    # cannot exceed the income earned above the rebate limit.
    rebate_marginal_relief = 0.0
    if (regime == "new" and NEW_REGIME_MARGINAL_RELIEF
            and total_taxable_income > NEW_REGIME_REBATE_LIMIT):
        excess_over_limit = total_taxable_income - NEW_REGIME_REBATE_LIMIT
        if tax_after_rebate > excess_over_limit:
            rebate_marginal_relief = tax_after_rebate - excess_over_limit
            rebate += rebate_marginal_relief
            tax_after_rebate = excess_over_limit

    # Round each tax line to the nearest rupee BEFORE summing — this mirrors the ITD
    # e-filing utility (Schedule SI lines and the normal-rate tax are each rounded), so
    # the reconciliation against a filed ITR matches to the rupee instead of drifting by ₹1.
    tax_after_rebate = round(tax_after_rebate)
    tax_ltcg_equity = round(tax_ltcg_equity)
    tax_stcg_equity_after_rebate = round(tax_stcg_equity_after_rebate)
    tax_ltcg_other_after_rebate = round(tax_ltcg_other_after_rebate)

    # Recompute total CG tax after rebate (from rounded components)
    total_cg_tax = tax_ltcg_equity + tax_stcg_equity_after_rebate + tax_ltcg_other_after_rebate

    # ── 10. Total Tax Before Cess ──────────────────────────────────────
    tax_crypto = round(crypto_income * CRYPTO_RATE)
    tax_gaming = round(gaming_income * GAMING_RATE)
    total_special_tax = tax_crypto + tax_gaming
    total_tax_before_cess = tax_after_rebate + total_cg_tax + total_special_tax
    
    # ── 11. Surcharge (with 15% CG cap, New-Regime 25% ceiling, marginal relief) ──
    total_income_for_surcharge = taxable_normal_income + ltcg_equity + stcg_equity + ltcg_other + crypto_income + gaming_income
    # Tax surcharged at the full applicable rate: slab tax (post-rebate) + crypto/gaming.
    normal_and_special_tax = tax_after_rebate + total_special_tax
    # Tax surcharged at min(rate, 15%): 111A STCG + 112/112A LTCG (post-rebate).
    cg_capped_tax = total_cg_tax
    surcharge_info = _compute_surcharge_with_caps(
        normal_and_special_tax, cg_capped_tax, total_income_for_surcharge, regime
    )
    surcharge = surcharge_info["surcharge"]
    
    # ── 12. Cess ───────────────────────────────────────────────────────
    cess = (total_tax_before_cess + surcharge) * CESS_RATE
    
    # ── 13. Total Tax Liability ────────────────────────────────────────
    total_tax = round(total_tax_before_cess + surcharge + cess, 0)
    
    # ── 14. TDS & Advance Tax Paid ─────────────────────────────────────
    tds_paid = overrides.get("manual_tds")
    if tds_paid is None:
        tds_paid = ais_data.get("tds_total", ais_data.get("salary", {}).get("tds_deducted", 0))
    advance_tax = sum(p.get("total", 0) for p in ais_data.get("tax_payments", []))
    
    manual_tax_paid = _safe_float(overrides.get("manual_taxes", 0))
    total_tax_paid = tds_paid + advance_tax + manual_tax_paid

    # ── 15. Interest u/s 234A / 234B / 234C ────────────────────────────
    has_business = (total_business_profit > 0) or bool(business_income)
    interest_234 = _compute_234_interest(
        total_tax, tds_paid, advance_tax, overrides, age, has_business
    )
    aggregate_liability = total_tax + interest_234["total"]

    # ── 16. Refund or Due ──────────────────────────────────────────────
    exact_refund_or_due = total_tax_paid - aggregate_liability  # Positive = refund, negative = due
    # Section 288B: Round refund or tax payable to nearest ₹10
    refund_or_due = round(exact_refund_or_due / 10.0) * 10.0
    
    # ── 16. ITR Type Determination ─────────────────────────────────────
    has_cg = total_capital_gains != 0
    has_equity_sales = len(cg_equity) > 0
    itr_type = "ITR-2" if (has_cg or has_equity_sales) else "ITR-1"
    
    # Dynamically compute AY from FY
    fy = ais_data.get("fy", "2025-26")
    ay = "2026-27" # default
    try:
        parts = fy.split("-")
        if len(parts) == 2:
            start_yr = int(parts[0])
            end_yr_str = parts[1]
            ay_start = start_yr + 1
            if len(end_yr_str) == 2:
                ay_end = int(end_yr_str) + 1
                ay = f"{ay_start}-{ay_end:02d}"
            elif len(end_yr_str) == 4:
                ay_end = int(end_yr_str) + 1
                ay = f"{ay_start}-{ay_end}"
    except Exception:
        pass
    
    return {
        "regime": regime,
        "fy": fy,
        "ay": ay,
        "itr_type": itr_type,
        "personal": ais_data.get("personal", {}),
        
        # Income Heads
        "income_heads": {
            "salary": {
                "gross": round(gross_salary, 0),
                "std_deduction": std_deduction,
                "sec10_hra": round(sec10_hra, 0),
                "sec10_lta": round(sec10_lta, 0),
                "sec10_other": round(sec10_other, 0),
                "sec16_ptax": round(sec16_ptax, 0),
                "total_sec10_sec16": round(total_sec10_sec16, 0),
                "net": round(net_salary, 0),
                "employer": ais_data.get("salary", {}).get("employer", ""),
            },
            "capital_gains": {
                "ltcg_equity": round(ltcg_equity, 0),
                "stcg_equity": round(stcg_equity, 0),
                "ltcg_other": round(ltcg_other, 0),
                "stcg_other": round(stcg_other, 0),
                "slab_taxed_cg": round(slab_taxed_cg, 0),
                "grandfather_benefit": round(grandfather_benefit, 0),
                "total": round(total_capital_gains, 0),
                # total_special_rate excludes stcg_other (at slab rates) — use this for CG income display
                "total_special_rate": round(total_cg_special_rate, 0),
                "ltcg_equity_exemption": LTCG_EQUITY_EXEMPTION,
                "ltcg_equity_taxable": round(ltcg_equity_taxable, 0),
            },
            "other_sources": {
                "dividends": round(total_dividends, 0),
                "savings_interest": round(total_savings_interest, 0),
                "fd_interest": round(total_fd_interest, 0),
                "other_interest": round(total_other_interest, 0),
                "foreign_interest": round(foreign_interest, 0),
                "total": round(total_other_sources, 0),
            },
            "business": {
                "revenue_44ada": round(revenue_44ada, 0),
                "profit_44ada": round(profit_44ada, 0),
                "revenue_44ad": round(revenue_44ad, 0),
                "profit_44ad": round(profit_44ad, 0),
                "total_profit": round(total_business_profit, 0)
            },
            "crypto": {
                "gains": round(crypto_income, 0),
                "tax": round(crypto_income * CRYPTO_RATE, 0)
            },
            "gaming": {
                "gains": round(gaming_income, 0),
                "tax": round(gaming_income * GAMING_RATE, 0)
            },
            "misc_income": {
                "total": round(total_misc_income, 0),
            },
        },
        
        # Deductions
        "deductions": deduction_details,
        "total_deductions": round(total_deductions, 0),
        # chapter_via_deductions_total is only the Chapter VI-A deductions (80C, 80D, etc.)
        # This matches itrData.deductions.total from the ITR parser
        "chapter_via_deductions_total": round(total_deductions, 0),
        # sec10_sec16_total captures the salary-head exemptions (HRA/LTA/PTax)
        "sec10_sec16_total": round(total_sec10_sec16, 0),
        
        # Tax Computation
        "gross_income": round(gross_income, 0),
        "taxable_normal_income": round(taxable_normal_income, 0),
        "tax_on_normal_income": round(tax_on_normal, 0),
        "rebate_87a": round(rebate, 0),
        "rebate_87a_on_normal": round(tax_on_normal - tax_after_rebate, 0),
        "rebate_87a_on_cg": round(
            (tax_stcg_equity - tax_stcg_equity_after_rebate) +
            (tax_ltcg_other - tax_ltcg_other_after_rebate), 0
        ),
        "tax_after_rebate": round(tax_after_rebate, 0),
        "tax_on_capital_gains": {
            "ltcg_equity": round(tax_ltcg_equity, 0),
            "stcg_equity": round(tax_stcg_equity_after_rebate, 0),   # post-rebate
            "ltcg_other": round(tax_ltcg_other_after_rebate, 0),     # post-rebate
            "total": round(total_cg_tax, 0),
        },
        "rebate_marginal_relief": round(rebate_marginal_relief, 0),
        "surcharge": round(surcharge, 0),
        "surcharge_detail": {
            "rate": surcharge_info["rate"],
            "cg_rate": surcharge_info["cg_rate"],
            "marginal_relief": round(surcharge_info["marginal_relief"], 0),
        },
        "cess": round(cess, 0),
        "total_tax": round(total_tax, 0),

        # Interest u/s 234A/234B/234C
        "interest_234a": interest_234["i234a"],
        "interest_234b": interest_234["i234b"],
        "interest_234c": interest_234["i234c"],
        "interest_234_total": interest_234["total"],
        "aggregate_liability": round(aggregate_liability, 0),

        # Tax Payments
        "tds_paid": round(tds_paid, 0),
        "advance_tax": round(advance_tax, 0),
        "manual_tax_paid": round(manual_tax_paid, 0),
        "total_tax_paid": round(total_tax_paid, 0),
        "refund_or_due": round(refund_or_due, 0),
        
        # Detailed Breakdowns
        "dividends_detail": ais_data.get("dividends", []),
        "interest_savings_detail": ais_data.get("interest_savings", []),
        "interest_deposits_detail": ais_data.get("interest_deposits", []),
        "interest_others_detail": ais_data.get("interest_others", []),
        "misc_income_detail": ais_data.get("misc_income", []),
        "cg_equity_detail": ais_data.get("capital_gains_equity", []),
        "cg_mf_equity_detail": ais_data.get("capital_gains_mf_equity", []),
        "cg_mf_other_detail": cg_mf_other,
        "cg_real_estate_detail": cg_real_estate,
        "cg_unlisted_detail": cg_unlisted,
        "cg_bonds_gold_detail": cg_bonds_gold,
        "salary_quarterly": ais_data.get("salary", {}).get("quarterly", []),
        "refunds": ais_data.get("refunds", []),
    }
