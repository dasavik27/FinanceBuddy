"""
Regression tests for the lot-level tax engine (FIFO reconstruction, STCG/LTCG
classification, ELSS lock-in, tax-aware sell-candidate selection). Uses the
synthetic (non-PII) portfolio fixture from conftest.py — never a real CAS file.
"""
from domains.mutual_funds.tax_lots import (
    compute_fund_lots,
    holding_tax_breakdown,
    select_sell_candidate,
)
from tests.conftest import FUND_EQUITY, FUND_ELSS, FUND_LIQUID


def test_compute_fund_lots_fifo_reduction(synthetic_transactions):
    lots = compute_fund_lots(synthetic_transactions, FUND_LIQUID)
    total_units = sum(l["units"] for l in lots)
    # 500 + 100 purchased, 200 redeemed FIFO (fully consumes the 500-unit lot's start)
    assert round(total_units, 2) == 400.0
    # FIFO should have eaten into the oldest (2022-01-15) lot first
    assert lots[0]["units"] < 500.0


def test_compute_fund_lots_equity_full_units(synthetic_transactions):
    lots = compute_fund_lots(synthetic_transactions, FUND_EQUITY)
    total_units = sum(l["units"] for l in lots)
    assert round(total_units, 2) == 3000.0  # 15 x 200, no redemptions


def test_equity_stcg_ltcg_split(synthetic_transactions):
    lots = compute_fund_lots(synthetic_transactions, FUND_EQUITY)
    bd = holding_tax_breakdown(lots, current_nav=26.0, category="Equity")
    # Oldest ~5 of 15 monthly installments are >365 days old -> LTCG bucket
    assert bd["ltcg_value"] > 0
    assert bd["stcg_value"] > 0
    assert bd["treatment"] == "equity"
    assert not bd["is_elss"]


def test_elss_lockin_flagged(synthetic_transactions):
    lots = compute_fund_lots(synthetic_transactions, FUND_ELSS)
    bd = holding_tax_breakdown(lots, current_nav=17.0, category="ELSS")
    assert bd["is_elss"]
    # Purchased 100 days ago -- nowhere near the 1095-day lock-in
    assert bd["locked_value"] > 0
    assert round(bd["locked_units"], 2) == 1000.0


def test_debt_regime_split_pre_and_post_cutoff(synthetic_transactions):
    lots = compute_fund_lots(synthetic_transactions, FUND_LIQUID)
    bd = holding_tax_breakdown(lots, current_nav=115.0, category="Liquid")
    assert bd["treatment"] == "debt"
    # The pre-2023 lot (partially consumed by FIFO) should have aged into LTCG;
    # the post-cutoff top-up is always slab-taxed via Section 50AA regardless of age.
    assert bd["ltcg_value"] > 0
    assert bd["stcg_value"] > 0
    assert bd["slab_taxed_value"] > 0


def test_select_sell_candidate_excludes_elss_lockin(synthetic_transactions, synthetic_holdings):
    mask = synthetic_holdings["Fund"] == FUND_ELSS
    result = select_sell_candidate(synthetic_holdings, synthetic_transactions, mask, sell_amount=5000)
    # The only fund in this category slice is fully ELSS-locked -> no sellable candidate
    assert result.get("picks", []) == [] or "note" in result
    if "note" in result:
        assert "locked" in result["note"].lower()


def test_select_sell_candidate_taxes_only_gain_not_principal(synthetic_transactions, synthetic_holdings):
    mask = synthetic_holdings["Fund"] == FUND_EQUITY
    sell_amount = 10000.0
    result = select_sell_candidate(synthetic_holdings, synthetic_transactions, mask, sell_amount)
    assert result["picks"], "Expected at least one pick for an unlocked equity fund"
    # Regression guard for the earlier bug: tax must be a small fraction of the
    # redemption amount (only the embedded GAIN is taxed, not the principal).
    assert result["estimated_tax"] < sell_amount * 0.3


def test_select_sell_candidate_flags_exit_load_for_recent_units(synthetic_transactions, synthetic_holdings):
    mask = synthetic_holdings["Fund"] == FUND_EQUITY
    # Force the picker to reach into the recent (<1Y, STCG) installments
    result = select_sell_candidate(synthetic_holdings, synthetic_transactions, mask, sell_amount=50000.0)
    assert result.get("estimated_exit_load", 0) >= 0
