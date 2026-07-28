"""
Regression tests for finance.py's dense quant functions that don't require
live network/NAV-provider calls. Uses the synthetic (non-PII) fixture from
conftest.py.
"""
from domains.mutual_funds.finance import (
    compute_xirr,
    compute_mandate_overlap,
    compute_sip_lumpsum_attribution,
)
from tests.conftest import FUND_EQUITY, FUND_ELSS, FUND_LIQUID


def test_compute_xirr_positive_growth(synthetic_transactions):
    # Total invested across all funds ~ (15*200*avg_nav) + 15000 + 60800; a generous
    # current value should yield a healthy positive XIRR, not blow up or return 0.
    invested = 15 * 200 * 22.0 + 15000 + 50000 + 10800 - 22400
    current_value = invested * 1.4
    xirr_pct = compute_xirr(synthetic_transactions, current_value)
    assert xirr_pct > 0
    assert xirr_pct < 200  # institutional sanity cap


def test_compute_xirr_zero_on_empty_or_invalid():
    import pandas as pd
    assert compute_xirr(pd.DataFrame(), 10000) == 0.0
    assert compute_xirr(pd.DataFrame({"Date": [], "Amount": []}), 0) == 0.0


def test_mandate_overlap_groups_same_category_cap_type(synthetic_holdings):
    import pandas as pd
    # Add a second Flexi Cap Equity fund so Equity+Flexi Cap has >=2 funds -> should group
    extra = synthetic_holdings.iloc[[0]].copy()
    extra["Fund"] = "Synthetic Flexi Growth Fund II"
    extra["AMC"] = "Synthetic AMC D"
    df_h = pd.concat([synthetic_holdings, extra], ignore_index=True)

    result = compute_mandate_overlap(df_h)
    equity_groups = [g for g in result["groups"] if g["category"] == "Equity"]
    assert equity_groups, "Expected an Equity/Flexi Cap overlap group"
    g = equity_groups[0]
    assert g["fund_count"] == 2
    assert g["same_amc"] is False  # different AMC in this case
    assert "disclaimer" in result and "proxy" in result["disclaimer"].lower()


def test_mandate_overlap_no_groups_when_all_distinct(synthetic_holdings):
    result = compute_mandate_overlap(synthetic_holdings)
    # Fixture has 3 funds, each a distinct Category/Cap-Type combo -> no overlap groups
    assert result["groups"] == []


def test_sip_lumpsum_attribution_splits_by_type(synthetic_transactions):
    total_value = 200000.0
    result = compute_sip_lumpsum_attribution(synthetic_transactions, total_value)
    assert result["is_approximate"] is True
    # 15 SIP installments vs 2 lumpsum purchases (ELSS + Liquid pre-cutoff) + 1 lumpsum top-up
    assert result["sip_invested"] > 0
    assert result["lumpsum_invested"] > 0
    # Splits must reconstruct the total value exactly (rounding aside)
    assert abs((result["sip_current_value"] + result["lumpsum_current_value"]) - total_value) < 1.0
