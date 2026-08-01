"""
Tests for shared/services/cache.py.

Several of these pin bugs that were live in the previous implementation, so they
are regression tests as much as unit tests:

  - values were handed back by reference, letting a caller's in-place edit corrupt
    every subsequent reader (and defeating the defensive .copy() in
    market_indices.fetch_benchmark_series);
  - the store was unbounded, which on a 512 MB box is a slow leak;
  - concurrent misses for the same key all recomputed;
  - per-session portfolio responses were labelled `public`, which permits a shared
    cache to re-serve one user's holdings to another.
"""

import threading
import time

import pandas as pd
import pytest

from shared.services.cache import (
    CACHE_CONFIG,
    DERIVED_CACHE,
    ProcessCache,
    cache_key,
    cached,
    get_cache_headers,
    request_memo,
    request_scope,
)


# ---------------------------------------------------------------------------
# Cache-Control visibility - the data-leak guard
# ---------------------------------------------------------------------------

# Anything derived from an uploaded CAS. A shared cache must never store these.
USER_DERIVED_TYPES = [
    "portfolio_summary",
    "holdings_detail",
    "performance_metrics",
    "tax_calculations",
    "rebalance_roadmap",
]


@pytest.mark.parametrize("cache_type", USER_DERIVED_TYPES)
def test_user_derived_responses_are_never_public(cache_type):
    header = get_cache_headers(cache_type)["Cache-Control"]
    assert "public" not in header, (
        f"{cache_type} is derived from one user's portfolio; 'public' would let a "
        f"CDN or proxy serve it to a different user. Got: {header}"
    )
    assert "private" in header or "no-store" in header


def test_unknown_cache_type_defaults_to_no_store():
    # Fail closed: if we do not know what a payload holds, intermediaries must not keep it.
    assert get_cache_headers("something_new_and_unclassified") == {"Cache-Control": "no-store"}


def test_public_only_for_user_independent_market_data():
    """
    An allowlist, so adding a `public` type is a deliberate act rather than a typo.

    Each name below has been checked to contain only data that is identical for every
    user. Note the limit of this guard: it validates the *policy table*, not what a
    route actually puts in the body. `/benchmark-overlay` shipped a user's portfolio
    curve under `comparison_data` and this test could not see it - that is what
    tests/test_cache_headers_routes.py exists for.
    """
    for cache_type, policy in CACHE_CONFIG.items():
        if policy.get("visibility") == "public":
            assert cache_type in {
                "benchmark_data",
                "market_indices",
                "live_navs",
                "comparison_data",
                # A live index quote (Nifty level + 1D change). Same for everyone; 60s TTL.
                "market_quote",
                # A listed equity's last traded price, keyed by NSE symbol. A share
                # price is identical for every holder; how many of them a given user
                # owns is in the session payload, never here. 5-minute TTL.
                "equity_quote",
            }, f"{cache_type} marked public - confirm it contains no user-specific data"


def test_market_quote_is_short_lived():
    """
    A live quote must not inherit the 24h `immutable` policy that suits settled
    historical series - the UI polls it every 60 seconds.
    """
    assert CACHE_CONFIG["market_quote"]["ttl"] <= 300
    header = get_cache_headers("market_quote")["Cache-Control"]
    assert "immutable" not in header


def test_every_configured_type_declares_visibility():
    for cache_type, policy in CACHE_CONFIG.items():
        assert "visibility" in policy, f"{cache_type} must declare visibility explicitly"


# ---------------------------------------------------------------------------
# Copy-on-return
# ---------------------------------------------------------------------------

def test_cached_series_is_not_returned_by_reference():
    store = ProcessCache(max_bytes=1 << 20, name="test")
    calls = []

    def produce():
        calls.append(1)
        return pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3))

    first = store.get_or_compute("k", produce, ttl=60)
    first.iloc[0] = 999.0  # a caller mutating what it received

    second = store.get_or_compute("k", produce, ttl=60)
    assert len(calls) == 1, "should have been served from cache"
    assert second.iloc[0] == 1.0, "mutation by an earlier caller leaked into the cache"


def test_request_memo_also_copies():
    @request_memo("t")
    def build():
        return pd.Series([1.0, 2.0])

    with request_scope():
        a = build()
        a.iloc[0] = 42.0
        b = build()
        assert b.iloc[0] == 1.0


# ---------------------------------------------------------------------------
# TTL and byte-budget eviction
# ---------------------------------------------------------------------------

def test_expired_entry_is_recomputed_and_dropped():
    store = ProcessCache(max_bytes=1 << 20, name="test")
    calls = []

    def produce():
        calls.append(1)
        return "v"

    store.get_or_compute("k", produce, ttl=0)  # already expired
    time.sleep(0.01)
    store.get_or_compute("k", produce, ttl=0)
    assert len(calls) == 2
    assert store.stats()["expiries"] >= 1


def test_cache_is_bounded_by_bytes():
    store = ProcessCache(max_bytes=8 * 1024, name="test")
    for i in range(200):
        store.set(f"k{i}", "x" * 512, ttl=60)

    stats = store.stats()
    assert stats["bytes"] <= store.max_bytes, "byte budget exceeded"
    assert stats["entries"] < 200, "nothing was evicted"
    assert stats["evictions"] > 0


def test_oversized_payload_is_not_cached_at_all():
    # Caching it would evict everything else to hold one item.
    store = ProcessCache(max_bytes=1024, name="test")
    store.set("huge", "x" * 100_000, ttl=60)
    assert store.stats()["entries"] == 0
    assert store.stats()["bytes"] == 0


def test_lru_evicts_least_recently_used_first():
    store = ProcessCache(max_bytes=4096, name="test")
    payload = "x" * 900
    for key in ("a", "b", "c"):
        store.set(key, payload, ttl=60)

    store.get("a")  # 'a' becomes most recently used, so 'b' is now the victim
    for key in ("d", "e", "f"):
        store.set(key, payload, ttl=60)

    found_a, _ = store.get("a")
    found_b, _ = store.get("b")
    assert found_a, "recently used entry was evicted before an older one"
    assert not found_b


# ---------------------------------------------------------------------------
# Single-flight
# ---------------------------------------------------------------------------

def test_concurrent_misses_compute_once():
    """
    The core free-tier win: the frontend fires every tab concurrently, and without
    single-flight each request runs the full computation on one shared vCPU.
    """
    store = ProcessCache(max_bytes=1 << 20, name="test")
    calls = []
    barrier = threading.Barrier(8)

    def produce():
        calls.append(1)
        time.sleep(0.05)  # simulate a slow simulation
        return "result"

    results = []

    def worker():
        barrier.wait()  # maximise overlap
        results.append(store.get_or_compute("hot", produce, ttl=60))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, f"expected 1 computation across 8 concurrent callers, got {len(calls)}"
    assert results == ["result"] * 8


def test_flight_lock_table_does_not_grow():
    store = ProcessCache(max_bytes=1 << 20, name="test")
    for i in range(100):
        store.get_or_compute(f"k{i}", lambda: "v", ttl=60)
    assert store._flight_locks == {}, "single-flight locks leaked"
    assert store._flight_waiters == {}


def test_slow_key_does_not_block_unrelated_key():
    store = ProcessCache(max_bytes=1 << 20, name="test")
    started = threading.Event()

    def slow():
        started.set()
        time.sleep(0.3)
        return "slow"

    t = threading.Thread(target=lambda: store.get_or_compute("slow", slow, ttl=60))
    t.start()
    started.wait(timeout=1)

    began = time.perf_counter()
    store.get_or_compute("fast", lambda: "fast", ttl=60)
    elapsed = time.perf_counter() - began
    t.join()

    assert elapsed < 0.2, "an unrelated key waited on the slow key's lock"


# ---------------------------------------------------------------------------
# Request scope
# ---------------------------------------------------------------------------

def test_request_memo_deduplicates_within_a_request():
    calls = []

    @request_memo("ledger")
    def build(session_id):
        calls.append(session_id)
        return {"rows": 3}

    with request_scope():
        for _ in range(10):
            build("s1")
    assert len(calls) == 1


def test_request_memo_does_not_leak_across_requests():
    calls = []

    @request_memo("ledger")
    def build(session_id):
        calls.append(session_id)
        return {"rows": 3}

    with request_scope():
        build("s1")
    with request_scope():
        build("s1")
    assert len(calls) == 2, "state leaked between requests"


def test_request_memo_is_passthrough_outside_a_request():
    # Keeps decorated helpers usable from scripts, tests and the purge thread.
    calls = []

    @request_memo("x")
    def build():
        calls.append(1)
        return 7

    assert build() == 7
    assert build() == 7
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def test_cache_key_is_order_stable_for_kwargs():
    assert cache_key("a", x=1, y=2) == cache_key("a", y=2, x=1)


def test_cache_key_distinguishes_none_from_string_none():
    assert cache_key(None) != cache_key("None")


def test_cache_key_normalises_integral_floats():
    # days=9999 and days=9999.0 must not fragment the cache.
    assert cache_key(days=9999) == cache_key(days=9999.0)


def test_cache_key_separates_distinct_arguments():
    # Guards against the delimiter collision that lossy key building invites.
    assert cache_key("a:b", "c") != cache_key("a", "b:c")


def test_cached_decorator_namespaces_by_function():
    @cached(ttl=60, namespace="ns1", store=DERIVED_CACHE)
    def f(x):
        return f"f{x}"

    @cached(ttl=60, namespace="ns2", store=DERIVED_CACHE)
    def g(x):
        return f"g{x}"

    assert f(1) == "f1"
    assert g(1) == "g1", "namespace collision between two cached functions"
