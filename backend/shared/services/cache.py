"""
shared/services/cache.py - cache primitives for Finance Buddy.

Three tiers, each with a distinct job. They are not fallbacks for each other;
mixing them up is what made the previous version ineffective.

  L0  request-scoped memo  - kills duplicate work *inside* one request. No TTL and
                             no eviction needed: the store dies with the response.
                             This is what stops /performance rebuilding the same
                             transaction ledger 3N+4 times.
  L1  process LRU + TTL    - holds *parsed* objects (pd.Series/DataFrame) between
                             requests, bounded by bytes rather than entry count
                             because a NAV series and a simulation frame differ by
                             orders of magnitude.
  L2  disk (shared/cache.py MarketCache) - survives restart, holds network payloads.

Also here: single-flight. We run one uvicorn worker on ~0.1 shared vCPU, and the
frontend fires every tab's query concurrently. Without single-flight, N concurrent
misses for the same key each compute the full result. With it, one computes and the
rest wait - which collapses a dashboard load's duplicate simulations even on a
completely cold cache.

Deliberately NOT here: Redis. With a single worker the in-process dict already is
the shared cache, so a Redis client would cost memory and buy nothing. Revisit only
if we go multi-worker.
"""

from __future__ import annotations

import contextvars
import copy
import logging
import sys
import threading
import time
from datetime import date, datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache policy by data type
# ---------------------------------------------------------------------------
# `visibility` is a correctness field, not a tuning knob. Anything derived from a
# user's uploaded CAS must never be marked `public`: a shared cache (CDN, corporate
# proxy, ISP cache) is then permitted to store one user's portfolio and re-serve it
# to another. Only genuinely user-independent market data may be `public`.

CACHE_CONFIG: Dict[str, Dict[str, Any]] = {
    # --- user-independent market data: safe to cache publicly ---
    "benchmark_data":      {"ttl": 4 * 3600,  "visibility": "public",  "description": "Market indices (NIFTY, SENSEX)"},
    "market_indices":      {"ttl": 24 * 3600, "visibility": "public",  "description": "Historical index data"},
    "live_navs":           {"ttl": 4 * 3600,  "visibility": "public",  "description": "Current fund NAVs from AMFI"},
    "comparison_data":     {"ttl": 1800,      "visibility": "public",  "description": "Fund peer comparison"},
    # A live index quote. Public because an index level is identical for everyone,
    # but with a 60s freshness window - deliberately NOT `market_indices`, whose 24h
    # `immutable` policy is right for settled historical series and badly wrong for a
    # price the UI polls every minute.
    "market_quote":        {"ttl": 60,        "visibility": "public",  "description": "Live index quote"},

    # --- derived from the user's own holdings: private, never shared-cacheable ---
    "portfolio_summary":   {"ttl": 300, "visibility": "no-store", "description": "Portfolio XIRR, gain, allocation"},
    "holdings_detail":     {"ttl": 900, "visibility": "private",  "description": "Individual fund holdings"},
    "performance_metrics": {"ttl": 900, "visibility": "private",  "description": "Sharpe, Sortino, drawdown"},
    "tax_calculations":    {"ttl": 900, "visibility": "no-store",  "description": "Tax computation on user lots"},
    "rebalance_roadmap":   {"ttl": 600, "visibility": "private",  "description": "Rebalancing transaction plan"},
}

_DEFAULT_POLICY = {"ttl": 300, "visibility": "no-store"}


def get_cache_headers(cache_type: str) -> Dict[str, str]:
    """
    Cache-Control for an endpoint's response.

    Unknown types fall back to `no-store` rather than a permissive default - if we
    do not know what a payload contains, we must not let intermediaries keep it.
    """
    policy = CACHE_CONFIG.get(cache_type, _DEFAULT_POLICY)
    ttl = policy["ttl"]
    visibility = policy.get("visibility", "no-store")

    if visibility == "no-store":
        return {"Cache-Control": "no-store"}

    if visibility == "private":
        # `private` permits the browser to cache but forbids shared caches.
        return {"Cache-Control": f"private, max-age={ttl}, must-revalidate"}

    # public, user-independent data only
    if ttl >= 24 * 3600:
        return {"Cache-Control": f"public, max-age={ttl}, immutable"}
    return {"Cache-Control": f"public, max-age={ttl}"}


def ttl_for(cache_type: str) -> int:
    """TTL in seconds for a configured cache type."""
    return CACHE_CONFIG.get(cache_type, _DEFAULT_POLICY)["ttl"]


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def cache_key(*args, **kwargs) -> str:
    """
    Build a stable key from arguments.

    Keyword args are sorted so call-site ordering does not fragment the key. Note
    that positional and keyword forms of the same argument still produce different
    keys - callers within a namespace should be consistent about how they call.

    Each component is length-prefixed rather than plainly joined, because a plain
    delimiter is ambiguous: ("a:b", "c") and ("a", "b:c") would otherwise collide,
    and fund names, tickers and ISINs do contain punctuation.
    """
    parts = [_key_part(a) for a in args]
    parts += [f"{k}={_key_part(v)}" for k, v in sorted(kwargs.items())]
    return "|".join(f"{len(p)}~{p}" for p in parts)


class UnsafeCacheKey(TypeError):
    """
    Raised when a value cannot be turned into a trustworthy cache key.

    Exists so the failure is loud instead of silent. The alternative - falling back
    to str() - is actively dangerous for containers whose repr is *truncated*: pandas
    and numpy elide the middle of large objects with "...", so two different
    portfolios can render to a byte-identical string. Verified: two 100-row frames
    differing only at row 50 produce the same key. A cache hit on that key serves one
    user's ledger to another.

    Callers that can proceed without caching (see request_memo) should catch this and
    compute directly. Being slow is always better than being wrong about money.
    """


def _key_part(value: Any) -> str:
    """
    Render one key component, avoiding unstable reprs.

    **Allowlist, not denylist.** An earlier version rejected a fixed set of type
    *names* ("DataFrame", "Series", "ndarray", ...) and fell through to `str(value)`
    for everything else. That leaked badly: DatetimeIndex, RangeIndex,
    CategoricalIndex, IntegerArray, DataFrameGroupBy and - worst - a plain `dict`
    holding a DataFrame all sailed through, and the dict case was proven to produce a
    byte-identical key for two different frames. Since the whole point of this
    function is that a wrong key silently serves one user's data to another, anything
    not known to render safely must raise.
    """
    if value is None:
        return "~"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # repr of a float is stable, but normalise integral floats so
        # days=9999 and days=9999.0 share a key.
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_key_part(v) for v in value) + "]"
    if isinstance(value, Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    raise UnsafeCacheKey(
        f"{type(value).__module__}.{type(value).__name__} is not a safe cache-key "
        f"component. Only None/bool/int/float/str/bytes/list/tuple/Enum/date are "
        f"accepted, because anything else may have a truncated or unordered repr and "
        f"render two different values identically. For frames use a content "
        f"fingerprint - see domains/mutual_funds/derived.py:_frame_fingerprint."
    )


# ---------------------------------------------------------------------------
# Sizing helpers (L1 is bounded by bytes)
# ---------------------------------------------------------------------------

def _sizeof(value: Any) -> int:
    """
    Best-effort byte size. Pandas objects report their real buffers; everything
    else falls back to a shallow estimate, which is fine because the point is to
    stop a few large frames from eating the budget, not to be exact.
    """
    try:
        usage = getattr(value, "memory_usage", None)
        if usage is not None:
            got = usage(deep=True)
            return int(got.sum()) if hasattr(got, "sum") else int(got)
    except Exception:
        pass

    try:
        return _sizeof_recursive(value, depth=3)
    except Exception:
        return 1024


def _sizeof_recursive(value: Any, depth: int) -> int:
    """
    Bounded-depth recursive sizer.

    Recursion matters for payloads like the AMFI bundle - a tuple of dicts holding
    tens of thousands of ISIN keys. A shallow sys.getsizeof there reports only the
    hash tables and understates the real footprint by an order of magnitude, which
    would let the byte budget be silently blown.
    """
    usage = getattr(value, "memory_usage", None)
    if usage is not None:
        got = usage(deep=True)
        return int(got.sum()) if hasattr(got, "sum") else int(got)

    base = sys.getsizeof(value)
    if depth <= 0:
        return base

    if isinstance(value, dict):
        # Sample large dicts rather than walking millions of entries on every set().
        items = value.items()
        n = len(value)
        if n > 2000:
            sampled = 0
            for i, (k, v) in enumerate(items):
                if i >= 2000:
                    break
                sampled += _sizeof_recursive(k, depth - 1) + _sizeof_recursive(v, depth - 1)
            return base + int(sampled * (n / 2000.0))
        return base + sum(
            _sizeof_recursive(k, depth - 1) + _sizeof_recursive(v, depth - 1) for k, v in items
        )

    if isinstance(value, (list, tuple, set)):
        n = len(value)
        if n > 2000:
            sampled = sum(_sizeof_recursive(v, depth - 1) for v in list(value)[:2000])
            return base + int(sampled * (n / 2000.0))
        return base + sum(_sizeof_recursive(v, depth - 1) for v in value)

    return base


_IMMUTABLE = (str, bytes, int, float, bool, complex, frozenset, type(None))


def _copy_out(value: Any) -> Any:
    """
    Hand back a copy of a mutable payload.

    Returning the cached object by reference is how a caller's in-place edit
    silently corrupts every later reader. market_indices.fetch_benchmark_series
    already copies on both sides for exactly this reason; a cache in front of it must
    not undo that. Note that dicts and lists need this just as much as DataFrames do -
    compute_period_comparison returns a dict of lists, and a caller appending to one
    of those lists would otherwise mutate the cached entry.

    Callers that store very large read-only payloads can opt out via
    `copy_on_read=False` when setting.
    """
    if isinstance(value, _IMMUTABLE):
        return value

    # pandas Series / DataFrame
    if hasattr(value, "copy") and hasattr(value, "index"):
        try:
            return value.copy()
        except Exception:
            return value

    if isinstance(value, (dict, list, tuple, set)):
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    return value


# ---------------------------------------------------------------------------
# L0: request-scoped memo
# ---------------------------------------------------------------------------
# A ContextVar rather than a thread-local: FastAPI runs sync endpoints in a
# threadpool, and anyio copies the context into the worker thread, so this stays
# correct for both sync and async handlers.

_request_store: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "financebuddy_request_cache", default=None
)


class request_scope:
    """
    Context manager establishing a per-request memo store.

    Installed by RequestCacheMiddleware. Outside a request the memo degrades to a
    no-op pass-through, so decorated helpers stay callable from scripts and tests.
    """

    def __init__(self) -> None:
        self._token = None

    def __enter__(self) -> Dict[str, Any]:
        store: Dict[str, Any] = {}
        self._token = _request_store.set(store)
        return store

    def __exit__(self, *exc_info) -> None:
        if self._token is not None:
            _request_store.reset(self._token)
            self._token = None


def request_memo(namespace: str = "") -> Callable:
    """
    Memoize for the lifetime of one request.

    Use for work that is pure within a request but must not persist across them -
    NAV series lookups by code, per-fund benchmark resolution, repeated scalar
    lookups. No TTL and no eviction: the store is discarded with the response.

    **Arguments must be key-safe.** Do not decorate a function whose arguments are
    DataFrames, Series or arrays: their reprs are truncated, so two different inputs
    can produce the same key. Rather than risk that, such a call now bypasses the
    memo entirely and computes directly (see UnsafeCacheKey). For frame-keyed
    caching use a content fingerprint - domains/mutual_funds/derived.py shows the
    pattern with pd.util.hash_pandas_object.

    Note this decorator is only correct inside a request handler. contextvars do not
    propagate into concurrent.futures worker threads, so a function called from a
    ThreadPoolExecutor sees no store and silently runs uncached - which is safe, just
    not useful.
    """
    def decorator(func: Callable) -> Callable:
        ns = namespace or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            store = _request_store.get()
            if store is None:
                return func(*args, **kwargs)  # outside a request: no memo

            try:
                key = f"{ns}|{cache_key(*args, **kwargs)}"
            except UnsafeCacheKey as e:
                # Fail open to correctness: compute rather than risk a key collision
                # returning another caller's result.
                logger.warning("[L0] bypassing memo for %s: %s", ns, e)
                return func(*args, **kwargs)

            if key in store:
                return _copy_out(store[key])

            result = func(*args, **kwargs)
            store[key] = result
            return _copy_out(result)

        wrapper.cache_clear = lambda: (_request_store.get() or {}).clear()  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# L1: bounded process cache with TTL and single-flight
# ---------------------------------------------------------------------------

class ProcessCache:
    """
    LRU + TTL cache bounded by total payload bytes.

    Bounded by bytes because entry count is a poor proxy here: one entry may be a
    3-element dict and the next a 3700x20 float frame. On a 512 MB box an
    unbounded dict is a slow memory leak, which is what the previous
    implementation was.

    Every mutating path holds `_lock`. Per-key single-flight locks are separate so
    a slow computation never blocks unrelated keys.
    """

    def __init__(self, max_bytes: int = 48 * 1024 * 1024, name: str = "L1"):
        self.name = name
        self.max_bytes = max_bytes
        # key -> (value, expires_at, nbytes, copy_on_read)
        self._store: "Dict[str, Tuple[Any, float, int, bool]]" = {}
        self._order: list[str] = []  # LRU: oldest first
        self._lock = threading.RLock()
        self._flight_locks: Dict[str, threading.Lock] = {}
        self._flight_waiters: Dict[str, int] = {}
        self._flight_guard = threading.Lock()
        self._bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expiries = 0

    # -- basic operations ---------------------------------------------------

    def get(self, key: str) -> Tuple[bool, Any]:
        """Return (found, value). Copies mutable payloads on the way out."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return False, None

            value, expires_at, nbytes, copy_on_read = entry
            if time.monotonic() >= expires_at:
                self._discard(key)
                self.expiries += 1
                self.misses += 1
                return False, None

            self._touch(key)
            self.hits += 1
            return True, _copy_out(value) if copy_on_read else value

    def set(self, key: str, value: Any, ttl: int, copy_on_read: bool = True) -> None:
        """
        Store a value.

        `copy_on_read=False` opts out of defensive copying for large payloads that
        callers treat as immutable - deep-copying a 50k-entry map on every access
        would cost more than the fetch it replaces. Use sparingly and document it.
        """
        nbytes = _sizeof(value)
        with self._lock:
            if key in self._store:
                self._discard(key)

            # An oversized single payload is simply not cached - caching it would
            # evict everything else to hold one item.
            if nbytes > self.max_bytes:
                logger.debug(
                    "[%s] payload for %s is %d bytes, over budget %d - not caching",
                    self.name, key, nbytes, self.max_bytes,
                )
                return

            self._store[key] = (value, time.monotonic() + ttl, nbytes, copy_on_read)
            self._order.append(key)
            self._bytes += nbytes
            self._evict_to_budget()

    def delete(self, key: str) -> None:
        with self._lock:
            self._discard(key)

    def delete_prefix(self, prefix: str) -> int:
        """
        Drop every entry whose key starts with `prefix`. Returns the count removed.

        Lets a targeted refresh clear one family of entries (say, benchmark series)
        without discarding unrelated ones that are expensive to rebuild.
        """
        with self._lock:
            victims = [k for k in self._store if k.startswith(prefix)]
            for key in victims:
                self._discard(key)
            return len(victims)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._order.clear()
            self._bytes = 0

    # -- single-flight ------------------------------------------------------

    def get_or_compute(
        self, key: str, producer: Callable[[], Any], ttl: int, copy_on_read: bool = True
    ) -> Any:
        """
        Return a cached value, or compute it exactly once across concurrent callers.

        The double-check after acquiring the flight lock is the point: the thread
        that waited finds the value the winner just stored instead of recomputing it.
        """
        found, value = self.get(key)
        if found:
            return value

        lock = self._acquire_flight_lock(key)
        try:
            with lock:
                found, value = self.get(key)
                if found:
                    return value

                result = producer()
                self.set(key, result, ttl, copy_on_read=copy_on_read)
                return _copy_out(result) if copy_on_read else result
        finally:
            self._release_flight_lock(key)

    def _acquire_flight_lock(self, key: str) -> threading.Lock:
        with self._flight_guard:
            lock = self._flight_locks.get(key)
            if lock is None:
                lock = self._flight_locks[key] = threading.Lock()
            self._flight_waiters[key] = self._flight_waiters.get(key, 0) + 1
            return lock

    def _release_flight_lock(self, key: str) -> None:
        # Refcounted so the lock table does not grow without bound.
        with self._flight_guard:
            remaining = self._flight_waiters.get(key, 1) - 1
            if remaining <= 0:
                self._flight_waiters.pop(key, None)
                self._flight_locks.pop(key, None)
            else:
                self._flight_waiters[key] = remaining

    # -- internals (all callers hold _lock) --------------------------------

    def _touch(self, key: str) -> None:
        try:
            self._order.remove(key)
        except ValueError:
            pass
        self._order.append(key)

    def _discard(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry is not None:
            self._bytes -= entry[2]
            try:
                self._order.remove(key)
            except ValueError:
                pass

    def _evict_to_budget(self) -> None:
        while self._bytes > self.max_bytes and self._order:
            oldest = self._order[0]
            self._discard(oldest)
            self.evictions += 1

    # -- observability -----------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "name": self.name,
                "entries": len(self._store),
                "bytes": self._bytes,
                "bytes_budget": self.max_bytes,
                "utilization_pct": round(100.0 * self._bytes / self.max_bytes, 1) if self.max_bytes else 0.0,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate_pct": round(100.0 * self.hits / total, 1) if total else None,
                "evictions": self.evictions,
                "expiries": self.expiries,
            }


# Two separate budgets so that a burst of large derived artifacts cannot evict the
# NAV/benchmark series that every recomputation depends on.
MARKET_CACHE = ProcessCache(max_bytes=32 * 1024 * 1024, name="L1-market")
DERIVED_CACHE = ProcessCache(max_bytes=24 * 1024 * 1024, name="L1-derived")


def cached(ttl: int = 300, namespace: str = "", store: Optional[ProcessCache] = None) -> Callable:
    """
    Cache a function's result in L1, with single-flight and copy-on-return.

    Prefer this over hand-rolled module-level dicts: it is bounded, locked, and
    reports hit rates.
    """
    target = store if store is not None else MARKET_CACHE

    def decorator(func: Callable) -> Callable:
        ns = namespace or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                key = f"{ns}|{cache_key(*args, **kwargs)}"
            except UnsafeCacheKey as e:
                # Same policy as request_memo: an argument we cannot key safely means
                # no caching, not a 500. Without this, decorating any function that
                # takes a DataFrame turns every call into an error.
                logger.warning("[L1] bypassing cache for %s: %s", ns, e)
                return func(*args, **kwargs)
            return target.get_or_compute(key, lambda: func(*args, **kwargs), ttl)

        def _cache_delete(*a, **k):
            try:
                target.delete(f"{ns}|{cache_key(*a, **k)}")
            except UnsafeCacheKey:
                pass  # nothing was cached under an unsafe key, so nothing to delete

        wrapper.cache_delete = _cache_delete  # type: ignore[attr-defined]
        wrapper.cache_stats = target.stats  # type: ignore[attr-defined]
        return wrapper

    return decorator


def memoize(ttl: int = 300, namespace: str = "", store: Optional[ProcessCache] = None) -> Callable:
    """Backwards-compatible alias for `cached`."""
    return cached(ttl=ttl, namespace=namespace, store=store)


def cache_stats() -> Dict[str, Any]:
    """Live metrics for /health/cache. Real counters, not a hardcoded dict."""
    return {
        "tiers": [MARKET_CACHE.stats(), DERIVED_CACHE.stats()],
    }


def clear_all_caches() -> None:
    """Drop every in-process cache tier. Used by refresh paths and tests."""
    MARKET_CACHE.clear()
    DERIVED_CACHE.clear()


__all__ = [
    "CACHE_CONFIG",
    "cache_key",
    "UnsafeCacheKey",
    "get_cache_headers",
    "ttl_for",
    "request_scope",
    "request_memo",
    "ProcessCache",
    "MARKET_CACHE",
    "DERIVED_CACHE",
    "cached",
    "memoize",
    "cache_stats",
    "clear_all_caches",
]
