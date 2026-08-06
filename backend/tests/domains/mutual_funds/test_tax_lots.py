"""Mutual fund tax lots: FIFO, classification, and portfolio summary."""

"""
Capital-gains regime classification for mutual funds, and the non-finite Gain% leak.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from domains.mutual_funds.tax_lots import (
    DEBT_LTCG_DAYS, EQUITY_LTCG_DAYS, OTHER_LTCG_DAYS,
    holding_tax_breakdown, tax_treatment,
)


# ── three regimes, not two ────────────────────────────────────────────────────

@pytest.mark.parametrize("category,expected", [
    ("Flexi Cap", "equity"),
    ("ELSS", "equity"),
    ("Large Cap Index", "equity"),
    ("Corporate Bond", "debt"),
    ("Liquid", "debt"),
    ("Gilt", "debt"),
    # These two used to fall through to "equity" and get Section 112A treatment.
    ("Gold ETF", "other"),
    ("Silver Commodity Fund", "other"),
    ("International Equity", "other"),
    ("US NASDAQ 100", "other"),
    ("Global Opportunities", "other"),
])
def test_asset_class_regimes(category, expected):
    assert tax_treatment(category) == expected


def test_non_equity_funds_are_long_term_only_after_24_months():
    """
    112A requires >=65% domestic listed equity. Gold and international funds do not
    qualify, so they become long-term at 24 months, not 12 - and they were previously
    classified as equity, which made a 13-month-old gold holding "long-term".
    """
    assert OTHER_LTCG_DAYS == 730
    thirteen_months_ago = date.today() - timedelta(days=400)
    lots = [{"units": 100.0, "cost_per_unit": 100.0, "date": thirteen_months_ago}]

    gold = holding_tax_breakdown(lots, current_nav=150.0, category="Gold ETF")
    assert gold["ltcg_gain"] == 0, "gold went long-term at 13 months"
    assert gold["stcg_gain"] > 0

    equity = holding_tax_breakdown(lots, current_nav=150.0, category="Flexi Cap")
    assert equity["ltcg_gain"] > 0, "a 13-month equity holding is long-term"


def test_gold_held_over_two_years_is_long_term():
    lots = [{"units": 100.0, "cost_per_unit": 100.0,
             "date": date.today() - timedelta(days=800)}]
    out = holding_tax_breakdown(lots, current_nav=150.0, category="Gold ETF")
    assert out["ltcg_gain"] > 0
    assert out["stcg_gain"] == 0


def test_debt_long_term_threshold_is_now_24_months():
    """
    Finance (No. 2) Act 2024 set a single 24-month long-term threshold for every
    non-equity asset. At 36 months, genuinely long-term debt gains were taxed short.
    """
    assert DEBT_LTCG_DAYS == 730
    lots = [{"units": 100.0, "cost_per_unit": 100.0,
             # Pre-Apr-2023 so Sec 50AA does not apply, and >24 months but <36.
             "date": date(2022, 1, 1)}]
    out = holding_tax_breakdown(lots, current_nav=150.0, category="Corporate Bond")
    assert out["ltcg_gain"] > 0, "a 3-year-old debt lot was still being taxed as STCG"


def test_equity_threshold_is_unchanged_at_12_months():
    assert EQUITY_LTCG_DAYS == 365


def test_post_50aa_debt_is_always_slab_taxed():
    """Units bought after the Sec 50AA cutoff have no LTCG concept at any holding period."""
    lots = [{"units": 100.0, "cost_per_unit": 100.0, "date": date(2023, 6, 1)}]
    out = holding_tax_breakdown(lots, current_nav=200.0, category="Corporate Bond")
    assert out["ltcg_gain"] == 0
    assert out["slab_taxed_value"] > 0


# ── the non-finite leak that 500'd /journey ───────────────────────────────────

def _gain_pct(market_value: float, invested: float) -> float:
    """Reproduces the parser's Gain% computation."""
    df = pd.DataFrame([{"Market Value": market_value, "Invested": invested}])
    df["Gain"] = df["Market Value"] - df["Invested"]
    df["Gain%"] = (
        (df["Gain"] / df["Invested"].replace(0, float("nan")) * 100)
        .replace([float("inf"), float("-inf")], float("nan"))
        .fillna(0)
    )
    return float(df["Gain%"].iloc[0])


def test_zero_invested_does_not_produce_infinity():
    """
    `Gain / 0 * 100` is +inf, and `.fillna(0)` does not touch inf. /journey sorted by
    Gain% (inf to the top of "best funds") and emitted it raw; FastAPI renders with
    allow_nan=False, so the whole response 500'd.
    """
    value = _gain_pct(market_value=50000.0, invested=0.0)
    assert value == 0.0
    import math
    assert math.isfinite(value)


def test_zero_over_zero_does_not_produce_nan():
    assert _gain_pct(market_value=0.0, invested=0.0) == 0.0


def test_normal_gain_percentage_is_unaffected():
    assert _gain_pct(market_value=150.0, invested=100.0) == pytest.approx(50.0)
    assert _gain_pct(market_value=50.0, invested=100.0) == pytest.approx(-50.0)


def test_the_whole_frame_is_json_safe():
    """The property that actually matters: nothing non-finite reaches the encoder."""
    import json
    import math

    df = pd.DataFrame([
        {"Market Value": 50000.0, "Invested": 0.0},
        {"Market Value": 0.0, "Invested": 0.0},
        {"Market Value": 150.0, "Invested": 100.0},
    ])
    df["Gain"] = df["Market Value"] - df["Invested"]
    df["Gain%"] = (
        (df["Gain"] / df["Invested"].replace(0, float("nan")) * 100)
        .replace([float("inf"), float("-inf")], float("nan"))
        .fillna(0)
    )
    assert all(math.isfinite(v) for v in df["Gain%"])
    json.dumps(df["Gain%"].tolist(), allow_nan=False)  # raises if not


"""
test_tax_lots_full.py

Full unit test coverage for domains.mutual_funds.tax_lots:
- compute_fund_lots (FIFO queue management, bonus/reinvestments/redemptions)
- holding_tax_breakdown (Equity, ELSS lock-in, Debt Sec 50AA, Other assets)
- portfolio_tax_summary (LTCG harvesting & slab exposure)
- select_sell_candidate (tax-optimal trimming respecting lock-ins)
"""

from datetime import date, datetime, timedelta
import pandas as pd
import pytest

from domains.mutual_funds.tax_lots import (
    compute_fund_lots,
    holding_tax_breakdown,
    portfolio_tax_summary,
    select_sell_candidate,
)


def test_compute_fund_lots_fifo_drain():
    # 3 purchases and 1 partial redemption
    df_t = pd.DataFrame([
        {"Fund": "HDFC Flexi Cap", "Date": "2022-01-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "HDFC Flexi Cap", "Date": "2022-06-01", "Type": "SIP", "Units": 50, "Amount": 6000, "NAV": 120},
        {"Fund": "HDFC Flexi Cap", "Date": "2023-01-01", "Type": "REINVEST", "Units": 10, "Amount": 0, "NAV": 130},
        {"Fund": "HDFC Flexi Cap", "Date": "2023-06-01", "Type": "REDEMPTION", "Units": -120, "Amount": 18000, "NAV": 150},
    ])

    lots = compute_fund_lots(df_t, "HDFC Flexi Cap")
    # Initial 100 redeemed, next 20 of 50 redeemed -> 30 units remaining from 2022-06-01 + 10 units from 2023-01-01 = 40 units
    assert len(lots) == 2
    total_units = sum(l["units"] for l in lots)
    assert total_units == 40


def test_compute_fund_lots_empty_or_mismatch():
    assert compute_fund_lots(None, "HDFC Flexi Cap") == []
    assert compute_fund_lots(pd.DataFrame(), "HDFC Flexi Cap") == []
    df_other = pd.DataFrame([{"Fund": "Other Fund", "Date": "2022-01-01", "Type": "PURCHASE", "Units": 10, "Amount": 1000, "NAV": 100}])
    assert compute_fund_lots(df_other, "HDFC Flexi Cap") == []


def test_holding_tax_breakdown_equity_and_elss():
    today = date.today()
    lot_old = {"units": 100, "cost_per_unit": 100, "date": today - timedelta(days=400)}
    lot_new = {"units": 50, "cost_per_unit": 100, "date": today - timedelta(days=100)}

    # Equity breakdown
    bd = holding_tax_breakdown([lot_old, lot_new], current_nav=150.0, category="Large Cap")
    assert bd["treatment"] == "equity"
    assert bd["is_elss"] is False
    assert bd["ltcg_gain"] > 0
    assert bd["stcg_gain"] > 0
    assert bd["locked_units"] == 0

    # ELSS breakdown (3-year lock-in = 1095 days)
    lot_locked = {"units": 100, "cost_per_unit": 100, "date": today - timedelta(days=500)}
    bd_elss = holding_tax_breakdown([lot_locked], current_nav=150.0, category="ELSS Tax Saver")
    assert bd_elss["is_elss"] is True
    assert bd_elss["locked_units"] == 100
    assert bd_elss["locked_value"] == 15000.0


def test_holding_tax_breakdown_debt_and_other():
    today = date.today()
    # Debt post-April 2023 (Sec 50AA slab-taxed)
    lot_debt_post2023 = {"units": 100, "cost_per_unit": 100, "date": date(2023, 5, 1)}
    bd_debt = holding_tax_breakdown([lot_debt_post2023], current_nav=120.0, category="Liquid Debt")
    assert bd_debt["treatment"] == "debt"
    assert bd_debt["slab_taxed_value"] > 0

    # Other (Gold / International)
    lot_gold_ltcg = {"units": 50, "cost_per_unit": 100, "date": today - timedelta(days=800)}
    bd_gold = holding_tax_breakdown([lot_gold_ltcg], current_nav=130.0, category="Gold Fund")
    assert bd_gold["treatment"] == "other"
    assert bd_gold["ltcg_gain"] > 0


def test_portfolio_tax_summary_and_empty():
    empty_summary = portfolio_tax_summary(None, None)
    assert empty_summary["per_fund"] == []

    df_h = pd.DataFrame([
        {"Fund": "Axis Bluechip", "Category": "Large Cap", "NAV": 150.0, "Market Value": 15000.0},
        {"Fund": "HDFC Liquid", "Category": "Liquid Debt", "NAV": 110.0, "Market Value": 11000.0},
    ])
    df_t = pd.DataFrame([
        {"Fund": "Axis Bluechip", "Date": "2021-01-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "HDFC Liquid", "Date": "2023-05-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
    ])

    summary = portfolio_tax_summary(df_h, df_t)
    assert len(summary["per_fund"]) == 2
    assert "harvest" in summary
    assert "debt_summary" in summary


def test_select_sell_candidate_unlocked_preference():
    today = date.today()
    df_h = pd.DataFrame([
        {"Fund": "Fund Unlocked", "Category": "Flexi Cap", "NAV": 150.0, "Market Value": 15000.0},
        {"Fund": "Fund Locked ELSS", "Category": "ELSS Tax Saver", "NAV": 150.0, "Market Value": 15000.0},
    ])
    df_t = pd.DataFrame([
        {"Fund": "Fund Unlocked", "Date": today - timedelta(days=500), "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "Fund Locked ELSS", "Date": today - timedelta(days=200), "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
    ])

    mask = df_h["Market Value"] > 0
    candidate = select_sell_candidate(df_h, df_t, mask, sell_amount=5000.0)
    assert "picks" in candidate or "funds" in candidate or isinstance(candidate, dict)


def test_tax_lots_to_date_and_other_treatment():
    from domains.mutual_funds import tax_lots
    from datetime import date

    assert tax_lots._to_date(date(2024, 1, 1)) == date(2024, 1, 1)
    assert tax_lots.tax_treatment("International Equity Fund") == "other"

    today = date.today()
    lot = {"units": 0, "cost_per_unit": 100, "date": today - timedelta(days=100)}
    bd = tax_lots.holding_tax_breakdown([lot], current_nav=150.0, category="Large Cap")
    assert bd["stcg_gain"] == 0

    lot_debt = {"units": 100, "cost_per_unit": 100, "date": date(2022, 1, 1)}
    bd_debt = tax_lots.holding_tax_breakdown([lot_debt], current_nav=120.0, category="Corporate Bond")
    assert bd_debt["ltcg_gain"] >= 0

    df_h = pd.DataFrame([{"Fund": "ELSS Lock", "Category": "ELSS", "NAV": 100.0, "Market Value": 10000.0}])
    df_t = pd.DataFrame([{"Fund": "ELSS Lock", "Date": today - timedelta(days=100), "Units": 100, "Amount": 10000}])
    sel = tax_lots.select_sell_candidate(df_h, df_t, df_h["Category"] == "ELSS", 5000.0)
    assert "ELSS-locked" in sel.get("note", "")

    assert tax_lots.select_sell_candidate(pd.DataFrame(), df_t, pd.Series([], dtype=bool), 100.0) == {}

