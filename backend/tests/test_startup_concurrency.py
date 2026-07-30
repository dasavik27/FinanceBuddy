"""
The anyio threadpool cap must actually be applied at startup.

51 of 54 endpoints are sync `def`, which FastAPI runs in anyio's worker threadpool.
That pool defaults to 40, so without this cap up to 40 GIL-bound pandas handlers
contend for ~0.1 shared vCPU — thrashing without parallelism, and multiplying peak
memory by the concurrency on a 512 MB box.

Worth a test rather than a log line: the startup hook logs what it did, but the app
does not configure logging at INFO, so in practice that message is invisible and the
setting was silently unverified.
"""

import anyio.to_thread
import pytest
from fastapi.testclient import TestClient

import main


def test_lifespan_caps_the_thread_limiter():
    """TestClient as a context manager runs the lifespan hooks."""
    with TestClient(main.app) as client:
        reported = client.get("/health").status_code
        assert reported == 200

        # Must be `async def`: current_default_thread_limiter() has to be called ON
        # the event loop. A sync endpoint runs *inside* the threadpool, where there is
        # no loop, and raises NoEventLoopError.
        @main.app.get("/__limiter_probe__")
        async def _probe():
            return {"tokens": anyio.to_thread.current_default_thread_limiter().total_tokens}

        try:
            tokens = client.get("/__limiter_probe__").json()["tokens"]
        finally:
            main.app.router.routes = [
                r for r in main.app.router.routes
                if getattr(r, "path", None) != "/__limiter_probe__"
            ]

    assert tokens == main.SYNC_ENDPOINT_CONCURRENCY, (
        f"threadpool limiter is {tokens}, expected {main.SYNC_ENDPOINT_CONCURRENCY}"
    )
    assert tokens < 40, "cap is not below anyio's default; the limit is not doing anything"


def test_cap_is_env_overridable_and_sane():
    assert 1 <= main.SYNC_ENDPOINT_CONCURRENCY <= 16, (
        f"{main.SYNC_ENDPOINT_CONCURRENCY} concurrent pandas handlers on ~0.1 vCPU "
        "is not a sane default"
    )


@pytest.mark.parametrize("middleware_name", [
    "DefaultCacheControlMiddleware",
    "IdentityMiddleware",
    "RequestCacheMiddleware",
    "TimingMiddleware",
])
def test_required_middleware_is_installed(middleware_name):
    """
    Ownership enforcement and the no-store default are middleware-dependent:
    identity.owns_record() trusts any caller that is not inside a request scope, which
    is only safe because IdentityMiddleware wraps every HTTP request.
    """
    installed = {m.cls.__name__ for m in main.app.user_middleware}
    assert middleware_name in installed, f"{middleware_name} is not installed"
