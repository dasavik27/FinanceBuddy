"""
Route-level cache-header tests.

tests/test_cache_core.py already pins the *policy table*: user-derived types are
never `public`, unknown types fail closed to `no-store`. That test could not catch
the actual leak found in review, because the bug was not in the table - it was a
router labelling a user-derived payload with a market-data type
(`comparison_data`, which is legitimately `public`).

So these tests assert on the header a route really emits, which is the property
that matters to a CDN.
"""

import sqlite3
import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from shared import storage
from shared.services.cache import CACHE_CONFIG, get_cache_headers

OWNER_PAN = "CCCCC3333C"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "headers_test.sqlite3"
    monkeypatch.setattr(storage, "DB_PATH", str(db))
    storage._init_db()
    yield db


@pytest.fixture
def real_session(isolated_db, monkeypatch):
    """
    A session the overview route can actually render, with the network stubbed.

    Needed so the cache-header assertion exercises the router's own header instead of
    the middleware fallback on a 404.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from shared.services import market_indices

    # No outbound calls from a test: an empty benchmark series is a valid input and
    # keeps the route on its normal code path.
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
    ledger_hash = storage.compute_ledger_hash(df_t, OWNER_PAN)
    storage.save_session(
        sid, df_h, df_t, pd.DataFrame(), is_partial=False,
        pan_id=OWNER_PAN, ledger_hash=ledger_hash,
    )
    mf_sessions.clear_all()
    yield sid
    mf_sessions.clear_all()


def _cache_control(resp) -> str:
    return resp.headers.get("cache-control", "")


# ── B3: the mislabelled benchmark-overlay response ────────────────────────────

def test_benchmark_overlay_is_not_publicly_cacheable(client, real_session):
    """
    /benchmark-overlay returns result["series"]["Portfolio"] - the user's own
    CAS-derived value series. It was labelled `comparison_data` and therefore shipped
    `public, max-age=1800`, authorizing any shared cache to store one user's portfolio
    and serve it to another.

    This uses a REAL session on purpose. An earlier version of this test hit a
    nonexistent session, which meant get_session raised 404 before the header line was
    ever reached - so the header came from the fallback middleware and the test passed
    even with the bug reintroduced. It asserted nothing about the fix.
    """
    resp = client.get(
        f"/mutual-funds/overview/{real_session}/benchmark-overlay",
        headers={"X-User-PAN": OWNER_PAN},
    )
    assert resp.status_code == 200, f"expected the route to actually execute, got {resp.status_code}"
    cc = _cache_control(resp).lower()
    assert cc, "no Cache-Control on a 200 carrying portfolio data"
    assert "public" not in cc, f"portfolio data is shared-cacheable: {cc!r}"
    assert "private" in cc or "no-store" in cc


def test_overview_route_uses_a_private_policy_type():
    """The type the router now names must itself be non-public."""
    assert CACHE_CONFIG["holdings_detail"]["visibility"] in ("private", "no-store")
    assert "public" not in get_cache_headers("holdings_detail")


# ── the default: everything fails closed ──────────────────────────────────────

# Routes that return per-user financial data and must never be shared-cacheable.
# Nonexistent ids are deliberate - the header is set before the body is known, and
# an error response must be no-store too (it can carry a detail message).
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
def test_user_data_routes_are_never_publicly_cacheable(client, path):
    resp = client.get(path)
    assert "public" not in _cache_control(resp).lower(), (
        f"{path} emitted a shared-cacheable header: {_cache_control(resp)!r}"
    )


@pytest.mark.parametrize("path", USER_DATA_ROUTES)
def test_user_data_routes_always_carry_a_cache_control_header(client, path):
    """
    Absent an explicit header, RFC 9111 4.2.2 lets a shared cache store a 200 GET
    heuristically. DefaultCacheControlMiddleware exists so a route cannot be
    cacheable merely by forgetting to say otherwise.
    """
    assert _cache_control(client.get(path)) != "", f"{path} sent no Cache-Control"


def test_health_is_still_reachable_and_not_broken_by_the_middleware(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert _cache_control(resp) == "no-store"
