"""
test_cache_headers_routes_mocked.py

Mock-based equivalents of test_cache_headers_routes.py.
Verifies that user-derived routes never emit `public` Cache-Control headers,
default cache policies fail closed, and the benchmark overlay uses private caching.
"""

import uuid
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from domains.mutual_funds import sessions as mf_sessions
from domains.mutual_funds.models import Portfolio
from shared.services.cache import CACHE_CONFIG, get_cache_headers
from shared import identity
from shared.identity import Caller

OWNER_USER_ID = "00000000-0000-0000-0000-0000000000ff"


@pytest.fixture
def client():
    return TestClient(app)


def _cache_control(resp) -> str:
    return resp.headers.get("cache-control", "")


@pytest.fixture
def resident_session(monkeypatch):
    """
    Register an in-memory session owned by the test caller so
    benchmark-overlay executes without needing Postgres or network.
    """
    from shared.services import market_indices

    monkeypatch.setattr(
        market_indices, "fetch_benchmark_series",
        lambda *a, **k: pd.Series(dtype=float),
    )
    monkeypatch.setattr(
        "domains.mutual_funds.routers.overview.fetch_benchmark_series",
        lambda *a, **k: pd.Series(dtype=float),
    )

    df_h = pd.DataFrame([{
        "Fund": "Test Fund", "ISIN": "INF000000001", "Units": 100.0, "NAV": 100.0,
        "Market Value": 10000.0, "Invested": 9000.0, "Category": "Flexi Cap",
    }])
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-01-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 100.0, "Amount": 9000.0, "NAV": 90.0,
    }])

    sid = str(uuid.uuid4())
    portfolio = Portfolio(df_h, df_t, pd.DataFrame(), False)
    mf_sessions._remember(sid, portfolio, owner=OWNER_USER_ID)
    yield sid
    mf_sessions.forget(sid)


def test_benchmark_overlay_is_not_publicly_cacheable_mocked(client, signed_in, resident_session):
    resp = client.get(
        f"/mutual-funds/overview/{resident_session}/benchmark-overlay",
        headers=signed_in,
    )
    assert resp.status_code == 200
    cc = _cache_control(resp).lower()
    assert cc
    assert "public" not in cc
    assert "private" in cc or "no-store" in cc


def test_overview_route_uses_private_policy_type():
    assert CACHE_CONFIG["holdings_detail"]["visibility"] in ("private", "no-store")
    assert "public" not in get_cache_headers("holdings_detail")


USER_DATA_ROUTES = [
    "/mutual-funds/overview/nope/summary",
    "/mutual-funds/overview/nope/allocation",
    "/mutual-funds/overview/nope/benchmark-overlay",
    "/mutual-funds/holdings/nope/holdings",
    "/mutual-funds/performance/nope/performance",
    "/tax-expert/nope/tax/summary",
    "/tax-expert/nope/tax/income",
    "/tax-expert/nope/tax/capital-gains",
    "/history/",
]


@pytest.mark.parametrize("path", USER_DATA_ROUTES)
def test_user_data_routes_are_never_publicly_cacheable_mocked(client, path):
    resp = client.get(path)
    assert "public" not in _cache_control(resp).lower()


@pytest.mark.parametrize("path", USER_DATA_ROUTES)
def test_user_data_routes_always_carry_cache_control_header_mocked(client, path):
    assert _cache_control(client.get(path)) != ""


def test_health_is_still_reachable_and_not_broken_by_middleware(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert _cache_control(resp) == "no-store"
