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
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tax_rules.json")
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
    """Compute surcharge based on total income."""
    for limit, rate in SURCHARGE_SLABS:
        if total_income <= limit:
            return tax * rate
    return tax * SURCHARGE_SLABS[-1][1]


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
    
    # Equity LTCG (Listed shares + Equity MF)
    ltcg_equity = sum(t.get("gain", 0) for t in cg_equity if t.get("type") == "LTCG")
    ltcg_equity += sum(t.get("gain", 0) for t in cg_mf_equity if t.get("type") == "LTCG")
    
    # Equity STCG
    stcg_equity = sum(t.get("gain", 0) for t in cg_equity if t.get("type") == "STCG")
    stcg_equity += sum(t.get("gain", 0) for t in cg_mf_equity if t.get("type") == "STCG")
    
    # Other (Debt/Non-Equity/RealEstate/Unlisted/Bonds/Gold) LTCG/STCG — treated differently
    # LTCG on these is usually 12.5% (Budget 2024 for all assets without indexation)
    # STCG on these is added to normal income (slab rates)
    
    # Let's combine all "Other" assets
    other_assets = cg_mf_other + cg_real_estate + cg_unlisted + cg_bonds_gold
    ltcg_other = sum(t.get("gain", 0) for t in other_assets if t.get("type") == "LTCG")
    stcg_other = sum(t.get("gain", 0) for t in other_assets if t.get("type") == "STCG")

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
    
    total_capital_gains = ltcg_equity + stcg_equity + ltcg_other + stcg_other
    # total_special_rate excludes stcg_other (which flows via slab into normal income)
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
    
    # Other STCG: Taxed at slab rate (included in normal income)
    slab_rate_cg = max(0, stcg_other)
    
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
        
        # 80D - Medical Insurance
        ded_80d = min(_safe_float(deductions.get("80d", 0)), DEDUCTION_80D_LIMIT_SELF + DEDUCTION_80D_LIMIT_PARENTS)
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
        
        # 2. Offset against STCG Equity (Only allowed in OLD regime)
        if rebate_limit > 0 and regime == "old":
            used_rebate = min(tax_stcg_equity_after_rebate, rebate_limit)
            tax_stcg_equity_after_rebate -= used_rebate
            rebate += used_rebate
            rebate_limit -= used_rebate
            
        # 3. Offset against LTCG Other (Sec 112) (Only allowed in OLD regime)
        if rebate_limit > 0 and regime == "old":
            used_rebate = min(tax_ltcg_other_after_rebate, rebate_limit)
            tax_ltcg_other_after_rebate -= used_rebate
            rebate += used_rebate
            rebate_limit -= used_rebate
            
    # Recompute total CG tax after rebate
    total_cg_tax = tax_ltcg_equity + tax_stcg_equity_after_rebate + tax_ltcg_other_after_rebate
    
    # ── 10. Total Tax Before Cess ──────────────────────────────────────
    tax_crypto = crypto_income * CRYPTO_RATE
    tax_gaming = gaming_income * GAMING_RATE
    total_special_tax = tax_crypto + tax_gaming
    total_tax_before_cess = tax_after_rebate + total_cg_tax + total_special_tax
    
    # ── 11. Surcharge ──────────────────────────────────────────────────
    total_income_for_surcharge = taxable_normal_income + ltcg_equity + stcg_equity + ltcg_other + crypto_income + gaming_income
    surcharge = _compute_surcharge(total_tax_before_cess, total_income_for_surcharge)
    
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
    
    # ── 15. Refund or Due ──────────────────────────────────────────────
    exact_refund_or_due = total_tax_paid - total_tax  # Positive = refund, negative = due
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
        "surcharge": round(surcharge, 0),
        "cess": round(cess, 0),
        "total_tax": round(total_tax, 0),
        
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
