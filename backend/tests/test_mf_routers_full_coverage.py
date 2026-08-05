"""
test_mf_routers_full_coverage.py

Comprehensive tests for mutual funds routers:
- overview.py
- portfolio.py
- holdings.py
- insights.py
- journey.py
- planning.py
- rebalance.py
- performance.py
"""

import io
import math
from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.models import Portfolio
from domains.mutual_funds.routers import (
    overview, portfolio, holdings, insights, journey, planning, rebalance, performance,
)
from domains.mutual_funds import sessions
from shared.cache import MarketCache


@pytest.fixture
def sample_portfolio_session(monkeypatch):
    """Sets up a registered mock portfolio in session memory."""
    dates = pd.date_range("2023-01-01", periods=10, freq="ME")
    df_h = pd.DataFrame([
        {
            "Fund": "HDFC Top 100 Direct Growth",
            "Category": "Large Cap",
            "Cap Type": "Large Cap",
            "Plan": "Direct",
            "ISIN": "INF179K01BE2",
            "Units": 100.0,
            "Invested": 10000.0,
            "NAV": 150.0,
            "Market Value": 15000.0,
            "Gain": 5000.0,
            "Gain%": 50.0,
            "Weight%": 30.0,
            "AMC": "HDFC",
            "NAV Date": "2024-01-10",
        },
        {
            "Fund": "Nippon India Small Cap Regular Growth",
            "Category": "Small Cap",
            "Cap Type": "Small Cap",
            "Plan": "Regular",
            "ISIN": "INF204K01E03",
            "Units": 200.0,
            "Invested": 20000.0,
            "NAV": 125.0,
            "Market Value": 25000.0,
            "Gain": 5000.0,
            "Gain%": 25.0,
            "Weight%": 50.0,
            "AMC": "Nippon",
            "NAV Date": "2024-01-10",
        },
        {
            "Fund": "SBI Liquid Direct Growth",
            "Category": "Liquid",
            "Cap Type": "Liquid",
            "Plan": "Direct",
            "ISIN": "INF200K01VA7",
            "Units": 10.0,
            "Invested": 10000.0,
            "NAV": 1000.0,
            "Market Value": 10000.0,
            "Gain": 0.0,
            "Gain%": 0.0,
            "Weight%": 20.0,
            "AMC": "SBI",
            "NAV Date": "2024-01-10",
        },
    ])

    df_t = pd.DataFrame([
        {
            "Fund": "HDFC Top 100 Direct Growth",
            "Date": pd.Timestamp("2023-01-15"),
            "Type": "PURCHASE_SIP",
            "Units": 100.0,
            "NAV": 100.0,
            "Amount": 10000.0,
        },
        {
            "Fund": "Nippon India Small Cap Regular Growth",
            "Date": pd.Timestamp("2023-02-15"),
            "Type": "PURCHASE_SIP",
            "Units": 200.0,
            "NAV": 100.0,
            "Amount": 20000.0,
        },
        {
            "Fund": "SBI Liquid Direct Growth",
            "Date": pd.Timestamp("2023-03-15"),
            "Type": "PURCHASE",
            "Units": 10.0,
            "NAV": 1000.0,
            "Amount": 10000.0,
        },
    ])

    df_s = pd.DataFrame([
        {"Fund": "HDFC Top 100 Direct Growth", "Date": "15-01-2023", "Amount": 5000.0},
        {"Fund": "Nippon India Small Cap Regular Growth", "Date": "15-02-2023", "Amount": 5000.0},
    ])

    from datetime import datetime
    p = Portfolio(df_h=df_h, df_t=df_t, df_s=df_s)
    sid = "test_mf_session_123"
    sessions._SESSIONS[sid] = {
        "portfolio": p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    return sid, p


# ── 1. Overview Router Tests ──
def test_overview_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    bench_series = pd.Series([100.0, 105.0, 110.0], index=pd.date_range("2023-01-01", periods=3))
    monkeypatch.setattr(overview, "fetch_benchmark_series", lambda t, d, refresh=False: bench_series)
    monkeypatch.setattr(
        overview,
        "cached_period_comparison",
        lambda *args, **kwargs: {
            "dates": ["2023-01-01", "2023-01-02"],
            "portfolio": [100.0, 110.0],
            "benchmark": [100.0, 105.0],
            "port_pct": 10.0,
            "bench_pct": 5.0,
            "port_value": 50000.0,
            "bench_value": 45000.0,
            "use_xirr": False,
        },
    )

    # get_summary
    resp_sum = overview.get_summary(sid, "Nifty 50")
    assert resp_sum.status_code == 200

    # get_overview
    resp_ov = overview.get_overview(sid, period="1Y", benchmark="Nifty 50")
    assert resp_ov.status_code == 200

    # get_benchmark_overlay (with benchmarks)
    resp_bm = overview.get_benchmark_overlay(sid, period="1Y", benchmarks="Nifty 50,S&P 500")
    assert resp_bm.status_code == 200

    # get_benchmark_overlay (empty benchmarks)
    resp_bm_empty = overview.get_benchmark_overlay(sid, period="1Y", benchmarks="")
    assert resp_bm_empty.status_code == 200

    # get_allocation
    resp_alloc = overview.get_allocation(sid)
    assert resp_alloc.status_code == 200


# ── 2. Portfolio Router Tests ──
def test_portfolio_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # parse_cas: file oversized
    oversized = UploadFile(filename="big.pdf", file=io.BytesIO(b"0" * (8 * 1024 * 1024 + 10)))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=oversized)
    assert exc.value.status_code == 422

    # parse_cas: empty file
    empty_f = UploadFile(filename="empty.pdf", file=io.BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=empty_f)
    assert exc.value.status_code == 422

    # parse_cas: missing password and no profile pan
    monkeypatch.setattr("shared.identity.current_pan", lambda: None)
    valid_f = UploadFile(filename="stmt.pdf", file=io.BytesIO(b"dummy pdf content"))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password=None)
    assert exc.value.status_code == 400

    # parse_cas: parse error
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (None, None, None, "Invalid PDF", False, None))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password="ABCDE1234F")
    assert exc.value.status_code == 422

    # parse_cas: empty holdings
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, False, None))
    with pytest.raises(HTTPException) as exc:
        portfolio.parse_cas(file=valid_f, password="ABCDE1234F")
    assert exc.value.status_code == 422

    # parse_cas: success
    caller_mock = MagicMock(user_id="u1", pan="OLD_PAN")
    monkeypatch.setattr("shared.identity.current_caller", lambda: caller_mock)
    pan_saved = []
    monkeypatch.setattr("shared.users.set_pan", lambda uid, pan: pan_saved.append((uid, pan)))
    monkeypatch.setattr(portfolio, "parse_cas_file", lambda raw, pw: (p.df_h, p.df_t, p.df_s, None, False, "2023-2024"))
    monkeypatch.setattr(portfolio, "create_session", lambda *args, **kwargs: "new_session_999")

    res_parse = portfolio.parse_cas(file=valid_f, password="NEW_PAN_1234F")
    assert res_parse["session_id"] == "new_session_999"
    assert ("u1", "NEW_PAN_1234F") in pan_saved

    # sync_portfolio
    monkeypatch.setattr("shared.services.market_data.resolve_scheme_code_from_isin", lambda isin: "12345")
    res_sync = portfolio.sync_portfolio(sid)
    assert res_sync["status"] == "ok"
    assert res_sync["cleared"] > 0

    # sync_portfolio on empty
    from datetime import datetime
    empty_p = Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame())
    sessions._SESSIONS["empty_sid"] = {
        "portfolio": empty_p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    assert portfolio.sync_portfolio("empty_sid") == {"status": "ok", "cleared": 0}


# ── 3. Holdings Router Tests ──
def test_holdings_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # Mock market data
    nav_s = pd.Series([140.0, 150.0], index=pd.to_datetime(["2024-01-09", "2024-01-10"]))
    monkeypatch.setattr(holdings, "fetch_nav_series_by_isin", lambda isin, days=10, refresh=False: nav_s)
    monkeypatch.setattr(holdings, "resolve_scheme_code_from_isin", lambda isin: "119551")
    monkeypatch.setattr(holdings, "fetch_fund_ter", lambda code, plan="Direct": 0.45)
    monkeypatch.setattr(holdings, "fetch_fund_metadata", lambda code: {"scheme_name": "HDFC Top 100", "scheme_category": "Large Cap", "fund_house": "HDFC", "scheme_type": "Open Ended"})
    monkeypatch.setattr(holdings, "fetch_live_portfolio", lambda isin, cat, name, refresh=False: {"expense_ratio": "0.45%", "aum": "30,000 Cr", "sectors": [], "holdings": []})

    # get_holdings with sorting
    res_h = holdings.get_holdings(sid, sort_by="Market Value", ascending="false", search="HDFC", cap_filter="Large Cap")
    assert len(res_h["holdings"]) == 1
    assert res_h["holdings"][0]["Fund"] == "HDFC Top 100 Direct Growth"

    # Test other sort options
    for sort_col in ["Signal", "Avg. NAV", "Curr. NAV", "P&L", "Current", "Day Chg.", "Fund"]:
        res = holdings.get_holdings(sid, sort_by=sort_col, ascending="true")
        assert res["total"] == 3

    # get_transactions
    res_tx = holdings.get_transactions(sid, limit=2)
    assert len(res_tx["transactions"]) == 2

    # get_fund_insights
    res_ins = holdings.get_fund_insights(sid, "INF179K01BE2", name="HDFC Top 100")
    assert res_ins["isin"] == "INF179K01BE2"
    assert res_ins["scheme_code"] == "119551"


# ── 4. Insights Router Tests ──
def test_insights_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    res_ins = insights.get_insights(sid)
    assert "score" in res_ins
    assert "score_breakdown" in res_ins
    assert "nudges" in res_ins
    assert len(res_ins["score_breakdown"]) == 5


# ── 5. Journey Router Tests ──
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


# ── 6. Planning Router Tests ──
def test_planning_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # get_tax_harvest
    res_tax = planning.get_tax_harvest(sid)
    assert isinstance(res_tax, dict)

    # get_sip_projection (default monthly_sip from df_s)
    res_sip = planning.get_sip_projection(sid, years=5, annual_return=12.0, stepup_pct=10.0, monthly_sip=0.0)
    assert "projected_corpus" in res_sip or "future_value" in res_sip or "assumed_monthly_sip" in res_sip

    # get_xirr_by_fy
    monkeypatch.setattr("domains.mutual_funds.derived.cached_xirr_by_fy", lambda df_t, df_h: [{"fy": "FY24", "xirr": 15.0}])
    res_fy = planning.get_xirr_by_fy(sid)
    assert "fy_series" in res_fy

    # get_sip_attribution
    res_attr = planning.get_sip_attribution(sid)
    assert isinstance(res_attr, dict)

    # get_mandate_overlap
    res_mo = planning.get_mandate_overlap(sid)
    assert isinstance(res_mo, dict)

    # get_what_if
    monkeypatch.setattr(planning, "fetch_nav_series_by_code", lambda code, days: pd.Series([10.0, 20.0], index=pd.date_range("2020-01-01", periods=2)))
    res_whatif = planning.get_what_if(sid, scheme_code="119551", monthly_amount=5000.0, years=3)
    assert "invested" in res_whatif or "future_value" in res_whatif or "total_invested" in res_whatif or "error" not in res_whatif

    # get_what_if empty
    monkeypatch.setattr(planning, "fetch_nav_series_by_code", lambda code, days: pd.Series([], dtype=float))
    assert "error" in planning.get_what_if(sid, scheme_code="119551")


# ── 7. Rebalance Router Tests ──
def test_rebalance_router(sample_portfolio_session):
    sid, p = sample_portfolio_session

    # Balanced profile
    res_plan = rebalance.get_rebalance_plan(sid, profile="Balanced")
    assert "drift_score" in res_plan
    assert "orders" in res_plan

    # Auto profile (which will detect Aggressive/Balanced/Conservative)
    res_auto = rebalance.get_rebalance_plan(sid, profile="Auto")
    assert "drift_score" in res_auto

    # Aggressive profile (triggers intra-equity check)
    res_agg = rebalance.get_rebalance_plan(sid, profile="Aggressive")
    assert "drift_score" in res_agg

    # Empty portfolio
    from datetime import datetime
    empty_p = Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame())
    sessions._SESSIONS["empty_sid"] = {
        "portfolio": empty_p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    assert rebalance.get_rebalance_plan("empty_sid")["status"] == "Empty"


# ── 8. Performance Router Tests ──
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
    monkeypatch.setattr(performance, "fetch_benchmark_series", lambda t, d, refresh=False: s)
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
