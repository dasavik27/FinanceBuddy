"""Mutual fund compare router."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds.routers import compare
from shared.services.cache import MARKET_CACHE


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
    empty = compare.get_history("TICKER")
    assert empty["dates"] == []
    assert empty["returns"] == {}

    dates = pd.date_range("2020-01-01", periods=100, freq="ME")
    s = pd.Series(np.linspace(100.0, 150.0, 100), index=dates)
    monkeypatch.setattr(compare, "fetch_benchmark_series", lambda t, d: s)
    monkeypatch.setattr(compare, "fetch_fund_ter", lambda code: 0.42)
    monkeypatch.setattr(compare, "compute_trailing_returns", lambda series: {"1Y": 12.0, "3Y": 15.0})
    monkeypatch.setattr(compare, "compute_risk_metrics", lambda *a, **k: {
        "sharpe": 1.2, "sortino": 1.4, "alpha": 2.0, "beta": 0.9, "vol": 14.0, "max_dd": -18.0,
    })
    monkeypatch.setattr(compare, "compute_consistency_score", lambda *a, **k: 7.5)
    res_hist = compare.get_history("TICKER")
    assert len(res_hist["dates"]) == 100
    assert res_hist["returns"]["1Y"] == 12.0
    assert res_hist["sharpe"] == 1.2
    assert res_hist["day_chg"] is not None

    res_mf = compare.get_history("122639")
    assert res_mf["ter"] == 0.42

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


def test_compare_metrics_from_sweep_gap(monkeypatch, sample_portfolio_session):
    from datetime import datetime
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions as mf_sessions
    from domains.mutual_funds.routers import compare

    sid, p = sample_portfolio_session
    monkeypatch.setattr("shared.services.market_data.fetch_nav_series_by_code", lambda *a, **k: pd.Series(
        [10.0, 11.0], index=pd.date_range("2020-01-01", periods=2, freq="ME"),
    ))
    monkeypatch.setattr("shared.services.market_indices.fetch_benchmark_series", lambda *a, **k: pd.Series(
        [100.0, 105.0], index=pd.date_range("2020-01-01", periods=2, freq="ME"),
    ))
    monkeypatch.setattr("domains.mutual_funds.finance.compute_trailing_returns", lambda s: {"1Y": 5.0, "3Y": 8.0, "5Y": 10.0})
    monkeypatch.setattr("domains.mutual_funds.finance.compute_risk_metrics", lambda *a, **k: {"sharpe": 1.0, "alpha": 2.0, "beta": 0.9})
    monkeypatch.setattr("domains.mutual_funds.finance.compute_consistency_score", lambda *a, **k: 80.0)
    out = compare.get_comparison_metrics("120716", vs="120717", session_id=sid)
    assert "metrics" in out


def test_compare_search_dedupes_and_skips_blank_symbols(monkeypatch):
    monkeypatch.setattr(
        compare,
        "get_nse_indices",
        lambda q: [
            {"symbol": "^NSEI", "name": "Nifty 50"},
            {"symbol": "", "name": "blank"},
            {"symbol": "^nsei", "name": "Nifty 50 dupe"},
        ],
    )
    monkeypatch.setattr(
        compare,
        "search_mutual_funds",
        lambda q: [{"symbol": "122639", "name": "Fund A"}],
    )
    out = compare.search_ticker("nif")
    symbols = [r["symbol"] for r in out["results"]]
    assert symbols == ["^NSEI", "122639"]
    assert out["peers"] == out["results"]


def test_compare_history_ter_exception_and_nifty_benchmark(monkeypatch):
    dates = pd.date_range("2020-01-01", periods=20, freq="ME")
    s = pd.Series(np.linspace(100.0, 120.0, 20), index=dates)

    def _series(ticker, days):
        return s

    monkeypatch.setattr(compare, "fetch_benchmark_series", _series)
    monkeypatch.setattr(
        compare,
        "fetch_fund_ter",
        MagicMock(side_effect=RuntimeError("ter down")),
    )
    monkeypatch.setattr(compare, "compute_trailing_returns", lambda series: {"1Y": 10.0})
    risk_calls = []

    def _risk(series, bench, risk_free_rate=6.5):
        risk_calls.append(bench is series)
        return {
            "sharpe": 1.0, "sortino": 1.1, "alpha": 0.5, "beta": 1.0, "vol": 12.0, "max_dd": -10.0,
        }

    monkeypatch.setattr(compare, "compute_risk_metrics", _risk)
    monkeypatch.setattr(compare, "compute_consistency_score", lambda *a, **k: 6.0)

    broken_ter = compare.get_history("122639")
    assert broken_ter["ter"] is None

    nifty = compare.get_history("Nifty 50")
    assert nifty["dates"]
    assert risk_calls[-1] is True
