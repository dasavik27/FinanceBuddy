"""
Integration tests for the middleware pipeline in main.py.

These exercise the wiring rather than the pieces: that the request-scoped memo store
is actually established around a handler (a ContextVar through Starlette's ASGI stack
into FastAPI's sync threadpool is easy to get subtly wrong), that timing headers are
emitted, and that the health endpoints report live state instead of asserting it.
"""

import pytest
from fastapi.testclient import TestClient

import main
from shared.services.cache import request_memo


@pytest.fixture
def client():
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def test_server_timing_header_is_present(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "server-timing" in {k.lower() for k in resp.headers}


def test_server_timing_reports_a_duration(client):
    resp = client.get("/health")
    timing = resp.headers["server-timing"]
    assert timing.startswith("total;dur=")
    assert float(timing.split("=")[1]) >= 0.0


# ---------------------------------------------------------------------------
# Request-scoped memo store
# ---------------------------------------------------------------------------

_calls = []


@request_memo("middleware_probe")
def _probe(tag: str):
    _calls.append(tag)
    return {"tag": tag}


@pytest.fixture(autouse=True)
def reset_calls():
    _calls.clear()
    yield
    _calls.clear()


def test_request_scope_is_active_inside_a_sync_handler(client):
    """
    The store is set by pure-ASGI middleware; a sync endpoint runs in anyio's
    threadpool. This asserts the ContextVar survives that hop - if it does not, the
    memo silently degrades to a pass-through and every dedup win is lost.
    """
    @main.app.get("/__test__/memo")
    def memo_endpoint():
        for _ in range(5):
            _probe("same")
        return {"calls": len(_calls)}

    resp = client.get("/__test__/memo")
    assert resp.status_code == 200
    assert resp.json()["calls"] == 1, (
        "request-scoped memo was not active inside the handler"
    )


def test_request_scope_does_not_leak_between_requests(client):
    @main.app.get("/__test__/memo2")
    def memo_endpoint_2():
        _probe("same")
        return {"calls": len(_calls)}

    client.get("/__test__/memo2")
    resp = client.get("/__test__/memo2")
    # Second request recomputes, so the module-level list has grown to 2.
    assert resp.json()["calls"] == 2, "memo state leaked across requests"


def test_request_scope_active_in_async_handler(client):
    @main.app.get("/__test__/memo_async")
    async def memo_endpoint_async():
        for _ in range(3):
            _probe("async")
        return {"calls": len(_calls)}

    resp = client.get("/__test__/memo_async")
    assert resp.json()["calls"] == 1


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

def test_health_does_not_claim_unverified_optimizations(client):
    """
    /health used to hardcode "phase_1_caching": "enabled" and a "cache_hit_target".
    A health endpoint should report state, not advertise intentions.
    """
    body = client.get("/health").json()
    assert body["status"] == "ok"
    flat = str(body).lower()
    for claim in ("cache_hit_target", "phase_1", "80%"):
        assert claim not in flat, f"/health still asserts {claim!r}"


def test_health_cache_reports_live_counters(client):
    body = client.get("/health/cache").json()
    assert "tiers" in body
    assert len(body["tiers"]) >= 1

    tier = body["tiers"][0]
    for field in ("entries", "bytes", "bytes_budget", "hits", "misses", "evictions"):
        assert field in tier, f"missing live metric {field!r}"
    assert isinstance(tier["hits"], int)


def test_health_cache_reflects_real_activity(client):
    from shared.services.cache import DERIVED_CACHE

    DERIVED_CACHE.clear()
    before = client.get("/health/cache").json()
    derived_before = [t for t in before["tiers"] if t["name"] == "L1-derived"][0]

    DERIVED_CACHE.get_or_compute("probe", lambda: "v", 60)
    DERIVED_CACHE.get_or_compute("probe", lambda: "v", 60)  # hit

    after = client.get("/health/cache").json()
    derived_after = [t for t in after["tiers"] if t["name"] == "L1-derived"][0]

    assert derived_after["hits"] > derived_before["hits"], (
        "cache metrics are not tracking real activity"
    )


# ---------------------------------------------------------------------------
# Compression / CORS wiring
# ---------------------------------------------------------------------------

def test_gzip_applies_to_larger_responses(client):
    resp = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    # TestClient transparently decompresses, so assert on the negotiated encoding.
    assert resp.headers.get("content-encoding") == "gzip"


def test_cors_exposes_the_timing_header(client):
    resp = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    exposed = resp.headers.get("access-control-expose-headers", "")
    assert "Server-Timing" in exposed, (
        "frontend cannot read Server-Timing without it being exposed"
    )
