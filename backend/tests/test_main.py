"""
test_main_middleware_full.py

Coverage for main.py middleware branches, lifespan hooks, and OpenAPI wiring
not exercised by test_middleware.py / test_startup_concurrency.py.
"""

import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import main
from shared.identity import Caller
from shared import users
from shared.services.cache import request_memo


ISSUER = "https://example-test-issuer.invalid/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-main"


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


class _StubJwks:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": self._public_key})()


def _mint_jwt(private_key, *, sub="user-main", email="main@example.test", exp_offset=3600):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": sub,
        "email": email,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def _find_identity_middleware(app):
    curr = app.middleware_stack
    while curr is not None:
        if isinstance(curr, main.IdentityMiddleware):
            return curr
        curr = getattr(curr, "app", None)
    return None


@pytest.fixture
def client_with_verifier(rsa_keypair):
    from shared.oidc import OidcJwtVerifier

    private_key, public_key = rsa_keypair
    verifier = OidcJwtVerifier(
        jwks_url="https://example.invalid/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        jwk_client=_StubJwks(public_key),
    )
    client = TestClient(main.app)
    client.get("/health")
    mw = _find_identity_middleware(main.app)
    old_verifier = mw._verifier
    mw._verifier = verifier
    yield client, private_key, mw
    mw._verifier = old_verifier


def test_lifespan_migration_success(monkeypatch):
    monkeypatch.setattr("migrations.migrate.upgrade", lambda: 0)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


def test_lifespan_migration_nonzero_rc(monkeypatch):
    monkeypatch.setattr("migrations.migrate.upgrade", lambda: 1)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


def test_lifespan_migration_exception(monkeypatch):
    def _boom():
        raise RuntimeError("migration failed")

    monkeypatch.setattr("migrations.migrate.upgrade", _boom)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200


def test_identity_middleware_no_verifier_warning():
    mw = main.IdentityMiddleware(MagicMock())
    mw._verifier = None
    assert mw._caller({"path": "/auth/me", "headers": []}) is None


def test_identity_middleware_non_bearer_auth(client_with_verifier):
    client, private_key, mw = client_with_verifier
    token = _mint_jwt(private_key)
    resp = client.get("/auth/me", headers={"Authorization": f"Token {token}"})
    assert resp.status_code == 401


def test_identity_middleware_auth_path_logging(client_with_verifier, monkeypatch):
    client, private_key, _ = client_with_verifier
    token = _mint_jwt(private_key)
    monkeypatch.setattr(
        users,
        "resolve",
        lambda issuer, subject, email=None, name=None: Caller(
            user_id="u-log", status="active", role="user", email=email or "x@test.com"
        ),
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_identity_resolution_exception_treated_as_anonymous(client_with_verifier, monkeypatch):
    client, private_key, _ = client_with_verifier
    token = _mint_jwt(private_key)
    monkeypatch.setattr(users, "resolve", MagicMock(side_effect=RuntimeError("db down")))
    resp = client.get("/health", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_pending_account_blocked_except_auth_me(client_with_verifier, monkeypatch):
    client, private_key, _ = client_with_verifier
    token = _mint_jwt(private_key, sub="pending-u", email="pending@example.test")
    monkeypatch.setattr(
        users,
        "resolve",
        lambda *a, **k: Caller(
            user_id="pending-u", status="pending", role="user", email="pending@example.test"
        ),
    )
    blocked = client.get(
        "/mutual-funds/overview/test-session/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert blocked.status_code == 403
    assert "pending" in blocked.json()["detail"].lower()

    allowed = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert allowed.status_code == 200


def test_suspended_account_blocked_except_auth_me(client_with_verifier, monkeypatch):
    client, private_key, _ = client_with_verifier
    token = _mint_jwt(private_key, sub="susp-u", email="susp@example.test")
    monkeypatch.setattr(
        users,
        "resolve",
        lambda *a, **k: Caller(
            user_id="susp-u", status="suspended", role="user", email="susp@example.test"
        ),
    )
    blocked = client.get(
        "/equity/overview/test-session/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert blocked.status_code == 403
    assert "suspended" in blocked.json()["detail"].lower()

    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200


def test_default_cache_control_middleware():
    captured = {}

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def capture_send(message):
        if message["type"] == "http.response.start":
            captured["headers"] = dict(message.get("headers", []))

    mw = main.DefaultCacheControlMiddleware(inner_app)

    import asyncio
    asyncio.run(mw({"type": "http", "method": "GET", "path": "/test"}, MagicMock(), capture_send))
    assert captured["headers"].get(b"cache-control") == b"no-store"


def test_timing_middleware_slow_request_warning(monkeypatch):
    import asyncio

    async def slow_app(scope, receive, send):
        await asyncio.sleep(0.01)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    monkeypatch.setattr(main, "SLOW_REQUEST_MS", 1.0)
    mw = main.TimingMiddleware(slow_app)

    async def noop_send(message):
        pass

    asyncio.run(mw({"type": "http", "method": "GET", "path": "/slow"}, MagicMock(), noop_send))


def test_non_http_scope_passthrough():
    import asyncio

    called = []

    async def app(scope, receive, send):
        called.append(scope["type"])

    for mw_cls in (main.TimingMiddleware, main.DefaultCacheControlMiddleware,
                   main.IdentityMiddleware, main.RequestCacheMiddleware):
        mw = mw_cls(app)
        asyncio.run(mw({"type": "websocket"}, MagicMock(), MagicMock()))
    assert called == ["websocket"] * 4


def test_custom_openapi_cached_and_public_routes(monkeypatch):
    main.app.openapi_schema = None
    schema = main.custom_openapi()
    assert schema["security"] == [{"BearerAuth": []}]
    assert "BearerAuth" in schema["components"]["securitySchemes"]

    health_op = schema["paths"]["/health"]["get"]
    assert health_op.get("security") == []

    cached = main.custom_openapi()
    assert cached is schema

    # x- extension keys in path items are skipped (line 563-564)
    from fastapi.openapi.utils import get_openapi

    fake_schema = get_openapi(
        title=main.app.title,
        version=main.app.version,
        description=main.app.description,
        routes=main.app.routes,
    )
    fake_schema["paths"]["/__xprobe__"] = {
        "x-internal": {"description": "skip me"},
        "post": {"responses": {"200": {"description": "ok"}}},
    }
    monkeypatch.setattr("main.get_openapi", lambda **kw: fake_schema)
    main.app.openapi_schema = None
    schema2 = main.custom_openapi()
    assert schema2["paths"]["/__xprobe__"]["post"].get("security") == [{"BearerAuth": []}]


def test_startup_db_pool_failure(monkeypatch):
    monkeypatch.setattr(main.db, "get_pool", MagicMock(side_effect=RuntimeError("no db")))
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

# ---------------------------------------------------------------------------
# Legacy middleware + health integration tests (merged)
# ---------------------------------------------------------------------------

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


def test_health_cache_requires_authentication(client):
    """
    The counters carry no user data, but they do reveal traffic volume and timing.
    /health stays open for the platform's liveness probe; this one does not.
    """
    assert client.get("/health/cache").status_code == 401


def test_health_cache_reports_live_counters(client, signed_in):
    body = client.get("/health/cache", headers=signed_in).json()
    assert "tiers" in body
    assert len(body["tiers"]) >= 1

    tier = body["tiers"][0]
    for field in ("entries", "bytes", "bytes_budget", "hits", "misses", "evictions"):
        assert field in tier, f"missing live metric {field!r}"
    assert isinstance(tier["hits"], int)


def test_health_cache_reflects_real_activity(client, signed_in):
    from shared.services.cache import DERIVED_CACHE

    DERIVED_CACHE.clear()
    before = client.get("/health/cache", headers=signed_in).json()
    derived_before = [t for t in before["tiers"] if t["name"] == "L1-derived"][0]

    DERIVED_CACHE.get_or_compute("probe", lambda: "v", 60)
    DERIVED_CACHE.get_or_compute("probe", lambda: "v", 60)  # hit

    after = client.get("/health/cache", headers=signed_in).json()
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

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_openapi_schema_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/health" in paths
    assert "/mutual-funds/portfolio/parse" in paths
    assert "/tax-expert/parse-ais" in paths


def test_openapi_exposes_bearer_auth_for_swagger(client):
    """Swagger Authorize needs components.securitySchemes + operation security."""
    schema = client.get("/openapi.json").json()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "BearerAuth" in schemes
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schema.get("security") == [{"BearerAuth": []}]
    # Public health stays optional in the UI.
    assert schema["paths"]["/health"]["get"].get("security") == []
    # Authenticated route advertises Bearer.
    me = schema["paths"]["/auth/me"]["get"]
    assert {"BearerAuth": []} in me.get("security", [])

def test_main_auth_middleware_no_verifier(monkeypatch):
    import main

    monkeypatch.setattr(main.oidc, "from_env", lambda: None)
    mw = main.IdentityMiddleware(MagicMock())
    assert mw._verifier is None

