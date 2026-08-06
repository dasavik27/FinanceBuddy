"""Mutual fund tab_common helpers and peer selection."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds import tab_common
from shared.services.cache import MARKET_CACHE


def test_tab_common_helpers():
    # 1. compare_metric
    assert tab_common.compare_metric("Alpha", None, 5.0)["winner"] is None
    assert tab_common.compare_metric("Alpha", 10.0, 5.0, higher_better=True)["winner"] == "A"
    assert tab_common.compare_metric("Alpha", 5.0, 10.0, higher_better=True)["winner"] == "B"
    assert tab_common.compare_metric("Alpha", 5.0, 5.0, higher_better=True)["winner"] == "Tie"
    assert tab_common.compare_metric("Expense", 0.5, 1.0, higher_better=False)["winner"] == "A"
    assert tab_common.compare_metric("Expense", 1.0, 0.5, higher_better=False)["winner"] == "B"
    assert tab_common.compare_metric("Expense", 0.5, 0.5, higher_better=False)["winner"] == "Tie"

    # 2. series_to_list
    dates = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"])
    s = pd.Series([10.0, np.nan, 12.5], index=dates)
    s_list = tab_common.series_to_list(s)
    assert len(s_list) == 2
    assert s_list[0]["date"] == "2025-01-01"
    assert s_list[0]["value"] == 10.0

    # 3. rebalance_roll_up
    assert tab_common.rebalance_roll_up("Large Cap") == "Equity"
    assert tab_common.rebalance_roll_up("Liquid") == "Debt"
    assert tab_common.rebalance_roll_up("Balanced Advantage") == "Hybrid"
    assert tab_common.rebalance_roll_up("Commodities") == "Other"

def test_tab_common_get_goal_value():
    df_h = pd.DataFrame([
        {"Category": "ELSS", "Market Value": 1000.0, "Cap Type": "Flexi Cap", "Fund": "Axis ELSS"},
        {"Category": "Liquid", "Market Value": 2000.0, "Cap Type": "N/A", "Fund": "SBI Liquid"},
        {"Category": "Index", "Market Value": 3000.0, "Cap Type": "Large Cap", "Fund": "UTI Nifty 50"},
        {"Category": "Equity", "Market Value": 4000.0, "Cap Type": "Mid Cap", "Fund": "Motilal Midcap"},
        {"Category": "Equity", "Market Value": 5000.0, "Cap Type": "Small Cap", "Fund": "Nippon Small Cap"},
        {"Category": "Corporate Bond", "Market Value": 6000.0, "Cap Type": "N/A", "Fund": "HDFC Corp Bond"},
        {"Category": "Flexi Cap", "Market Value": 7000.0, "Cap Type": "Flexi Cap", "Fund": "Parag Parikh Flexi Cap"},
    ])

    assert tab_common.get_goal_value(df_h, "ELSS") == 1000.0
    assert tab_common.get_goal_value(df_h, "Liquid") == 2000.0
    assert tab_common.get_goal_value(df_h, "Index") == 3000.0
    assert tab_common.get_goal_value(df_h, "Mid Cap") == 4000.0
    assert tab_common.get_goal_value(df_h, "Small Cap") == 5000.0
    assert tab_common.get_goal_value(df_h, "Debt") == 6000.0
    assert tab_common.get_goal_value(df_h, "Equity") == 7000.0
    assert tab_common.get_goal_value(df_h, "NonExistent") == 0.0

def test_tab_common_prefetch_peer_navs(monkeypatch):
    # Empty
    assert tab_common._prefetch_peer_navs([]) == {}

    # Populated with error handling
    def mock_fetch(code, days):
        if code == "ERR":
            raise RuntimeError("API Fail")
        return pd.Series([10.0, 11.0], index=pd.date_range("2024-01-01", periods=2))

    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", mock_fetch)
    res = tab_common._prefetch_peer_navs(["12345", "ERR", "12345"])
    assert "12345" in res and not res["12345"].empty
    assert "ERR" in res and res["ERR"].empty

def test_tab_common_get_diverse_category_peers(monkeypatch):
    MARKET_CACHE.clear()

    # Mock search
    def mock_search(q):
        if "Large Cap" in q:
            return [
                {"symbol": "1001", "name": "HDFC Top 100 Direct Plan Growth"},
                {"symbol": "1002", "name": "SBI Bluechip Direct Growth"},
                {"symbol": "1003", "name": "ICICI Prudential Large Cap Direct Growth"},
            ]
        return []

    # Mock nav series
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    monkeypatch.setattr(tab_common, "search_mutual_funds", mock_search)
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.55)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda code, days: mock_series)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 15.0, "3Y": 12.0, "5Y": 14.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 8.5)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 3.2, "sharpe": 1.1})

    peers, fallback = tab_common.get_diverse_category_peers("Large Cap", max_peers=2)
    assert len(peers) == 2
    assert fallback is False
    assert peers[0]["alpha_str"] == "+3.2%"

def test_tab_common_peer_fallback_and_veteran_harvest(monkeypatch):
    MARKET_CACHE.clear()
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    def mock_search(q):
        if q == "Mid Cap Direct":
            return []
        if "Flexi Cap Direct" in q or "Large Cap Direct" in q:
            return [
                {"symbol": "9001", "name": "Axis Flexi Cap Direct Growth"},
                {"symbol": "9002", "name": "SBI Flexi Cap Direct Growth"},
            ]
        if "Large Cap Fund" in q:
            return [
                {"symbol": "8001", "name": "Fallback Large Cap Direct Growth"},
            ]
        return [
            {"symbol": "7001", "name": "Some Regular Plan Growth"},
        ]

    monkeypatch.setattr(tab_common, "search_mutual_funds", mock_search)
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.65)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda code, days: mock_series)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 12.0, "3Y": 11.0, "5Y": 10.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 7.0)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 1.0, "sharpe": 0.8})

    peers, fallback = tab_common.get_diverse_category_peers("Mid Cap", max_peers=2, base_fund_name="Axis Flexi")
    assert fallback is True
    assert len(peers) >= 1

def test_tab_common_skips_zero_5y_peers(monkeypatch):
    MARKET_CACHE.clear()
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    monkeypatch.setattr(
        tab_common,
        "search_mutual_funds",
        lambda q: [{"symbol": "1001", "name": "HDFC Large Cap Direct Growth"}],
    )
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.55)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda code, days: mock_series)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 10.0, "3Y": 9.0, "5Y": 0.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 5.0)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 0.0, "sharpe": 0.5})

    peers, _ = tab_common.get_diverse_category_peers("Large Cap", max_peers=2)
    assert peers == []

def test_tab_common_peer_cap_and_self_skip(monkeypatch):
    MARKET_CACHE.clear()
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    many = [
        {"symbol": str(i), "name": f"AMC{i} Large Cap Direct Growth"}
        for i in range(35)
    ]

    monkeypatch.setattr(tab_common, "search_mutual_funds", lambda q: many if "Large Cap" in q else [])
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.55)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda code, days: mock_series)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 15.0, "3Y": 12.0, "5Y": 14.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 8.0)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 1.0, "sharpe": 1.0})

    peers, _ = tab_common.get_diverse_category_peers("Large Cap", max_peers=5, base_fund_name="AMC0 Large Cap")
    assert len(peers) <= 5
    assert all("AMC0" not in p["name"] for p in peers)

def test_tab_common_fallback_peer_cap(monkeypatch):
    MARKET_CACHE.clear()
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    fallback = [
        {"symbol": str(i), "name": f"Fallback AMC{i} Large Cap Direct Growth"}
        for i in range(20)
    ]

    def mock_search(q):
        if q == "Small Cap Direct":
            return []
        if "Small Cap Fund" in q:
            return fallback
        return []

    monkeypatch.setattr(tab_common, "search_mutual_funds", mock_search)
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.65)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda code, days: mock_series)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 12.0, "3Y": 11.0, "5Y": 10.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 7.0)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 1.0, "sharpe": 0.8})

    peers, fallback_used = tab_common.get_diverse_category_peers("Small Cap", max_peers=3)
    assert fallback_used is True
    assert len(peers) <= 3

def test_tab_common_skips_empty_prefetched_nav(monkeypatch):
    MARKET_CACHE.clear()
    dates = pd.date_range("2019-01-01", periods=100, freq="ME")
    mock_series = pd.Series(np.linspace(10.0, 25.0, 100), index=dates)

    monkeypatch.setattr(
        tab_common,
        "search_mutual_funds",
        lambda q: [
            {"symbol": "1001", "name": "HDFC Large Cap Direct Growth"},
            {"symbol": "1002", "name": "SBI Large Cap Direct Growth"},
        ],
    )
    monkeypatch.setattr(tab_common, "fetch_fund_ter", lambda code: 0.55)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda ticker, days: mock_series)

    def nav_by_code(code, days):
        return mock_series if code == "1001" else pd.Series(dtype=float)

    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", nav_by_code)
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"1Y": 15.0, "3Y": 12.0, "5Y": 14.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda s, b: 8.0)
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda s, b, risk_free_rate: {"alpha": 1.0, "sharpe": 1.0})

    peers, _ = tab_common.get_diverse_category_peers("Large Cap", max_peers=2)
    assert len(peers) == 1


def test_tab_common_compute_diverse_peers_fallback(monkeypatch):
    from domains.mutual_funds import tab_common

    def search_mutual_funds(q):
        if q == "Large Cap Fund":
            return [{"symbol": str(i), "name": f"Peer {i} Direct Growth"} for i in range(20)]
        return []

    monkeypatch.setattr("shared.services.market_data.search_mutual_funds", search_mutual_funds)
    monkeypatch.setattr(tab_common, "search_mutual_funds", search_mutual_funds)
    monkeypatch.setattr(tab_common, "_extract_amc", lambda name: "AMC")
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", lambda *a, **k: pd.Series(
        [10.0, 12.0], index=pd.date_range("2020-01-01", periods=2, freq="ME"),
    ))
    monkeypatch.setattr(tab_common, "_prefetch_peer_navs", lambda codes: {
        c: pd.Series([10.0, 12.0], index=pd.date_range("2020-01-01", periods=2, freq="ME"))
        for c in codes
    })
    monkeypatch.setattr(tab_common, "compute_trailing_returns", lambda s: {"5Y": 10.0, "1Y": 5.0, "3Y": 8.0})
    monkeypatch.setattr(tab_common, "compute_risk_metrics", lambda *a, **k: {"sharpe": 1.0})
    monkeypatch.setattr(tab_common, "compute_consistency_score", lambda *a, **k: 80.0)
    monkeypatch.setattr(tab_common.MARKET_CACHE, "get_or_compute", lambda k, fn, ttl: fn())
    peers, fb = tab_common._compute_diverse_category_peers("Large Cap Fund", "Base Fund", 1)
    assert fb is True
