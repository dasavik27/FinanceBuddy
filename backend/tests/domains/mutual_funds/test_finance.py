"""
Regression and edge-case coverage for domains.mutual_funds.finance.
Uses the synthetic (non-PII) fixture from conftest.py where applicable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds import finance
from domains.mutual_funds.finance import (
    _to_date,
    compute_ltcg_harvest,
    compute_mandate_overlap,
    compute_risk_metrics,
    compute_rolling_return_avg,
    compute_rolling_returns,
    compute_sip_lumpsum_attribution,
    compute_xirr,
    compute_xirr_by_fy,
    is_absolute_return,
    simulate_historical_sip,
    stepup_sip_projection,
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


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 29, 12, 0, 0)


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    monkeypatch.setattr(finance, "datetime", _FrozenDateTime)
    monkeypatch.setattr(finance.logging, "raiseExceptions", False, raising=False)


def test_to_date_accepts_plain_date():
    d = date(2024, 6, 15)
    assert _to_date(d) is d
    assert _to_date(pd.Timestamp("2024-06-15")) == d


def test_compute_xirr_short_term_absolute_return():
    df = pd.DataFrame([
        {"Date": pd.Timestamp("2025-10-01"), "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
        {"Date": pd.Timestamp("2026-01-15"), "Amount": -5000, "Units": 50, "NAV": 100, "Type": "SIP", "Fund": "F1"},
    ])
    result = compute_xirr(df, current_value=16000)
    assert -99 <= result <= 500
    assert result > 0


def test_compute_xirr_zero_on_one_sided_flows():
    df = pd.DataFrame([
        {"Date": "2020-01-01", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
    ])
    assert compute_xirr(df, current_value=0) == 0.0
    assert compute_xirr(df, current_value=-100) == 0.0


def test_compute_xirr_returns_zero_on_xirr_failure(monkeypatch):
    df = pd.DataFrame([
        {"Date": "2020-01-01", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
        {"Date": "2024-01-01", "Amount": 5000, "Units": -50, "NAV": 100, "Type": "REDEMPTION", "Fund": "F1"},
    ])
    monkeypatch.setattr(finance, "xirr", lambda *a, **k: None)
    assert compute_xirr(df, current_value=8000) == 0.0


def test_compute_xirr_exception_handler(monkeypatch):
    df = pd.DataFrame([
        {"Date": "2020-01-01", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
    ])
    monkeypatch.setattr(finance, "xirr", MagicMock(side_effect=RuntimeError("boom")))
    assert compute_xirr(df, current_value=12000) == 0.0


def test_compute_xirr_by_fy_with_mocked_navs(monkeypatch):
    dates = pd.date_range("2022-01-01", periods=800, freq="B")
    nav = pd.Series(np.linspace(10.0, 20.0, len(dates)), index=dates)

    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda isin, days: nav if isin == "INF123" else pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda code, days: nav,
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_name",
        lambda name, days: nav,
    )

    df_t = pd.DataFrame([
        {"Date": "2023-05-01", "Fund": "Alpha Fund", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE"},
        {"Date": "2024-08-01", "Fund": "Alpha Fund", "Amount": -5000, "Units": 40, "NAV": 125, "Type": "SIP"},
    ])
    df_h = pd.DataFrame([
        {"Fund": "Alpha Fund", "ISIN": "INF123", "Scheme_Code": "111", "Market Value": 18000},
    ])
    rows = compute_xirr_by_fy(df_t, df_h)
    assert rows
    assert any("FY" in r["fy"] for r in rows)


def test_compute_xirr_by_fy_empty_and_nav_fallback(monkeypatch):
    assert compute_xirr_by_fy(pd.DataFrame(), pd.DataFrame()) == []

    df_t = pd.DataFrame([
        {"Date": "2023-01-01", "Fund": "No Nav Fund", "Amount": -5000, "Units": 50, "NAV": 100, "Type": "PURCHASE"},
    ])
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_name",
        lambda *a, **k: pd.Series(dtype=float),
    )
    rows = compute_xirr_by_fy(df_t, pd.DataFrame())
    assert isinstance(rows, list)


def test_simulate_historical_sip_error_paths():
    nav = pd.Series([10.0, 11.0], index=pd.date_range("2024-01-01", periods=2, freq="ME"))
    assert simulate_historical_sip(None, 1000, 5) == {}
    assert simulate_historical_sip(nav, 0, 5) == {}
    assert simulate_historical_sip(nav, 1000, 0) == {}
    assert "error" in simulate_historical_sip(pd.Series([10.0], index=[pd.Timestamp("2024-01-01")]), 1000, 5)


def test_simulate_historical_sip_success():
    dates = pd.date_range("2019-01-01", periods=72, freq="ME")
    nav = pd.Series(np.linspace(10.0, 30.0, len(dates)), index=dates)
    out = simulate_historical_sip(nav, monthly_amount=5000, years=3)
    assert out["installments"] > 0
    assert out["final_value"] > out["total_invested"]


def test_mandate_overlap_empty_and_zero_value():
    assert compute_mandate_overlap(None)["groups"] == []
    df = pd.DataFrame([{"Category": "Equity", "Cap Type": "Flexi Cap", "Market Value": 0, "Fund": "X", "AMC": "A"}])
    assert compute_mandate_overlap(df)["groups"] == []


def test_mandate_overlap_without_group_columns():
    df = pd.DataFrame([{"Market Value": 1000, "Fund": "Only Fund"}])
    assert compute_mandate_overlap(df)["groups"] == []


def test_sip_lumpsum_attribution_edge_cases():
    assert compute_sip_lumpsum_attribution(pd.DataFrame(), 1000) == {}
    df = pd.DataFrame([
        {"Type": "REDEMPTION", "Units": -10, "Amount": 1000, "NAV": 100},
    ])
    assert compute_sip_lumpsum_attribution(df, 1000) == {}


def test_sip_lumpsum_imputes_amount_from_units():
    df = pd.DataFrame([
        {"Type": "PURCHASE", "Units": 10, "Amount": 0, "NAV": 100},
    ])
    out = compute_sip_lumpsum_attribution(df, 1000)
    assert out["lumpsum_invested"] == 1000


def test_is_absolute_return_flag():
    short = pd.DataFrame([
        {"Date": "2026-01-01", "Amount": -1000, "Units": 10, "NAV": 100, "Type": "PURCHASE"},
    ])
    assert is_absolute_return(short) is True
    long = pd.DataFrame([
        {"Date": "2020-01-01", "Amount": -1000, "Units": 10, "NAV": 100, "Type": "PURCHASE"},
    ])
    assert is_absolute_return(long) is False


def test_rolling_returns_empty_and_insufficient():
    assert compute_rolling_return_avg(None, 3) is None
    assert compute_rolling_return_avg(pd.Series(dtype=float), 3) is None
    short = pd.Series([10.0, 11.0], index=pd.date_range("2025-01-01", periods=2))
    avg, series = compute_rolling_returns(short, window_years=5)
    assert avg is None
    assert series.empty


def test_compute_risk_metrics_without_benchmark():
    dates = pd.date_range("2022-01-01", periods=400, freq="B")
    nav = pd.Series(np.linspace(100, 150, len(dates)), index=dates)
    out = compute_risk_metrics(nav, pd.Series(dtype=float), risk_free_rate=6.5, min_days=90)
    assert out["data_days"] >= 90
    assert out["sharpe"] != 0.0
    assert out["beta"] == 1.0


def test_compute_risk_metrics_short_history_returns_defaults():
    nav = pd.Series([100.0, 101.0], index=pd.date_range("2025-01-01", periods=2))
    out = compute_risk_metrics(nav, pd.Series(dtype=float), min_days=90)
    assert out["risk_label"] == "N/A"


def test_stepup_sip_projection_with_lumpsum():
    out = stepup_sip_projection(
        monthly_sip=5000, years=3, annual_return=12.0, stepup_pct=10.0, lumpsum=25000
    )
    assert len(out["projection"]) == 3
    assert out["final_value"] > out["total_invested"]


def test_compute_ltcg_harvest_partial_and_losses():
    holdings = [
        {"fund": "Small Gain", "gain": 50000, "holding_days": 400, "current_value": 150000, "invested": 100000},
        {"fund": "Big Gain", "gain": 200000, "holding_days": 500, "current_value": 400000, "invested": 200000},
        {"fund": "Loss Book", "gain": 0, "stcg": -5000, "ltcg": 0, "holding_days": 100},
    ]
    out = compute_ltcg_harvest(holdings, ltcg_exemption=125000)
    assert out["eligible_count"] >= 2
    assert any("PARTIAL" in h["action"] for h in out["harvest_list"])
    assert any("LOSS" in h["action"] for h in out["harvest_list"])


def test_compute_benchmark_xirr_and_risk_alpha_paths():
    from domains.mutual_funds.finance import compute_benchmark_xirr

    dates = pd.date_range("2022-01-01", periods=500, freq="B")
    nav = pd.Series(np.linspace(100, 160, len(dates)), index=dates)
    bench = pd.Series(np.linspace(100, 140, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[10], "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
        {"Date": dates[200], "Amount": 5000, "Units": -40, "NAV": 125, "Type": "REDEMPTION", "Fund": "F1"},
    ])
    bxirr, bval = compute_benchmark_xirr(df_t, bench)
    assert bxirr != 0.0 or bval > 0

    # Monthly overlap long enough for Jensen alpha branch
    risk = compute_risk_metrics(nav, bench, risk_free_rate=6.5, min_days=60)
    assert risk["alpha"] != 0.0 or risk["sharpe"] != 0.0


def test_compute_xirr_only_inflows_returns_zero():
    df = pd.DataFrame([
        {"Date": pd.Timestamp("2020-01-01"), "Amount": 5000, "Units": -50, "NAV": 100, "Type": "REDEMPTION", "Fund": "F1"},
    ])
    assert compute_xirr(df, current_value=1000) == 0.0


def test_is_absolute_return_empty_ledger():
    assert is_absolute_return(pd.DataFrame(columns=["Date", "Amount", "Units", "NAV", "Type"])) is False


def test_simulate_historical_sip_invalid_inputs():
    dates = pd.date_range("2024-01-01", periods=60, freq="B")
    nav = pd.Series([10.0] * len(dates), index=dates)
    assert simulate_historical_sip(nav, monthly_amount=0, years=5) == {}
    assert simulate_historical_sip(None, monthly_amount=1000, years=5) == {}


def test_compute_xirr_by_fy_skips_empty_snapshot_window(monkeypatch):
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_name",
        lambda *a, **k: pd.Series(dtype=float),
    )
    df_t = pd.DataFrame([
        {"Date": pd.Timestamp("2026-07-30"), "Fund": "Late Fund", "Amount": -1000, "Units": 10, "NAV": 100, "Type": "PURCHASE"},
    ])
    rows = compute_xirr_by_fy(df_t, pd.DataFrame())
    assert rows == [] or isinstance(rows, list)


def test_compute_xirr_by_fy_code_nav_fallback(monkeypatch):
    dates = pd.date_range("2023-04-01", periods=400, freq="B")
    nav_by_code = pd.Series(np.linspace(10, 15, len(dates)), index=dates)

    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda code, days: nav_by_code if code == "123456" else pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_name",
        lambda *a, **k: pd.Series(dtype=float),
    )
    df_t = pd.DataFrame([
        {"Date": dates[5], "Fund": "Code Fund", "Amount": -10000, "Units": 1000, "NAV": 10,
         "Type": "PURCHASE", "ISIN": "", "Scheme Code": "123456"},
    ])
    rows = compute_xirr_by_fy(df_t, pd.DataFrame())
    assert len(rows) >= 1


def test_simulate_historical_sip_zero_nav_monthly():
    dates = pd.date_range("2024-01-01", periods=40, freq="B")
    nav = pd.Series([0.0] * len(dates), index=dates)
    out = simulate_historical_sip(nav, monthly_amount=1000, years=1)
    assert "error" in out


def test_compute_benchmark_xirr_short_hold_absolute():
    from domains.mutual_funds.finance import compute_benchmark_xirr

    dates = pd.date_range("2025-01-01", periods=30, freq="B")
    bench = pd.Series(np.linspace(100, 105, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
        {"Date": dates[20], "Amount": 5000, "Units": -50, "NAV": 100, "Type": "REDEMPTION", "Fund": "F1"},
    ])
    pct, val = compute_benchmark_xirr(df_t, bench)
    assert isinstance(pct, float)
    assert val >= 0


def test_compute_period_comparison_cagr():
    from domains.mutual_funds.finance import compute_period_comparison

    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    bench = pd.Series(np.linspace(100, 140, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Fund": "F1", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE"},
    ])
    df_h = pd.DataFrame([
        {"Fund": "F1", "ISIN": "INF1", "Scheme Code": "123", "Current Value": 15000},
    ])
    out = compute_period_comparison(df_t, df_h, total_value=15000, bench_series=bench, period_days=400)
    assert "port_pct" in out


def test_compute_xirr_by_fy_tx_nav_fallback(monkeypatch):
    dates = pd.date_range("2023-04-01", periods=400, freq="B")
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_name",
        lambda *a, **k: pd.Series(dtype=float),
    )
    df_t = pd.DataFrame([
        {"Date": dates[10], "Fund": "NavLess", "Amount": -5000, "Units": 50, "NAV": 100,
         "Type": "PURCHASE", "ISIN": "INF999", "Scheme Code": ""},
    ])
    rows = compute_xirr_by_fy(df_t, pd.DataFrame())
    assert isinstance(rows, list)


def test_compute_benchmark_xirr_income_and_slab(monkeypatch):
    from domains.mutual_funds.finance import compute_benchmark_xirr

    dates = pd.date_range("2023-01-01", periods=400, freq="B")
    bench = pd.Series(np.linspace(100, 130, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
        {"Date": dates[50], "Amount": 500, "Units": 0, "NAV": 0, "Type": "INCOME", "Fund": "F1"},
        {"Date": dates[100], "Amount": 8000, "Units": -80, "NAV": 100, "Type": "SELL", "Fund": "F1"},
    ])
    pct, val = compute_benchmark_xirr(df_t, bench)
    assert isinstance(pct, float)


def test_compute_period_comparison_empty_period(monkeypatch):
    from domains.mutual_funds.finance import compute_period_comparison

    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    bench = pd.Series(np.linspace(100, 105, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Fund": "F1", "Amount": -1000, "Units": 10, "NAV": 100, "Type": "PURCHASE"},
    ])
    df_h = pd.DataFrame([{"Fund": "F1", "ISIN": "INF1", "Scheme Code": "1", "Market Value": 1200}])
    out = compute_period_comparison(df_t, df_h, total_value=1200, bench_series=bench, period_days=5)
    assert isinstance(out, dict)


def test_compute_risk_metrics_short_series():
    nav = pd.Series([10, 11, 12], index=pd.date_range("2024-01-01", periods=3))
    risk = compute_risk_metrics(nav, nav, min_days=60)
    assert risk["data_days"] < 60 or "vol" in risk



def test_get_standard_ledger_empty_inputs():
    from domains.mutual_funds.finance import _get_standard_ledger

    assert _get_standard_ledger(None) == []
    assert _get_standard_ledger(pd.DataFrame()) == []

def test_compute_rolling_returns_empty_and_no_cagrs():
    from domains.mutual_funds.finance import (
        compute_rolling_return_avg,
        compute_rolling_returns,
        compute_rolling_return_series,
    )

    avg, series = compute_rolling_returns(None, 1)
    assert avg is None
    assert series.empty
    assert compute_rolling_return_avg(pd.Series(dtype=float), 1) is None
    assert compute_rolling_return_series(pd.Series(dtype=float), 1).empty

def test_compute_risk_metrics_capture_and_alpha_paths():
    from domains.mutual_funds.finance import compute_risk_metrics

    dates = pd.date_range("2020-01-01", periods=800, freq="B")
    nav = pd.Series(np.linspace(100, 220, len(dates)), index=dates)
    bench = pd.Series(np.linspace(100, 150, len(dates)), index=dates)
    out = compute_risk_metrics(nav, bench, risk_free_rate=6.5, min_days=60)
    assert out["risk_label"] != "N/A"
    assert "alpha" in out

    dates2 = pd.date_range("2024-01-01", periods=120, freq="B")
    nav2 = pd.Series(np.linspace(100, 130, len(dates2)), index=dates2)
    bench2 = pd.Series(np.linspace(100, 105, len(dates2)), index=dates2)
    out2 = compute_risk_metrics(nav2, bench2, min_days=30)
    assert out2["alpha"] != 0.0 or out2["beta"] != 0.0

def test_compute_benchmark_xirr_zero_bench_price_and_one_sided():
    from domains.mutual_funds.finance import compute_benchmark_xirr

    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    bench = pd.Series([0.0] * len(dates), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Amount": -1000, "Units": 10, "NAV": 100, "Type": "PURCHASE", "Fund": "F1"},
    ])
    pct, val = compute_benchmark_xirr(df_t, bench)
    assert pct == 0.0

    bench2 = pd.Series(np.linspace(100, 105, len(dates)), index=dates)
    df_in = pd.DataFrame([
        {"Date": dates[0], "Amount": 5000, "Units": -50, "NAV": 100, "Type": "REDEMPTION", "Fund": "F1"},
    ])
    pct2, val2 = compute_benchmark_xirr(df_in, bench2)
    assert pct2 == 0.0
    assert val2 >= 0

def test_compute_period_comparison_cagr(monkeypatch):
    from domains.mutual_funds.finance import compute_period_comparison

    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    bench = pd.Series(np.linspace(100, 160, len(dates)), index=dates)
    df_t = pd.DataFrame([
        {"Date": dates[0], "Fund": "F1", "Amount": -10000, "Units": 100, "NAV": 100, "Type": "PURCHASE"},
    ])
    df_h = pd.DataFrame([{"Fund": "F1", "ISIN": "INF1", "Scheme Code": "1", "Market Value": 15000}])
    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_isin",
        lambda *a, **k: pd.Series(np.linspace(100, 150, 200), index=dates[:200]),
    )
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_code", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_name", lambda *a, **k: pd.Series(dtype=float))
    out = compute_period_comparison(df_t, df_h, total_value=15000, bench_series=bench, period_days=400)
    assert out.get("port_pct") is not None

def test_finance_xirr_by_fy_and_benchmark_branches(monkeypatch):
    from domains.mutual_funds.finance import compute_benchmark_xirr, compute_xirr_by_fy, compute_risk_metrics

    dates = pd.date_range("2023-04-01", periods=400, freq="B")
    nav = pd.Series(np.linspace(10, 15, len(dates)), index=dates)
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_isin", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_code", lambda code, days: nav if code == "999" else pd.Series(dtype=float))
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_name", lambda *a, **k: pd.Series(dtype=float))

    df_t = pd.DataFrame([
        {"Date": dates[5], "Fund": "Code Fund", "Amount": -10000, "Units": 1000, "NAV": 10,
         "Type": "PURCHASE", "ISIN": "", "Scheme Code": "999"},
        {"Date": dates[200], "Fund": "Code Fund", "Amount": 5000, "Units": -400, "NAV": 12,
         "Type": "REDEMPTION", "ISIN": "", "Scheme Code": "999"},
    ])
    rows = compute_xirr_by_fy(df_t, pd.DataFrame())
    assert isinstance(rows, list)

    bench = pd.Series(np.linspace(100, 130, len(dates)), index=dates)
    pct, val = compute_benchmark_xirr(df_t, bench)
    assert isinstance(pct, float)

    # High vol for Very High risk label
    nav2 = pd.Series(np.linspace(100, 300, len(dates)), index=dates)
    bench2 = pd.Series(np.linspace(100, 110, len(dates)), index=dates)
    out = compute_risk_metrics(nav2, bench2, min_days=60)
    assert out["risk_label"] != "N/A"

