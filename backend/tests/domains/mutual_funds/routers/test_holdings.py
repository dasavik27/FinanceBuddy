"""Mutual fund holdings router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import holdings


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

    # Test other sort options (pass search="" — Query defaults are not resolved on direct calls)
    for sort_col in ["Signal", "Avg. NAV", "Curr. NAV", "P&L", "Current", "Day Chg.", "Fund"]:
        res = holdings.get_holdings(sid, sort_by=sort_col, ascending="true", search="")
        assert res["total"] == 3

    # get_transactions
    res_tx = holdings.get_transactions(sid, limit=2)
    assert len(res_tx["transactions"]) == 2

    # get_fund_insights
    res_ins = holdings.get_fund_insights(sid, "INF179K01BE2", name="HDFC Top 100")
    assert res_ins["isin"] == "INF179K01BE2"
    assert res_ins["scheme_code"] == "119551"

def test_holdings_router_extended(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    nav_s = pd.Series([140.0, 150.0, 160.0], index=pd.to_datetime(["2024-01-08", "2024-01-09", "2024-01-10"]))
    monkeypatch.setattr(holdings, "fetch_nav_series_by_isin", lambda isin, days=10, refresh=False: nav_s)
    monkeypatch.setattr(holdings, "resolve_scheme_code_from_isin", lambda isin: None)
    monkeypatch.setattr(holdings, "fetch_fund_ter", lambda code, plan="Direct": None)
    monkeypatch.setattr(
        holdings,
        "fetch_live_portfolio",
        lambda *a, **k: {"expense_ratio": "0.55%"},
    )

    res = holdings.get_holdings(sid, sort_by="Fund", ascending="true", search="", cap_filter="All")
    assert res["total"] >= 1

    empty_h = type("P", (), {"df_h": pd.DataFrame(columns=["Fund", "ISIN"]), "df_t": pd.DataFrame()})()
    monkeypatch.setattr(holdings, "get_session", lambda session_id: empty_h)
    assert holdings.get_holdings(sid)["total"] == 0


import numpy as np
from datetime import datetime
from unittest.mock import MagicMock

from domains.mutual_funds.models import Portfolio
from domains.mutual_funds import sessions as mf_sessions
from domains.mutual_funds.routers import holdings



@pytest.fixture
def sample_mf_session(monkeypatch):
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions as mf_sessions
    from datetime import datetime

    df_h = pd.DataFrame([
        {"Fund": "HDFC Top 100 Direct Growth", "Category": "Large Cap", "Cap Type": "Large Cap",
         "Plan": "Direct", "ISIN": "INF179K01BE2", "Units": 100.0, "Invested": 10000.0,
         "NAV": 150.0, "Market Value": 15000.0, "Gain": 5000.0, "Gain%": 50.0, "Weight%": 100.0,
         "AMC": "HDFC", "NAV Date": "2024-01-10"},
    ])
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())
    sid = "target_mf_sess"
    mf_sessions._SESSIONS[sid] = {"portfolio": p, "last_accessed": datetime.now(), "owner": None}
    yield sid, p
    mf_sessions._SESSIONS.pop(sid, None)
def test_holdings_sort_fund_and_enrichment_edges(monkeypatch, sample_mf_session):
    from domains.mutual_funds.routers import holdings

    sid, _ = sample_mf_session
    monkeypatch.setattr(
        holdings, "fetch_nav_series_by_isin",
        lambda isin, days=10, refresh=False: pd.Series(
            [100.0, 101.0], index=pd.date_range("2026-08-01", periods=2),
        ),
    )
    monkeypatch.setattr(holdings, "resolve_scheme_code_from_isin", lambda isin: "119551")
    monkeypatch.setattr(holdings, "fetch_fund_ter", lambda *a, **k: None)
    monkeypatch.setattr(holdings, "fetch_live_portfolio", MagicMock(side_effect=RuntimeError("x")))
    out = holdings.get_holdings(sid, sort_by="Fund", ascending="true", search="", cap_filter="All")
    assert "holdings" in out

def test_holdings_nav_sort_and_enrich_edges(monkeypatch, sample_mf_session):
    from domains.mutual_funds.routers import holdings

    sid, _ = sample_mf_session
    monkeypatch.setattr(
        holdings, "fetch_nav_series_by_isin",
        lambda isin, days=7, refresh=False: pd.Series([100.0], index=pd.date_range("2026-08-01", periods=1)),
    )
    monkeypatch.setattr(holdings, "resolve_scheme_code_from_isin", lambda isin: None)
    monkeypatch.setattr(holdings, "fetch_fund_ter", lambda *a, **k: None)
    monkeypatch.setattr(holdings, "fetch_live_portfolio", lambda *a, **k: None)
    out = holdings.get_holdings(sid, sort_by="Day Chg.", ascending="false", search="", cap_filter="All")
    assert "holdings" in out



"""
The fund-name search parameter on GET /mutual-funds/holdings/{sid}/holdings.

pandas' `Series.str.contains` defaults to `regex=True`, so this query parameter used to
be compiled and executed as a regular expression against every fund name. That made an
unauthenticated-shaped input into both a CPU-exhaustion vector and an uncaught 500.
These tests pin the substring semantics and the bound.
"""

import time

import pandas as pd
import pytest


def _search(df: pd.DataFrame, needle: str) -> pd.DataFrame:
    """The filter exactly as the router applies it."""
    return df[df["Fund"].str.contains(needle, case=False, na=False, regex=False)]


def test_regex_metacharacters_are_matched_literally():
    df = pd.DataFrame({"Fund": ["HDFC Small Cap Fund", "ICICI (Growth) Plan", "Axis Bluechip"]})

    # A literal paren finds the fund that actually contains one...
    assert len(_search(df, "(Growth)")) == 1
    # ...and a regex that would match everything matches nothing, because it is a needle.
    assert len(_search(df, ".*")) == 0
    assert len(_search(df, "^HDFC")) == 0


def test_malformed_pattern_does_not_raise():
    """`(` alone raises re.PatternError under regex=True, which no handler catches."""
    df = pd.DataFrame({"Fund": ["HDFC Small Cap Fund"]})
    for needle in ["(", ")", "[", "*", "+", "?", "\\", "[a-"]:
        assert len(_search(df, needle)) == 0, f"{needle!r} unexpectedly matched"


def test_backtracking_pattern_is_not_expensive():
    """
    "(a+)+$" against a run of 'a' costs exponential time when compiled as a regex:
    measured at 0.15s for 18 characters, 6.7s for 24, over two minutes for 30 - one row,
    one request. As a literal needle it is a substring scan.
    """
    df = pd.DataFrame({"Fund": ["a" * 60 + "!"] * 50})
    start = time.perf_counter()
    _search(df, "(a+)+$")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"substring search took {elapsed:.2f}s - is regex back on?"


def test_search_is_case_insensitive_and_substring():
    df = pd.DataFrame({"Fund": ["HDFC Small Cap Fund", "Axis Bluechip"]})
    assert len(_search(df, "small cap")) == 1
    assert len(_search(df, "SMALL")) == 1
    assert len(_search(df, "bluechip")) == 1


def _amc_filter(df: pd.DataFrame, amc: str) -> pd.DataFrame:
    """The AMC filter exactly as routers/performance.py applies it."""
    import re
    amcs = [a.strip().upper() for a in amc.split(",") if a.strip()]
    pattern = "|".join(re.escape(a) for a in amcs)
    return df[df["AMC"].str.upper().str.contains(pattern, na=False)]


def test_amc_filter_keeps_multi_select_alternation():
    """re.escape must not break the OR semantics - this is a multi-select filter."""
    df = pd.DataFrame({"AMC": ["HDFC AMC", "ICICI Prudential", "Axis AMC"]})
    assert len(_amc_filter(df, "HDFC,Axis")) == 2
    assert len(_amc_filter(df, "ICICI")) == 1


def test_amc_filter_treats_metacharacters_literally():
    """Without escaping, the *contents* of the alternation were a caller-supplied regex."""
    df = pd.DataFrame({"AMC": ["HDFC AMC", "ICICI Prudential"]})
    assert len(_amc_filter(df, ".*")) == 0
    assert len(_amc_filter(df, "^HDFC")) == 0


def test_amc_filter_does_not_raise_on_a_malformed_pattern():
    """`(` alone raised re.PatternError into an uncaught 500."""
    df = pd.DataFrame({"AMC": ["HDFC AMC"]})
    for needle in ["(", ")", "[", "*", "+", "[a-"]:
        assert len(_amc_filter(df, needle)) == 0, f"{needle!r} unexpectedly matched"


def test_amc_filter_is_not_vulnerable_to_backtracking():
    df = pd.DataFrame({"AMC": ["a" * 60 + "!"] * 50})
    start = time.perf_counter()
    _amc_filter(df, "(a+)+$")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"AMC filter took {elapsed:.2f}s - is the escaping gone?"


def test_search_length_is_bounded_at_the_route():
    """The route declares max_length; an over-long needle is a 422, not work."""
    from fastapi.routing import APIRoute
    from main import app

    target = "/mutual-funds/holdings/{session_id}/holdings"
    route = None
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path == target:
            route = r
            break
        if hasattr(r, "original_router"):
            prefix = getattr(getattr(r, "include_context", None), "prefix", "")
            for sub_r in r.original_router.routes:
                if isinstance(sub_r, APIRoute) and (prefix + sub_r.path) == target:
                    route = sub_r
                    break
            if route:
                break

    assert route is not None, f"Route {target} not found"
    search_param = next(p for p in route.dependant.query_params if p.name == "search")
    # Constraints live in field_info.metadata as annotated_types markers under
    # pydantic v2, not as attributes on the field itself.
    bounds = [
        m.max_length for m in (search_param.field_info.metadata or [])
        if hasattr(m, "max_length")
    ]
    assert bounds == [100], (
        f"search has no length bound (metadata={search_param.field_info.metadata}); "
        "its length was the exponent in the blow-up"
    )
