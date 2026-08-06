"""
Every budget route refuses an anonymous caller.

This is a sweep rather than a per-route test, and it is deliberately written to
discover routes rather than list them. The budget domain grew from three routers to
five in one change; a hand-maintained list is exactly the thing that goes stale, and a
new route added six months from now that forgets its auth check is the failure this is
here to catch.

Why it matters more than it looks. `identity.owns_record()` allows any caller to read a
record with **no owner** - that is correct for internal callers, and it is why every
write path has to require an authenticated user. An unauthenticated upload would create
a session owned by nobody, which owns_record would then hand to everyone. The routers
enforce this with `_require_caller()`; this test is what stops that from being dropped.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

# Routes that are legitimately reachable without a credential. Empty, and it should
# stay that way - every budget route touches somebody's bank statements.
_PUBLIC: set = set()

# A placeholder for each path parameter. The value never matters: an anonymous caller
# must be refused before the id is ever looked up, so any syntactically valid value
# exercises the same decision.
_PATH_VALUES = {
    "session_id": "overall",
    "account_key": "HDFC:savings:1234",
    "rule_id": "deadbeef",
}


def _budget_routes():
    """(method, concrete path) for every budget route, path params filled in."""
    found = []
    schema = app.openapi()
    for path, path_item in schema.get("paths", {}).items():
        if not path.startswith("/budget"):
            continue
        if path in _PUBLIC:
            continue
        concrete = path
        for name, value in _PATH_VALUES.items():
            concrete = concrete.replace("{" + name + "}", value)
        if "{" in concrete:
            raise AssertionError(
                f"{path} has a path parameter this test does not know how to fill. "
                "Add it to _PATH_VALUES rather than skipping the route."
            )
        for method in path_item.keys():
            m = method.upper()
            if m not in {"HEAD", "OPTIONS"}:
                found.append((m, concrete))
    return sorted(found)


ROUTES = _budget_routes()


def test_the_sweep_actually_found_the_routes():
    """
    Guards the guard.

    If route discovery silently returned nothing - a changed prefix, a router that
    stopped being registered - every test below would vacuously pass.
    """
    assert len(ROUTES) >= 25, f"expected the full budget surface, found {len(ROUTES)}"
    paths = {path for _, path in ROUTES}
    # One from each router, so a router dropped from main.py fails here.
    assert "/budget/portfolio/upload" in paths
    assert "/budget/analytics/overall/overview" in paths
    assert "/budget/rules" in paths
    assert "/budget/accounts" in paths
    assert "/budget/insights/overall/recurring" in paths


@pytest.mark.parametrize("method,path", ROUTES, ids=[f"{m} {p}" for m, p in ROUTES])
def test_route_refuses_an_anonymous_caller(method, path):
    """
    401, never 200.

    A 422 is also acceptable: FastAPI validates the body before the handler runs, so a
    route with a required payload can reject the shape before it ever checks identity.
    What must not happen is a 2xx.
    """
    client = TestClient(app)
    response = client.request(method, path, json={}, files=None)

    assert response.status_code != 200, (
        f"{method} {path} served an anonymous caller. Every budget route reads or "
        f"writes somebody's bank statements and must call _require_caller()."
    )
    assert response.status_code in (401, 422), (
        f"{method} {path} answered {response.status_code} to an anonymous caller; "
        "expected 401 (no identity) or 422 (body rejected first)."
    )
