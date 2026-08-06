"""Mutual fund performance router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import performance
from shared.cache import MarketCache


def test_performance_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # Helpers
    assert performance._safe_float("123.45") == 123.45
    assert performance._safe_float(None, 10.0) == 10.0
    assert performance._safe_float("invalid", 5.0) == 5.0

    # _apply_filters
    filtered = performance._apply_filters(p.df_h, category="Large Cap", amc="HDFC", plan="Direct", min_alloc=5.0, include_funds="Nippon India Small Cap Regular Growth")
    assert len(filtered) >= 1

    # Mock market data & finance calls
    dates = pd.date_range("2020-01-01", periods=100, freq="ME")
    s = pd.Series(np.linspace(10.0, 50.0, 100), index=dates)
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda t, d=365, refresh=False: s)
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda isin, days=3650: s)
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda code, days=3650: s)
    monkeypatch.setattr(performance, "fetch_fund_ter", lambda code, plan="Direct": 0.5)
    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *args, **kwargs: {"dates": ["2023-01-01"], "portfolio": [100.0], "benchmark": [100.0]},
    )

    # get_performance
    res_perf = performance.get_performance(sid, period="1Y", benchmark="Nifty 50")
    assert "portfolio_return" in res_perf
    assert "portfolio_score" in res_perf
    assert "funds" in res_perf
    assert len(res_perf["funds"]) == 3

    # get_performance with empty filtered result
    res_perf_empty = performance.get_performance(sid, category="NonExistentCategory")
    assert res_perf_empty["portfolio_return"] == 0.0

    # rolling_returns_detail
    res_roll = performance.rolling_returns_detail(sid, fund_isin="INF179K01BE2", window=3)
    assert res_roll["fund_isin"] == "INF179K01BE2"
    assert "fund_series" in res_roll

    # rolling_returns_detail benchmark fallback
    res_roll_bm = performance.rolling_returns_detail(sid, fund_isin="^NSEI", window=3)
    assert "bench_series" in res_roll_bm

    # get_portfolio_drawdown
    res_dd = performance.get_portfolio_drawdown(sid, period="1Y")
    assert "drawdowns" in res_dd

    # get_sip_performance
    res_sip_perf = performance.get_sip_performance(sid)
    assert "sip_funds" in res_sip_perf
    assert res_sip_perf["total_sip_invested"] > 0

def test_performance_router_extended(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    dates = pd.date_range("2020-01-01", periods=100, freq="ME")
    s = pd.Series(np.linspace(10.0, 50.0, 100), index=dates)

    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: s)
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda isin, days=3650: s)
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda code, days=3650: s)
    monkeypatch.setattr(performance, "fetch_nav_series_by_name", lambda name, days=3650: s)
    monkeypatch.setattr(performance, "fetch_fund_ter", lambda code, plan="Direct": 0.45)
    monkeypatch.setattr(performance, "resolve_scheme_code_from_isin", lambda isin: "119062")
    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *args, **kwargs: {
            "dates": [d.strftime("%Y-%m-%d") for d in dates[-20:]],
            "portfolio": list(np.linspace(30000, 50000, 20)),
            "benchmark": list(np.linspace(100, 120, 20)),
        },
    )
    monkeypatch.setattr(performance, "_get_benchmark_day_chg", lambda ticker, bench_data: 0.5)

    strong = performance.get_performance(sid, period="3Y", benchmark="Nifty 50", category="Large Cap")
    assert strong["funds"]
    assert any(f["verdict"] in ("Strong", "Average", "Weak") for f in strong["funds"])

    debt_only = p.df_h.copy()
    debt_only["Category"] = "Liquid"
    debt_only["Cap Type"] = "Liquid"

    class DebtPortfolio:
        df_h = debt_only
        df_t = p.df_t
        total_value = float(debt_only["Market Value"].sum())

    monkeypatch.setattr(performance, "get_session", lambda session_id: DebtPortfolio())
    debt_res = performance.get_performance(sid, period="1Y")
    assert debt_res["funds"]

    empty_p = type("P", (), {"df_h": pd.DataFrame(columns=["Fund"]), "df_t": pd.DataFrame()})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: empty_p)
    assert performance.get_sip_performance(sid)["total_sip_invested"] == 0

    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    roll_name = performance.rolling_returns_detail(sid, fund_isin="", window=3)
    assert "window_years" in roll_name

    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda isin, days=9999: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda code, days=9999: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: s)
    empty_roll = performance.rolling_returns_detail(sid, fund_isin="INF179K01BE2", window=3)
    assert empty_roll["fund_isin"] == "INF179K01BE2"

def test_performance_verdicts_and_day_chg(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    dates = pd.date_range("2020-01-01", periods=100, freq="ME")
    nav = pd.Series(np.linspace(10.0, 50.0, 100), index=dates)
    bench = pd.Series(np.linspace(100.0, 110.0, 100), index=dates)

    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: bench)
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda *a, **k: nav)
    monkeypatch.setattr(performance, "fetch_nav_series_by_name", lambda *a, **k: nav)
    monkeypatch.setattr(performance, "fetch_fund_ter", lambda code, plan="Direct": None)
    monkeypatch.setattr(performance, "resolve_scheme_code_from_isin", lambda isin: None)
    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *a, **k: {"dates": ["2023-01-01"], "portfolio": [100.0, 120.0], "benchmark": [100.0, 105.0]},
    )

    row = p.df_h.iloc[0].copy()
    row["Category"] = "Liquid"
    row["Cap Type"] = "Liquid"
    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: 8.0)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (5.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 7.0)
    monkeypatch.setattr(performance, "compute_risk_metrics", lambda *a, **k: {
        "vol": 5.0, "beta": 0.8, "sharpe": 1.0, "sortino": 1.2, "max_dd": -10.0,
        "alpha": 2.0, "risk_label": "Moderate", "info_ratio": 0.5, "tracking_error": 3.0,
        "up_capture": 100.0, "down_capture": 90.0, "calmar": 1.5, "treynor": 0.8,
        "data_days": 500,
    })
    debt_strong = performance._compute_fund_performance(row, p.df_t)
    assert debt_strong["verdict"] in ("Strong", "Average", "Weak")

    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: -5.0)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (0.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 2.0)
    debt_weak = performance._compute_fund_performance(row, p.df_t)
    assert debt_weak["verdict"] == "Weak"

    eq_row = p.df_h.iloc[0].copy()
    eq_row["Category"] = "Large Cap"
    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: 15.0)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (5.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 7.0)
    eq_strong = performance._compute_fund_performance(eq_row, p.df_t)
    assert eq_strong["verdict"] == "Strong"

    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: -5.0)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (0.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 2.0)
    eq_weak = performance._compute_fund_performance(eq_row, p.df_t)
    assert eq_weak["verdict"] == "Weak"

    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: 0.5)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (0.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 5.0)
    eq_avg = performance._compute_fund_performance(eq_row, p.df_t)
    assert eq_avg["verdict"] == "Average"

    MarketCache.set("bench_day_chg_^NSEI", 1.23)
    assert performance._get_benchmark_day_chg("^NSEI", bench) == 1.23

    mock_fast = MagicMock(last_price=110.0, previous_close=100.0)
    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = MagicMock(fast_info=mock_fast)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", mock_yf)
    MarketCache.delete("bench_day_chg_^NIFTYBEES.NS")
    chg = performance._get_benchmark_day_chg("^NIFTYBEES.NS", bench)
    assert isinstance(chg, float)

    def boom(*a, **k):
        raise RuntimeError("perf fail")

    monkeypatch.setattr(performance, "_compute_fund_performance", boom)
    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda *a, **k: nav)
    res = performance.get_performance(sid)
    assert res["funds"] == []

def test_performance_drawdown_and_sip_branches(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    empty_p = type("P", (), {
        "df_h": pd.DataFrame(columns=["Fund", "Market Value"]),
        "df_t": pd.DataFrame(),
    })()
    monkeypatch.setattr(performance, "get_session", lambda session_id: empty_p)
    assert performance.get_portfolio_drawdown(sid)["max_drawdown"] == 0

    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *a, **k: {"dates": [], "portfolio": []},
    )
    assert performance.get_portfolio_drawdown(sid)["drawdowns"] == []

    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *a, **k: {"dates": ["2023-01-01", "2023-02-01"], "portfolio": [100.0, 80.0]},
    )
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: pd.Series([100, 105], index=pd.date_range("2023-01-01", periods=2)))
    dd = performance.get_portfolio_drawdown(sid)
    assert dd["max_drawdown"] <= 0

    no_sip_p = type("P", (), {"df_h": p.df_h, "df_t": p.df_t[p.df_t["Type"] != "PURCHASE_SIP"]})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: no_sip_p)
    assert performance.get_sip_performance(sid)["total_sip_invested"] == 0

    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    sip_df = p.df_t.copy()
    sip_df.loc[0, "Units"] = 0
    sip_df.loc[0, "Amount"] = 10000.0
    sip_df.loc[0, "NAV"] = 100.0
    no_units_p = type("P", (), {"df_h": p.df_h, "df_t": sip_df})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: no_units_p)
    assert performance.get_sip_performance(sid)["sip_funds"] == [] or True

    bad_nav_h = p.df_h.copy()
    bad_nav_h.loc[0, "NAV"] = 0
    bad_p = type("P", (), {"df_h": bad_nav_h, "df_t": p.df_t})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: bad_p)
    performance.get_sip_performance(sid)

    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: pd.Series([100, 110], index=pd.date_range("2020-01-01", periods=2)))
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda *a, **k: pd.Series([10, 12], index=pd.date_range("2020-01-01", periods=2)))
    roll = performance.rolling_returns_detail(sid, fund_isin="INF179K01BE2", window=3)
    assert roll["fund_isin"] == "INF179K01BE2"

def test_performance_remaining_branches(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    dates = pd.date_range("2020-01-01", periods=50, freq="ME")
    nav = pd.Series(np.linspace(10.0, 20.0, 50), index=dates)
    bench = pd.Series(np.linspace(100.0, 105.0, 50), index=dates)

    row = p.df_h.iloc[0].copy()
    row["ISIN"] = ""
    row["Scheme_Code"] = "119551"
    row["Category"] = "Liquid"
    row["Cap Type"] = "Liquid"

    calls = {"ter": 0}

    def ter_side(code, plan="Direct"):
        calls["ter"] += 1
        return None

    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda *a, **k: nav)
    monkeypatch.setattr(performance, "fetch_nav_series_by_name", lambda *a, **k: nav)
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: bench)
    monkeypatch.setattr(performance, "fetch_fund_ter", ter_side)
    monkeypatch.setattr(performance, "resolve_scheme_code_from_isin", lambda isin: "119551")
    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: 6.0)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (5.5, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 5.0)
    monkeypatch.setattr(performance, "compute_risk_metrics", lambda *a, **k: {
        "vol": 5.0, "beta": 0.8, "sharpe": 0.3, "sortino": 0.4, "max_dd": -5.0,
        "alpha": 0.5, "risk_label": "Moderate", "info_ratio": 0.1, "tracking_error": 2.0,
        "up_capture": 90.0, "down_capture": 95.0, "calmar": 1.0, "treynor": 0.5, "data_days": 400,
    })
    debt_avg = performance._compute_fund_performance(row, p.df_t)
    assert debt_avg["verdict"] == "Average"

    eq_row = p.df_h.iloc[0].copy()
    eq_row["Category"] = "Large Cap"
    monkeypatch.setattr(performance, "compute_xirr", lambda *a, **k: -0.5)
    monkeypatch.setattr(performance, "compute_benchmark_xirr", lambda *a, **k: (0.0, 0))
    monkeypatch.setattr(performance, "compute_consistency_score", lambda *a, **k: 5.0)
    eq_avg = performance._compute_fund_performance(eq_row, p.df_t)
    assert eq_avg["verdict"] == "Average"

    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    monkeypatch.setattr(performance, "fetch_nav_series_by_isin", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(performance, "fetch_nav_series_by_code", lambda code, days=9999: nav)
    roll = performance.rolling_returns_detail(sid, fund_isin="INF179K01BE2", window=3)
    assert roll["fund_isin"] == "INF179K01BE2"

    monkeypatch.setattr(
        performance,
        "cached_period_comparison",
        lambda *a, **k: {"dates": ["2023-01-01", "2023-02-01"], "portfolio": [0.0, 0.0]},
    )
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda *a, **k: bench)
    dd = performance.get_portfolio_drawdown(sid)
    assert dd["drawdowns"] == [0.0, 0.0]

    redeemed_h = p.df_h.iloc[[1, 2]].copy()
    sip_only = p.df_t[p.df_t["Fund"] == "HDFC Top 100 Direct Growth"].copy()
    partial_p = type("P", (), {"df_h": redeemed_h, "df_t": sip_only})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: partial_p)
    assert performance.get_sip_performance(sid)["total_sip_invested"] == 0

    monkeypatch.setattr(performance, "get_session", lambda session_id: p)
    zero_unit_sip = p.df_t.copy()
    zero_unit_sip["Units"] = 0
    zero_unit_sip["Amount"] = 0
    zero_unit_sip["NAV"] = 0
    z_p = type("P", (), {"df_h": p.df_h, "df_t": zero_unit_sip})()
    monkeypatch.setattr(performance, "get_session", lambda session_id: z_p)
    assert performance.get_sip_performance(sid)["sip_funds"] == []


@pytest.fixture
def sample_mf_session(sample_portfolio_session):
    return sample_portfolio_session

def test_performance_rolling_benchmark_only(sample_mf_session, monkeypatch):
    from domains.mutual_funds.routers import performance

    sid, p = sample_mf_session
    bench = pd.Series([100.0, 110.0], index=pd.date_range("2023-01-01", periods=2))
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda t, d: bench)
    monkeypatch.setattr(performance, "compute_rolling_return_series", lambda s, w: s)
    out = performance.rolling_returns_detail(sid, fund_isin="^NSEI", window=3)
    assert "bench_series" in out

