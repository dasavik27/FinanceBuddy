"""Tests for equity research engine (VCP / Trend Template)."""

import numpy as np
import pandas as pd
import pytest

from domains.equity.research_engine import evaluate_symbol, list_strategies, run_scan
from domains.equity.research_engine.pivots import argrelextrema
from domains.equity.research_engine.universe import resolve_universe
from domains.equity.research_engine.vcp import evaluate, trend_template


def _synthetic_uptrend(n: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    close = np.linspace(100, 180, n) + np.sin(np.linspace(0, 12, n)) * 1.5
    vol = np.linspace(2_000_000, 400_000, n)
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.012,
            "Low": close * 0.988,
            "Close": close,
            "Volume": vol,
        },
        index=idx,
    )


def test_list_strategies_includes_vcp():
    ids = {s["id"] for s in list_strategies()}
    assert "minervini_vcp" in ids


def test_resolve_universe_nifty_and_custom():
    assert len(resolve_universe("nifty50")) == 50
    assert resolve_universe("custom", ["reliance", "INFY", "INFY"]) == ["RELIANCE", "INFY"]


def test_argrelextrema_finds_peak():
    data = np.array([1.0, 2.0, 5.0, 2.0, 1.0, 0.5, 1.0])
    peaks = argrelextrema(data, np.greater_equal, order=2)
    assert 2 in set(peaks.tolist())


def test_trend_template_passes_strong_uptrend():
    df = _synthetic_uptrend()
    tt = trend_template(df)
    assert tt["passes_template"] is True
    assert tt["passed_count"] >= 8


def test_evaluate_returns_score_payload():
    out = evaluate(_synthetic_uptrend(), rs_percentile=80.0)
    assert out["ok"] is True
    assert out["strategy"] == "minervini_vcp"
    assert out["score"] >= 0
    assert "trend" in out and "vcp" in out


def test_evaluate_symbol_unknown_strategy():
    out = evaluate_symbol("RELIANCE", strategy_id="nope")
    assert out["ok"] is False
    assert "unknown strategy" in out["reason"]


def test_run_scan_monkeypatched(monkeypatch):
    df = _synthetic_uptrend()
    monkeypatch.setattr(
        "domains.equity.research_engine.ohlc.fetch_ohlcv",
        lambda sym, days=500: df,
    )
    out = run_scan(universe="nifty50", symbols=["AAA", "BBB"], limit=2)
    assert out["ok"] is True
    assert out["evaluated"] == 2
    assert len(out["results"]) == 2
    assert out["results"][0]["score"] >= out["results"][1]["score"]


def test_research_router_strategies():
    from domains.equity.routers import research

    body = research.strategies()
    assert any(s["id"] == "minervini_vcp" for s in body["strategies"])


def test_research_router_scan_requires_auth(monkeypatch):
    from fastapi import HTTPException
    from domains.equity.routers import research

    monkeypatch.setattr("domains.equity.routers.research.identity.current_user_id", lambda: None)
    with pytest.raises(HTTPException) as ei:
        research.scan(research.ScanRequest(symbols=["AAA"], limit=1))
    assert ei.value.status_code == 401


def test_research_router_scan_ok(monkeypatch):
    from domains.equity.routers import research

    monkeypatch.setattr("domains.equity.routers.research.identity.current_user_id", lambda: "u1")
    monkeypatch.setattr(
        "domains.equity.routers.research.run_scan",
        lambda **kw: {
            "ok": True,
            "results": [],
            "evaluated": 0,
            "requested": 0,
            "skipped": [],
            "setups": 0,
            "strategy": "minervini_vcp",
            "universe": "custom",
        },
    )
    out = research.scan(research.ScanRequest(symbols=["AAA"], limit=1))
    assert out["ok"] is True
