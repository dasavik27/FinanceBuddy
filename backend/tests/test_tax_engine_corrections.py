"""
Correctness regressions in the tax engine and AIS parser.

Each test below corresponds to a defect that produced a confidently wrong rupee figure
with no error at any log level.
"""

import pandas as pd
import pytest

from domains.tax_expert import tax_engine
from domains.tax_expert.tax_engine import _grandfathered_gain, _normalize_fy


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
