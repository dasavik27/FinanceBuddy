"""Mutual fund journey router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import journey


def test_journey_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    monkeypatch.setattr(journey, "fetch_benchmark_series", lambda t, d: pd.Series([100.0, 105.0], index=pd.date_range("2023-01-01", periods=2)))
    monkeypatch.setattr(
        journey,
        "cached_period_comparison",
        lambda *args, **kwargs: {
            "dates": ["2023-01-15", "2023-02-15", "2023-03-15"],
            "market_value": [10000.0, 30000.0, 50000.0],
        },
    )

    res_j = journey.get_journey_data(sid)
    assert res_j["status"] == "success"
    assert len(res_j["monthly_flows"]) > 0
    assert len(res_j["capital_curve"]) > 0
    assert len(res_j["best_funds"]) > 0

def test_journey_router_fallback(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    def fail_comparison(*a, **k):
        raise RuntimeError("curve fail")

    monkeypatch.setattr(journey, "fetch_benchmark_series", lambda t, d: pd.Series([100.0], index=pd.date_range("2023-01-01", periods=1)))
    monkeypatch.setattr(journey, "cached_period_comparison", fail_comparison)
    out = journey.get_journey_data(sid)
    assert out["status"] == "success"
    assert out["capital_curve"]

    redeem_t = p.df_t.copy()
    redeem_t = pd.concat([redeem_t, pd.DataFrame([{
        "Fund": "HDFC Top 100 Direct Growth",
        "Date": pd.Timestamp("2023-06-15"),
        "Type": "REDEMPTION",
        "Units": -10.0,
        "NAV": 120.0,
        "Amount": -1200.0,
    }])])
    redeem_p = type("P", (), {"df_h": p.df_h, "df_t": redeem_t, "total_value": 50000.0})()
    monkeypatch.setattr(journey, "get_session", lambda session_id: redeem_p)
    monkeypatch.setattr(
        journey,
        "cached_period_comparison",
        lambda *a, **k: {"dates": ["2023-01-15"], "market_value": [15000.0]},
    )
    out2 = journey.get_journey_data(sid)
    assert out2["monthly_flows"]

    opening_t = pd.DataFrame([{
        "Fund": "HDFC Top 100 Direct Growth",
        "Date": pd.Timestamp("2023-01-01"),
        "Type": "Opening Balance",
        "Units": 0.0,
        "NAV": 0.0,
        "Amount": 0.0,
    }])
    open_p = type("P", (), {"df_h": p.df_h, "df_t": opening_t, "total_value": 50000.0})()
    monkeypatch.setattr(journey, "get_session", lambda session_id: open_p)
    monkeypatch.setattr(journey, "cached_period_comparison", fail_comparison)
    assert journey.get_journey_data(sid)["status"] == "success"


def test_journey_curve_fail_fallback(monkeypatch, sample_portfolio_session):
    from domains.mutual_funds.routers import journey

    sid, _ = sample_portfolio_session
    monkeypatch.setattr("shared.services.market_indices.fetch_benchmark_series", lambda *a, **k: pd.Series([100.0], index=pd.to_datetime(["2024-01-01"])))
    monkeypatch.setattr("domains.mutual_funds.derived.cached_period_comparison", MagicMock(side_effect=Exception("curve fail")))
    jout = journey.get_journey_data(sid)
    assert jout["status"] == "success"


def test_journey_empty_market_curve_raises_into_fallback(monkeypatch, sample_portfolio_session):
    """Empty dates/values from comparison hits the empty-curve raise then capital fallback."""
    from domains.mutual_funds.routers import journey

    sid, _ = sample_portfolio_session
    monkeypatch.setattr(journey, "fetch_benchmark_series", lambda *a, **k: pd.Series([100.0], index=pd.to_datetime(["2024-01-01"])))
    monkeypatch.setattr(
        journey,
        "cached_period_comparison",
        lambda *a, **k: {"dates": [], "market_value": []},
    )
    out = journey.get_journey_data(sid)
    assert out["status"] == "success"
    assert "capital_curve" in out
