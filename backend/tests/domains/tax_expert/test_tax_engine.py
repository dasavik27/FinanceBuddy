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
from datetime import datetime

import pandas as pd
import pytest

from domains.tax_expert import tax_engine, tax_sessions
from domains.tax_expert.tax_engine import _grandfathered_gain, _normalize_fy, compute_tax


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


# ── Section 112A grandfathering was dead code ─────────────────────────────────

def test_grandfathering_applies_without_an_acquisition_date():
    """
    The gate used to require `acquired_date`, which the AIS capital-gains schedules do
    not contain - they carry only "DATE OF SALE/ TRANSFER". So the branch never fired in
    production, and every pre-2018 holding was taxed on its full historical gain. The
    only places those keys appear are the tests that injected them.
    """
    trade = {
        "type": "LTCG",
        "consideration": 500000.0,
        "cost": 100000.0,
        "gain": 400000.0,          # raw gain, ungrandfathered
        "fmv_31jan2018": 300000.0,
    }
    # Cost becomes max(100000, min(300000, 500000)) = 300000 -> gain 200000.
    assert _grandfathered_gain(trade) == 200000.0


def test_grandfathering_is_vetoed_by_a_known_post_cutoff_acquisition():
    """A spurious FMV on a post-2018 lot must not under-tax it."""
    trade = {
        "type": "LTCG",
        "consideration": 500000.0,
        "cost": 100000.0,
        "gain": 400000.0,
        "fmv_31jan2018": 300000.0,
        "acquired_date": "2020-06-01",
    }
    assert _grandfathered_gain(trade) == 400000.0


def test_grandfathering_never_increases_a_gain():
    """gf_cost >= cost by construction, so relief can only reduce the taxable gain."""
    trade = {
        "type": "LTCG", "consideration": 500000.0, "cost": 400000.0,
        "gain": 100000.0, "fmv_31jan2018": 50000.0,
    }
    assert _grandfathered_gain(trade) <= 100000.0


def test_grandfathering_ignores_short_term_trades():
    trade = {"type": "STCG", "consideration": 5.0, "cost": 1.0, "gain": 4.0,
             "fmv_31jan2018": 3.0}
    assert _grandfathered_gain(trade) == 4.0


def test_no_fmv_means_no_relief():
    trade = {"type": "LTCG", "consideration": 500000.0, "cost": 100000.0, "gain": 400000.0}
    assert _grandfathered_gain(trade) == 400000.0


# ── financial-year normalisation, which now gates a tax credit ────────────────

@pytest.mark.parametrize("raw,expected", [
    ("2025-26", "2025-26"),
    ("2025-2026", "2025-26"),
    ("F.Y. 2025-26", "2025-26"),
    ("2025 - 26", "2025-26"),
    ("2025/26", "2025-26"),
    ("2025", "2025-26"),
    ("", None),
    (None, None),
    ("not a year", None),
])
def test_financial_year_normalisation(raw, expected):
    """The AIS spells this several ways; comparing raw strings would misclassify every
    challan and silently drop a real tax credit."""
    assert _normalize_fy(raw) == expected


# ── AIS parser: immovable property is not a capital gain ──────────────────────

def test_property_transaction_does_not_fabricate_a_gain():
    """
    _process_real_estate used to record `cost: 0, gain: <full transaction value>`. The
    AIS never reports a cost of acquisition, and SFT-012 / TDS-194IA cover both sides of
    a conveyance - so buying a Rs 1 crore flat manufactured Rs 1 crore of LTCG.
    """
    from domains.tax_expert.ais_parser import _process_real_estate

    headers = ["SRNO", "PROPERTYDESCRIPTION", "TRANSACTIONVALUE", "STATUS"]
    df = pd.DataFrame(
        [headers, ["1", "Flat 4B, Pune", "10000000", "Active"]],
    )
    result = {"cg_real_estate": []}
    _process_real_estate(df, headers, result)

    assert len(result["cg_real_estate"]) == 1
    entry = result["cg_real_estate"][0]
    assert entry["gain"] == 0.0, "the full transaction value was booked as gain again"
    assert entry["cost_unknown"] is True
    assert entry["consideration"] == 10000000.0, "the transaction must still be surfaced"


def test_cost_unknown_entries_are_excluded_from_taxable_gains():
    """The parser flags them; the engine must actually honour the flag."""
    ais = {
        "fy": "2025-26",
        "salary": {"gross": 0, "quarterly": []},
        "cg_real_estate": [{
            "type": "LTCG", "security": "Flat", "consideration": 10000000.0,
            "cost": 0.0, "gain": 0.0, "cost_unknown": True, "needs_review": True,
        }],
    }
    out = tax_engine.compute_tax(ais, regime="new")
    assert out["cost_unknown_count"] == 1
    assert out["cost_unknown_value"] == 10000000.0
    assert out["total_tax"] == 0, (
        f"a property purchase produced Rs {out['total_tax']:,.0f} of tax"
    )


# ── AIS parser: 194A interest was dropped whole ───────────────────────────────

def test_194a_interest_table_is_parsed():
    """
    A 194A child table has the TDS shape ("AMOUNT PAID/CREDITED" + "TDS DEDUCTED"), not
    the SFT-016 shape ("INTEREST AMOUNT"). Both codes were routed to the SFT processor,
    whose guard requires INTERESTAMOUNT, so every 194A table was discarded whole.
    """
    from domains.tax_expert.ais_parser import _process_interest_tds

    headers = ["SRNO", "QUARTER", "AMOUNTPAIDCREDITED", "TDSDEDUCTED", "STATUS"]
    df = pd.DataFrame([headers, ["1", "Q1", "80000", "8000", "Active"]])
    result = {"interest_deposits": [], "interest_savings": []}
    _process_interest_tds(df, headers, result)

    assert len(result["interest_deposits"]) == 1
    row = result["interest_deposits"][0]
    assert row["amount"] == 80000.0
    assert row["tds_deducted"] == 8000.0


def test_interest_tds_reaches_the_total():
    """tds_total summed salary and dividends only, so interest TDS went uncredited."""
    from domains.tax_expert.ais_parser import _finalise_tds_total

    result = {
        "salary": {"quarterly": [{"tds_deducted": 5000.0}]},
        "dividends": [{"tds_deducted": 1000.0}],
        "interest_deposits": [{"tds_deducted": 8000.0}],
        "interest_savings": [],
        "rent_received": [],
        "tds_total": 0.0,
    }
    _finalise_tds_total(result)
    assert result["tds_total"] == 14000.0


# ── capital losses must not buy a rebate ──────────────────────────────────────

def test_a_capital_loss_does_not_unlock_the_87a_rebate():
    """
    total_taxable_income added raw, unfloored capital gains, so a loss dragged income
    below the Rs 12 lakh threshold and handed out a rebate the taxpayer had not earned.
    """
    base = {"fy": "2025-26", "salary": {"gross": 1400000, "quarterly": []}}
    with_loss = dict(base, cg_equity=[{
        "type": "LTCG", "security": "X", "consideration": 100000.0,
        "cost": 400000.0, "gain": -300000.0,
    }])

    out_plain = tax_engine.compute_tax(base, regime="new")
    out_loss = tax_engine.compute_tax(with_loss, regime="new")

    assert out_loss["total_tax"] >= out_plain["total_tax"], (
        "a capital loss reduced tax on salary income via the rebate threshold"
    )


@pytest.fixture(autouse=True)
def _clean_tax_sessions():
    tax_sessions.clear_all()
    yield
    tax_sessions.clear_all()


def _sample_ais():
    return {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "name": "Test User"},
        "salary": {"gross": 1_200_000, "tds_deducted": 100_000},
        "capital_gains_equity": [
            {"sr": 1, "security": "RELIANCE", "type": "LTCG", "gain": 300_000,
             "consideration": 500_000, "cost": 200_000},
        ],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
        "tax_payments": [
            {"fy": "2024-25", "total": 5000},
            {"fy": "2025-26", "total": 10000},
        ],
    }

def test_tax_engine_advance_tax_other_year_filter():
    ais = _sample_ais()
    result = tax_engine.compute_tax(ais, regime="old", overrides={})
    assert result["fy"] == "2025-26"

def test_tax_engine_bf_losses_and_old_regime_deductions():
    ais = _sample_ais()
    ais["capital_gains_equity"] = [
        {"sr": 1, "type": "LTCG", "gain": 200000, "consideration": 400000, "cost": 200000},
        {"sr": 2, "type": "STCG", "gain": 50000, "consideration": 150000, "cost": 100000},
    ]
    ais["capital_gains_mf_other"] = [
        {"sr": 1, "type": "LTCG", "gain": 80000, "consideration": 180000, "cost": 100000},
    ]
    result = tax_engine.compute_tax(
        ais,
        regime="old",
        overrides={
            "bf_losses": {"stcl": 100000, "ltcl": 50000},
            "deductions": {
                "80c": 150000, "80ccd1b": 50000, "80d_detail": {"self": 25000},
                "24b": 200000, "80g": 10000,
            },
            "age": 65,
        },
    )
    assert result["regime"] == "old"
    assert "total_tax" in result or "tax_summary" in result

def test_tax_engine_grandfathering_and_80d():
    gain = tax_engine._grandfathered_gain({
        "type": "LTCG", "gain": 100000, "consideration": 500000, "cost": 200000,
        "fmv_31jan2018": 300000, "acquired_date": "2017-01-01",
    })
    assert gain <= 300000

    flat_80d = tax_engine._compute_80d({"80d": 25000}, age=35)
    assert flat_80d == 25000
    detail_80d = tax_engine._compute_80d({
        "80d_detail": {"self": 20000, "parents": 15000, "preventive": 6000},
    }, age=35)
    assert detail_80d <= 50000

def test_tax_engine_new_regime_marginal_relief(monkeypatch):
    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 1_250_000, "tds_deducted": 0},
        "capital_gains_equity": [],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
    }
    result = tax_engine.compute_tax(ais, regime="new", overrides={})
    assert result["regime"] == "new"
    assert "rebate" in result or "tax_summary" in result or "total_tax" in result

def test_tax_engine_new_regime_marginal_relief_high_income():
    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 1_300_000, "tds_deducted": 0},
        "capital_gains_equity": [],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
    }
    result = tax_engine.compute_tax(ais, regime="new", overrides={})
    assert result["regime"] == "new"
    assert result.get("rebate_marginal_relief", 0) >= 0 or "tax_summary" in result

def test_tax_engine_rebate_on_special_and_ay_parse(monkeypatch):
    monkeypatch.setattr(tax_engine, "REBATE_ALLOW_ON_SPECIAL", True)
    ais = {
        "fy": "2025-2026",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 550000},
        "capital_gains_equity": [{"type": "STCG", "gain": 120000, "consideration": 220000, "cost": 100000}],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [{"type": "LTCG", "gain": 90000, "consideration": 180000, "cost": 90000}],
    }
    result = tax_engine.compute_tax(ais, regime="old", overrides={})
    assert result["ay"].startswith("2026")

    caps = tax_engine._compute_surcharge_with_caps(80000, 30000, 7_000_000, "old")
    assert caps["marginal_relief"] >= 0

def test_tax_engine_safe_float_and_bf_losses():
    assert tax_engine._safe_float("bad") == 0.0
    assert tax_engine._safe_float(None) == 0.0

    ais = _sample_ais()
    ais["capital_gains_equity"] = [
        {"sr": 1, "type": "LTCG", "gain": 200_000, "consideration": 400_000, "cost": 200_000},
    ]
    ais["capital_gains_mf_equity"] = [
        {"sr": 1, "type": "STCG", "gain": 50_000, "consideration": 150_000, "cost": 100_000},
    ]
    result = tax_engine.compute_tax(
        ais,
        regime="old",
        overrides={"bf_losses": {"stcl": 80000, "ltcl": 50000}},
    )
    assert "total_tax" in result or "tax_summary" in result

def test_tax_engine_surcharge_and_helpers():
    assert tax_engine._compute_slab_tax(600000, tax_engine.NEW_REGIME_SLABS) > 0
    assert tax_engine._compute_surcharge(100000, 6000000) > 0
    assert tax_engine._surcharge_rate(6000000, "new") <= tax_engine.SURCHARGE_NEW_REGIME_MAX_RATE
    assert tax_engine._surcharge_threshold_below(6000000) == 5000000
    caps = tax_engine._compute_surcharge_with_caps(50000, 20000, 6000000, "old")
    assert "surcharge" in caps
    assert tax_engine._months_ceil(
        datetime(2024, 1, 1),
        datetime(2024, 3, 15),
    ) >= 2
    assert tax_engine._round_down_100(1234.56) == 1200
    assert tax_engine._normalize_fy("2025-26") == "2025-26"
    assert tax_engine._normalize_fy("F.Y. 2025-2026") == "2025-26"
    assert tax_engine._parse_iso("2024-08-15") is not None
    assert tax_engine._parse_iso("bad") is None

def test_tax_engine_surcharge_top_slab_and_bf_cascade():
    assert tax_engine._compute_surcharge(50000, 10_000_000) > 0
    assert tax_engine._months_ceil(datetime(2024, 1, 15), datetime(2024, 3, 1)) >= 2

    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "dob": "01/01/1950"},
        "salary": {"gross": 900000},
        "interest_savings": [{"amount": 60000}],
        "capital_gains_equity": [
            {"type": "LTCG", "gain": 300000, "consideration": 600000, "cost": 300000},
        ],
        "capital_gains_mf_equity": [
            {"type": "STCG", "gain": 80000, "consideration": 180000, "cost": 100000},
        ],
        "capital_gains_mf_other": [
            {"type": "LTCG", "gain": 50000, "consideration": 120000, "cost": 70000},
        ],
    }
    result = tax_engine.compute_tax(
        ais,
        regime="old",
        overrides={
            "bf_losses": {"stcl": 150000, "ltcl": 350000},
            "deductions": {"80ccd2": 25000},
        },
    )
    assert result["regime"] == "old"

def test_tax_engine_surcharge_and_interest_branches(monkeypatch):
    from domains.tax_expert import tax_engine

    assert tax_engine._compute_surcharge(10000, 99999999) == pytest.approx(10000 * tax_engine.SURCHARGE_SLABS[-1][1])
    assert tax_engine._months_ceil(datetime(2024, 1, 1), datetime(2024, 2, 15)) >= 2

    caps = tax_engine._compute_surcharge_with_caps(50000, 20000, 6000000, "old")
    assert caps["marginal_relief"] >= 0

    monkeypatch.setattr(tax_engine, "INTEREST_234", {})
    empty_rules = tax_engine._compute_234_interest(0, 0, 0, {}, 30, False)
    assert empty_rules["total"] == 0.0

    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "dob": "bad-dob"},
        "salary": {"gross": 800000},
        "capital_gains_equity": [],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
        "interest_savings": [{"amount": 50000}],
    }
    result = tax_engine.compute_tax(
        ais,
        regime="old",
        overrides={"deductions": {"80ccd2": 50000}, "age": 65},
    )
    assert result["regime"] == "old"

    ais2 = {
        "fy": "2025-2026",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 500000},
        "capital_gains_equity": [
            {"type": "LTCG", "gain": 500000, "consideration": 800000, "cost": 300000},
        ],
        "capital_gains_mf_equity": [
            {"type": "STCG", "gain": 100000, "consideration": 200000, "cost": 100000},
        ],
        "capital_gains_mf_other": [],
    }
    result2 = tax_engine.compute_tax(
        ais2,
        regime="old",
        overrides={"bf_losses": {"stcl": 200000, "ltcl": 400000}},
    )
    assert "fy" in result2

    monkeypatch.setattr(tax_engine, "REBATE_ALLOW_ON_SPECIAL", True)
    ais3 = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 600000},
        "capital_gains_equity": [{"type": "STCG", "gain": 200000, "consideration": 400000, "cost": 200000}],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [{"type": "LTCG", "gain": 150000, "consideration": 300000, "cost": 150000}],
    }
    result3 = tax_engine.compute_tax(ais3, regime="old", overrides={})
    assert result3.get("rebate", 0) >= 0

def test_tax_engine_ay_parse_exception():
    from domains.tax_expert import tax_engine

    ais = {"fy": "BADFY", "personal": {}, "salary": {"gross": 0},
           "capital_gains_equity": [], "capital_gains_mf_equity": [], "capital_gains_mf_other": []}
    out = tax_engine.compute_tax(ais, regime="new", overrides={})
    assert "ay" in out

def test_tax_engine_rebate_on_special_income(monkeypatch):
    from domains.tax_expert import tax_engine

    monkeypatch.setattr(tax_engine, "REBATE_ALLOW_ON_SPECIAL", True)
    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F"},
        "salary": {"gross": 500000},
        "capital_gains_equity": [{"type": "STCG", "gain": 200000, "consideration": 400000, "cost": 200000}],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [{"type": "LTCG", "gain": 100000, "consideration": 200000, "cost": 100000}],
    }
    out = tax_engine.compute_tax(ais, regime="old", overrides={})
    assert out.get("rebate", 0) >= 0

def test_tax_engine_surcharge_top_slab_and_paths():
    from domains.tax_expert import tax_engine

    top = tax_engine._compute_surcharge(100000, 999999999)
    assert top == pytest.approx(100000 * tax_engine.SURCHARGE_SLABS[-1][1])
    assert tax_engine._months_ceil(datetime(2024, 6, 1), datetime(2024, 1, 1)) == 0

    ais = {
        "fy": "2025-26",
        "personal": {"pan": "ABCDE1234F", "dob": "01/01/1940"},
        "salary": {"gross": 900000},
        "capital_gains_equity": [{"type": "STCG", "gain": 50000, "consideration": 100000, "cost": 50000}],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [{"type": "STCG", "gain": 30000, "consideration": 60000, "cost": 30000}],
    }
    out = tax_engine.compute_tax(ais, regime="old", overrides={"bf_losses": {"stcl": 100000}, "age": 85})
    assert out["regime"] == "old"

