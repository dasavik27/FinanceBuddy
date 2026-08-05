"""
test_mf_tab_common_and_compare_full.py

Comprehensive unit tests for:
- domains/mutual_funds/tab_common.py (peer prefetching, diverse peer generation, metric comparisons, series formatting, goal allocations, rollups)
- domains/mutual_funds/routers/compare.py (benchmark listing, search, history, peers endpoint, head-to-head metrics)
"""

from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds import tab_common
from domains.mutual_funds.routers import compare
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


def test_compare_router_endpoints(monkeypatch):
    # 1. list_benchmarks
    res_list = compare.list_benchmarks()
    assert "benchmarks" in res_list and len(res_list["benchmarks"]) > 0

    # 2. search_ticker
    monkeypatch.setattr(compare, "get_nse_indices", lambda q: [{"symbol": "^NSEI", "name": "Nifty 50"}])
    monkeypatch.setattr(compare, "search_mutual_funds", lambda q: [{"symbol": "123", "name": "Fund X"}])
    res_search = compare.search_ticker("Nifty")
    assert len(res_search["results"]) == 2

    # 3. get_history
    monkeypatch.setattr(compare, "fetch_benchmark_series", lambda t, d: pd.Series([], dtype=float))
    assert compare.get_history("TICKER") == {"dates": [], "values": []}

    dates = pd.date_range("2025-01-01", periods=3)
    s = pd.Series([100.0, 110.0, 105.0], index=dates)
    monkeypatch.setattr(compare, "fetch_benchmark_series", lambda t, d: s)
    res_hist = compare.get_history("TICKER")
    assert len(res_hist["dates"]) == 3
    assert res_hist["values"] == [100.0, 110.0, 105.0]

    # 4. get_category_peers
    monkeypatch.setattr(
        "domains.mutual_funds.tab_common.get_diverse_category_peers",
        lambda cat: ([{"name": "Peer 1"}], False),
    )
    res_peers = compare.get_category_peers("Large Cap")
    assert len(res_peers["peers"]) == 1

    # 5. get_comparison_metrics
    # Empty case
    monkeypatch.setattr(compare, "fetch_nav_series_by_code", lambda code, days: pd.Series([], dtype=float))
    assert compare.get_comparison_metrics("1001", "1002") == {"wins": {"A": 0, "B": 0}, "metrics": []}

    # Populated head-to-head comparison
    dates = pd.date_range("2020-01-01", periods=100, freq="ME")
    s1 = pd.Series(np.linspace(10.0, 30.0, 100), index=dates)
    s2 = pd.Series(np.linspace(10.0, 20.0, 100), index=dates)

    monkeypatch.setattr(
        "shared.services.market_data.fetch_nav_series_by_code",
        lambda code, days: s1 if code == "1001" else s2,
    )
    monkeypatch.setattr(
        "shared.services.market_indices.fetch_benchmark_series",
        lambda t, days: s2,
    )

    res_metrics = compare.get_comparison_metrics("1001", "1002")
    assert "wins" in res_metrics
    assert "metrics" in res_metrics
    assert len(res_metrics["metrics"]) > 0
