"""
Regression tests for the Indian income-tax computation engine (AY 2026-27).

The headline test (`test_golden_old_regime_reproduces_filed_return`) pins the engine
to a fully worked ITR-2 so that any future rate/logic change that breaks a known-good
return fails loudly. The remaining tests exercise each correctness rule added to the
engine: 112A grandfathering, Section 50AA slab taxation, the 15%/25% surcharge caps,
87A rebate gating on special-rate income, 80D sub-limits, the 80CCD(1) salary cap and
Section 234A/B/C interest.

All figures are amounts only — no name/PAN/identity — and DOBs are generic.
"""
import pytest

from domains.tax_expert.tax_engine import compute_tax


# ─────────────────────────────────────────────────────────────────────────────
# Golden return — a complete, verified ITR-2 (Old Regime) computed end-to-end.
# ─────────────────────────────────────────────────────────────────────────────
def _golden_ais():
    return {
        "personal": {"dob": "01/01/1990"},          # non-senior
        "salary_annexure": {"gross_salary": 2703161},
        "salary": {"employer": "Acme", "tds_deducted": 383190, "quarterly": []},
        "dividends": [{"amount": 186}],
        "interest_savings": [{"amount": 3115}],
        "interest_deposits": [{"amount": 2404}],
        "tds_total": 383190,
        "fy": "2025-26",
    }


def _golden_overrides():
    return {
        "deductions": {
            "hra": 400980, "lta": 45200, "sec10_other": 295080, "ptax": 2400,
            "80c": 145499, "80ccd1": 70000, "80ccd1b": 50000, "80d": 73500,
        },
        "capital_gains": {
            "ltcg_equity": 166710, "stcg_equity": 3272,
            "ltcg_other": 18269, "stcg_other": 1528,
        },
    }


def test_golden_old_regime_reproduces_filed_return():
    r = compute_tax(_golden_ais(), regime="old", overrides=_golden_overrides())

    assert r["income_heads"]["salary"]["net"] == 1909501
    assert r["taxable_normal_income"] == 1640119
    assert r["total_deductions"] == 276615
    assert r["tax_on_normal_income"] == 304536
    assert r["tax_on_capital_gains"]["total"] == 8152      # 654 + 5214 + 2284
    assert r["surcharge"] == 0
    assert r["cess"] == 12508
    assert r["total_tax"] == 325196
    assert r["interest_234_total"] == 0
    assert r["refund_or_due"] == 57990                     # rounded to nearest ₹10 (Sec 288B)
    assert r["itr_type"] == "ITR-2"


def test_ltcg_equity_125k_exemption_applied():
    r = compute_tax(_golden_ais(), regime="old", overrides=_golden_overrides())
    cg = r["income_heads"]["capital_gains"]
    assert cg["ltcg_equity_exemption"] == 125000
    # 166710 − 125000 = 41710 taxable @ 12.5% = 5214 (rounded)
    assert cg["ltcg_equity_taxable"] == 41710
    assert r["tax_on_capital_gains"]["ltcg_equity"] == 5214


# ─────────────────────────────────────────────────────────────────────────────
# Section 112A grandfathering (FMV as on 31-Jan-2018)
# ─────────────────────────────────────────────────────────────────────────────
def test_grandfathering_applied_for_pre_2018_lot():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
        "capital_gains_equity": [{
            "type": "LTCG", "security": "OLD", "consideration": 500000, "cost": 100000,
            "gain": 400000, "fmv_31jan2018": 450000, "acquired_date": "2015-06-01",
        }],
    }
    r = compute_tax(ais, regime="new", overrides={})
    cg = r["income_heads"]["capital_gains"]
    # Grandfathered cost = max(100000, min(450000, 500000)) = 450000 → gain 50000.
    assert cg["ltcg_equity"] == 50000
    assert cg["grandfather_benefit"] == 350000


def test_grandfathering_not_applied_for_post_2018_lot():
    """A post-cutoff lot must NOT get grandfathering even if an FMV is present."""
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
        "capital_gains_equity": [{
            "type": "LTCG", "security": "NEW", "consideration": 500000, "cost": 100000,
            "gain": 400000, "fmv_31jan2018": 450000, "acquired_date": "2020-06-01",
        }],
    }
    r = compute_tax(ais, regime="new", overrides={})
    assert r["income_heads"]["capital_gains"]["ltcg_equity"] == 400000
    assert r["income_heads"]["capital_gains"]["grandfather_benefit"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Section 50AA — specified (debt) funds always taxed at slab
# ─────────────────────────────────────────────────────────────────────────────
def test_section_50aa_slab_fund_routed_to_normal_income():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 1500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
        "cg_bonds_gold": [{
            "type": "LTCG", "security": "Liquid", "consideration": 300000, "cost": 200000,
            "gain": 100000, "slab_taxed": True,
        }],
    }
    r = compute_tax(ais, regime="old", overrides={"deductions": {}})
    cg = r["income_heads"]["capital_gains"]
    assert cg["slab_taxed_cg"] == 100000
    assert cg["ltcg_other"] == 0            # not given the 12.5% treatment
    # The slab gain must be inside taxable normal income, not the special-rate total.
    assert r["tax_on_capital_gains"]["ltcg_other"] == 0


def test_debt_fund_flagged_by_acquisition_date():
    """is_debt + acquisition on/after the 2023-04-01 cutoff ⇒ slab taxation."""
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 1500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
        "capital_gains_mf_other": [{
            "type": "LTCG", "security": "Gilt", "consideration": 130000, "cost": 90000,
            "gain": 40000, "is_debt": True, "acquired_date": "2023-06-01",
        }],
    }
    r = compute_tax(ais, regime="old", overrides={"deductions": {}})
    assert r["income_heads"]["capital_gains"]["slab_taxed_cg"] == 40000
    assert r["income_heads"]["capital_gains"]["ltcg_other"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Surcharge caps + marginal relief
# ─────────────────────────────────────────────────────────────────────────────
def test_surcharge_cg_capped_at_15pct():
    ais = {
        "personal": {"dob": "01/01/1985"},
        "salary_annexure": {"gross_salary": 8000000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
        "capital_gains_mf_equity": [{
            "type": "LTCG", "security": "X", "consideration": 5000000, "cost": 2000000, "gain": 3000000,
        }],
    }
    r = compute_tax(ais, regime="new", overrides={})
    # Total income > 1cr but ≤ 2cr → base 15%; CG portion also capped at 15%.
    assert r["surcharge_detail"]["cg_rate"] <= 0.15
    assert r["surcharge"] > 0


def test_new_regime_surcharge_capped_at_25pct():
    ais = {
        "personal": {"dob": "01/01/1985"},
        "salary_annexure": {"gross_salary": 80000000},   # > ₹5cr
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
    }
    r = compute_tax(ais, regime="new", overrides={})
    assert r["surcharge_detail"]["rate"] == 0.25          # 37% band does not apply in New Regime


# ─────────────────────────────────────────────────────────────────────────────
# 87A rebate must NOT reduce special-rate tax (current ITD position)
# ─────────────────────────────────────────────────────────────────────────────
def test_rebate_not_applied_to_special_rate_income():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 450000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
    }
    overrides = {"deductions": {}, "capital_gains": {"stcg_equity": 50000}}
    r = compute_tax(ais, regime="old", overrides=overrides)
    # Normal tax fully rebated, but the ₹50,000 STCG @20% = ₹10,000 stays taxable.
    assert r["tax_after_rebate"] == 0
    assert r["tax_on_capital_gains"]["stcg_equity"] == 10000


# ─────────────────────────────────────────────────────────────────────────────
# 80D sub-limits
# ─────────────────────────────────────────────────────────────────────────────
def test_80d_preventive_checkup_capped_at_5000():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 1500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
    }
    overrides = {"deductions": {"80d_detail": {"self_preventive": 8000}}}
    r = compute_tax(ais, regime="old", overrides=overrides)
    assert r["deductions"]["80d"] == 5000     # preventive capped at ₹5,000


def test_80d_self_plus_senior_parents():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 1500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
    }
    overrides = {"deductions": {"80d_detail": {
        "self_premium": 20000, "self_preventive": 8000,      # → 20000 + 5000 = 25000 (capped)
        "parents_senior": True, "parents_medical": 60000,    # → 50000 (senior cap)
    }}}
    r = compute_tax(ais, regime="old", overrides=overrides)
    assert r["deductions"]["80d"] == 75000


# ─────────────────────────────────────────────────────────────────────────────
# 80CCD(1) capped at 10% of salary
# ─────────────────────────────────────────────────────────────────────────────
def test_80ccd1_capped_at_10pct_of_salary():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 500000},
        "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26",
    }
    overrides = {"deductions": {"80ccd1": 100000}}     # 10% of 5L = 50000 cap
    r = compute_tax(ais, regime="old", overrides=overrides)
    assert r["deductions"]["80ccd1"] == 50000


# ─────────────────────────────────────────────────────────────────────────────
# Section 234 interest
# ─────────────────────────────────────────────────────────────────────────────
def test_no_234_interest_when_tds_covers_and_filed_on_time():
    r = compute_tax(_golden_ais(), regime="old", overrides=_golden_overrides())
    assert r["interest_234a"] == 0
    assert r["interest_234b"] == 0
    assert r["interest_234c"] == 0


def test_234_interest_on_late_filing_with_shortfall():
    ais = {
        "personal": {"dob": "01/01/1990"},
        "salary_annexure": {"gross_salary": 2000000},
        "salary": {"tds_deducted": 100000, "quarterly": []}, "tds_total": 100000, "fy": "2025-26",
    }
    r = compute_tax(ais, regime="new", overrides={"filing_date": "2026-10-15"})
    assert r["interest_234a"] > 0     # filed after 31-Jul with tax payable
    assert r["interest_234b"] > 0     # advance tax < 90% of assessed
    assert r["interest_234c"] > 0     # instalments deferred


def test_senior_without_business_exempt_from_234b():
    ais = {
        "personal": {"dob": "01/01/1955"},   # senior citizen
        "salary_annexure": {"gross_salary": 2000000},
        "salary": {"tds_deducted": 100000, "quarterly": []}, "tds_total": 100000, "fy": "2025-26",
    }
    r = compute_tax(ais, regime="new", overrides={})
    assert r["interest_234b"] == 0
    assert r["interest_234c"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Regime comparison / basic sanity
# ─────────────────────────────────────────────────────────────────────────────
def test_empty_return_is_itr1_and_zero_tax():
    ais = {"personal": {"dob": "01/01/1990"}, "salary_annexure": {"gross_salary": 0},
           "salary": {"tds_deducted": 0, "quarterly": []}, "tds_total": 0, "fy": "2025-26"}
    r = compute_tax(ais, regime="new", overrides={})
    assert r["itr_type"] == "ITR-1"
    assert r["total_tax"] == 0
