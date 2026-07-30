"""
main.py - Finance Buddy API Service Gateway.

Deployment shape this is tuned for: a single uvicorn worker on a free-tier box
(~512 MB RAM, ~0.1 shared vCPU). That has two consequences worth keeping in mind
when editing this file:

  - CPU is the binding constraint, and everything is serialized through one
    process. Duplicate computation costs wall-clock directly.
  - Because there is exactly one worker, in-process caches genuinely are shared
    caches. That is why there is no Redis here: it would cost memory and buy
    nothing until we run multiple workers.

Middleware order below is deliberate - see the comments at each layer.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

# Load .env manually to avoid python-dotenv dependency
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, _, value = line.partition('=')
                if key and value:
                    os.environ[key.strip()] = value.strip()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from shared.identity import identity_scope, normalize_pan, decode_jwt_pan
from shared.services.cache import cache_stats, request_scope

# Shared Infrastructure Gateways
from shared.routers import auth, google_auth, market, accounts, history

# Domain: Mutual Funds
from domains.mutual_funds.routers import (
    portfolio, overview, holdings, performance, compare, insights, rebalance, journey, planning,
)

# Domain: Equity (Indian Stocks) — placeholder
from domains.equity import router as equity

# Domain: Tax Expert
from domains.tax_expert.routers import (
    session as tax_session, income as tax_income, capital_gains as tax_capital_gains,
    summary as tax_summary, itr as tax_itr, rules as tax_rules,
)

logger = logging.getLogger(__name__)

# Requests slower than this get logged with their path so regressions surface in
# the Render logs without needing an APM.
SLOW_REQUEST_MS = float(os.getenv("FINANCEBUDDY_SLOW_REQUEST_MS", "1500"))

# 51 of this app's 54 endpoints are sync `def`, which FastAPI runs in anyio's worker
# threadpool. That pool defaults to 40 tokens, so up to 40 GIL-bound pandas handlers
# could contend for ~0.1 shared vCPU at once - adding context-switch thrash without
# any parallelism, and multiplying peak memory by the concurrency, because each
# handler holds its own intermediate DataFrames on a 512 MB box.
#
# Capping it makes excess requests queue instead of thrash: slower to start serving
# under burst, but faster to finish and bounded in memory. Same reasoning the
# ThreadPoolExecutor sizing already follows, one level up.
SYNC_ENDPOINT_CONCURRENCY = int(os.getenv("FINANCEBUDDY_SYNC_CONCURRENCY", "8"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks. There was no startup hook here at all before."""
    import anyio.to_thread

    limiter = anyio.to_thread.current_default_thread_limiter()
    previous = limiter.total_tokens
    limiter.total_tokens = SYNC_ENDPOINT_CONCURRENCY
    logger.info(
        "[STARTUP] sync endpoint concurrency capped at %d (anyio default was %d)",
        SYNC_ENDPOINT_CONCURRENCY, previous,
    )
    yield


app = FastAPI(
    title="Finance Buddy API",
    description="Smart Wealth Dashboard, Mutual Fund Portfolio Analytics, and Tax Expert Engine",
    version="8.1.0",
    lifespan=lifespan,
)


# ────────────────────────────────────────────────────────────────────────────
# MIDDLEWARE
# ────────────────────────────────────────────────────────────────────────────
# Pure ASGI middleware rather than BaseHTTPMiddleware: BaseHTTPMiddleware runs the
# downstream app in a child task, which both costs overhead and complicates
# contextvar lifetime. These run in the same task as the handler.

class TimingMiddleware:
    """
    Adds a Server-Timing header and logs slow requests.

    Innermost layer (see the ordering note at the add_middleware calls), so the number
    is handler time and excludes compression. Close enough to be useful for spotting
    slow endpoints in the logs; do not read it as the latency the browser experiences.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        started = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                headers = message.setdefault("headers", [])
                headers.append(
                    (b"server-timing", f"total;dur={elapsed_ms:.1f}".encode("latin-1"))
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms >= SLOW_REQUEST_MS:
            logger.warning(
                "[SLOW] %s %s took %.0f ms",
                scope.get("method", "?"),
                scope.get("path", "?"),
                elapsed_ms,
            )


class DefaultCacheControlMiddleware:
    """
    Stamps `Cache-Control: no-store` on any response that did not set one.

    Absent an explicit header, RFC 9111 section 4.2.2 permits a shared cache to
    store a 200 GET heuristically. Almost every route here returns per-user
    financial data - holdings, capital gains, income - and only one router was
    setting the header at all, so the carefully-built "unknown types fail closed"
    policy in shared/services/cache.py was never actually reached on those paths.

    Doing it as middleware rather than route by route means a new endpoint is
    private by default and has to opt *out* to be cacheable, which is the correct
    direction for this data.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(k.lower() == b"cache-control" for k, _ in headers):
                    headers.append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, send_wrapper)


class IdentityMiddleware:
    """
    Binds the caller's asserted PAN for the request (shared/identity.py).

    Priority order:
      1. Authorization: Bearer <JWT>  — Google OAuth flow (verified, preferred)
      2. X-User-PAN header            — legacy PAN-only flow (local dev / tests)

    Ownership is enforced deep in the data-access layer rather than per route, so
    the identity has to be available there without threading a parameter through
    every signature. Same ContextVar mechanism as the L0 memo below.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        auth_header = None
        pan_header  = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                auth_header = value.decode("latin-1")
            elif key == b"x-user-pan":
                pan_header = value.decode("latin-1")

        # JWT takes priority: it is cryptographically verified.
        pan = decode_jwt_pan(auth_header)
        # Fall back to legacy header (local dev, unit tests, PAN-only login).
        if pan is None:
            pan = normalize_pan(pan_header)

        with identity_scope(pan):
            await self.app(scope, receive, send)


class RequestCacheMiddleware:
    """
    Establishes the L0 request-scoped memo store (shared/services/cache.py).

    Innermost layer so the store's lifetime brackets only handler execution. This
    is what lets a single request compute a transaction ledger or a NAV series once
    instead of once per call site.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        with request_scope():
            await self.app(scope, receive, send)


# NOTE ON ORDERING: `add_middleware` PREPENDS to the stack, so the LAST call added is
# the OUTERMOST layer — the opposite of what the comments here used to claim. Measured
# nesting, outermost first:
#
#   ServerError > RequestCache > Identity > CORS > GZip > DefaultCacheControl > Timing > router
#
# Two consequences worth knowing rather than discovering later:
#   - CORS sits OUTSIDE DefaultCacheControl and short-circuits preflights, so an OPTIONS
#     response carries no Cache-Control. Harmless (a preflight has no body), but it means
#     "every response gets no-store" is not literally true.
#   - Timing is innermost, so its number excludes compression rather than including it.
app.add_middleware(TimingMiddleware)

# Fail closed on caching, for any route that did not set a header itself.
app.add_middleware(DefaultCacheControlMiddleware)

# Compress responses > 200 bytes. Portfolio JSON payloads are highly compressible,
# and on a free tier bandwidth and TTFB both matter.
app.add_middleware(GZipMiddleware, minimum_size=200)

# CORS. Note: allow_origins=["*"] together with allow_credentials=True is an
# invalid and unsafe combination (the spec forbids a wildcard origin on credentialed
# requests, and browsers reject it), so origins are always explicit here.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = [
    o.strip() for o in os.getenv("FINANCEBUDDY_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Let the frontend read the timing header for its own diagnostics.
    expose_headers=["Server-Timing"],
)

# Identity before the request store: ownership checks run inside handlers, so the
# PAN must already be bound by the time one executes.
app.add_middleware(IdentityMiddleware)

# Added last => innermost => wraps the route handler only.
app.add_middleware(RequestCacheMiddleware)


# ────────────────────────────────────────────────────────────────────────────
# ROUTERS
# ────────────────────────────────────────────────────────────────────────────

# Shared Infrastructure
app.include_router(auth.router,         prefix="/auth",      tags=["Infrastructure - Authentication"])
app.include_router(google_auth.router,  prefix="/auth",      tags=["Infrastructure - Google OAuth"])
app.include_router(market.router,       prefix="/market",    tags=["Infrastructure - Live Market Feed"])
app.include_router(accounts.router,     prefix="/accounts",  tags=["Infrastructure - Vault Manager"])
app.include_router(history.router,      prefix="/history",   tags=["Infrastructure - History Timeline"])

# Domain: Mutual Funds
app.include_router(portfolio.router,    prefix="/mutual-funds/portfolio",     tags=["Mutual Funds - Session Management"])
app.include_router(overview.router,     prefix="/mutual-funds/overview",      tags=["Mutual Funds - Overview & Allocation"])
app.include_router(holdings.router,     prefix="/mutual-funds/holdings",      tags=["Mutual Funds - Holdings Explorer"])
app.include_router(performance.router,  prefix="/mutual-funds/performance",   tags=["Mutual Funds - Trailing & Rolling Performance"])
app.include_router(compare.router,      prefix="/mutual-funds/compare",       tags=["Mutual Funds - Peer Comparison Matrix"])
app.include_router(insights.router,     prefix="/mutual-funds/insights",      tags=["Mutual Funds - Smart Nudges & CIO Advisories"])
app.include_router(rebalance.router,    prefix="/mutual-funds/rebalance",     tags=["Mutual Funds - Rebalancing & Drift Audit"])
app.include_router(journey.router,      prefix="/mutual-funds/journey",       tags=["Mutual Funds - Wealth Journey Timeline"])
app.include_router(planning.router,     prefix="/mutual-funds/planning",      tags=["Mutual Funds - Tax Harvest & Goal Planning"])

# Domain: Equity (Indian Stocks) — placeholder namespace, reserved so the frontend
# can code against the final URL shape before the domain lands.
app.include_router(equity.router, prefix="/equity", tags=["Equity - Indian Stocks (Coming Soon)"])

# Domain: Tax Expert — all six routers share the /tax-expert prefix and define
# non-overlapping paths within it.
app.include_router(tax_session.router,        prefix="/tax-expert", tags=["Tax Expert - Session Management"])
app.include_router(tax_income.router,         prefix="/tax-expert", tags=["Tax Expert - Income Breakdown"])
app.include_router(tax_capital_gains.router,  prefix="/tax-expert", tags=["Tax Expert - Capital Gains"])
app.include_router(tax_summary.router,        prefix="/tax-expert", tags=["Tax Expert - Computation & Regime Compare"])
app.include_router(tax_itr.router,            prefix="/tax-expert", tags=["Tax Expert - ITR Comparison"])
app.include_router(tax_rules.router,          prefix="/tax-expert", tags=["Tax Expert - Client Rules Feed"])


@app.get("/health", tags=["Infrastructure - Health"])
def health():
    """Service health check."""
    return {"status": "ok", "version": app.version}


@app.get("/health/cache", tags=["Infrastructure - Health"])
def health_cache():
    """
    Live cache metrics - real counters from the in-process tiers.

    Useful for answering "is the cache actually working" after a deploy, rather
    than asserting that it is.
    """
    return cache_stats()
