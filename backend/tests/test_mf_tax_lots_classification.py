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
