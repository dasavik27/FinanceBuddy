"""
Caching behaviour for the market-data fetches that were previously uncached.

These pin *call counts*, not timings — the property that matters is "how many times
did we hit the upstream", and asserting that structurally keeps the test fast and
non-flaky.
"""

import threading
import time

import pytest

from shared import config
from shared.services import market_data, market_indices
from shared.services.cache import MARKET_CACHE


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    MARKET_CACHE.clear()
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    monkeypatch.setattr(market_data.config, "CACHE_TTL_MINUTES", 60)
    yield
    MARKET_CACHE.clear()


# ── B5: the ten-way TER download ──────────────────────────────────────────────

def test_concurrent_ter_misses_cause_one_download(monkeypatch):
    """
    /holdings enriches every holding inside ThreadPoolExecutor(max_workers=10), and
    each worker calls fetch_fund_ter. The old code checked a module dict under a lock
    but released it before fetching, so all ten missed at once and each downloaded the
    full AMFI TER file.
    """
    calls = []
    barrier = threading.Barrier(10)

    def slow_fetch():
        calls.append(1)
        time.sleep(0.2)  # widen the window a lock-free version would race through
        return {"12345": 0.62, "67890": 1.15}

    monkeypatch.setattr(market_data, "_fetch_amfi_ter_all_uncached", slow_fetch)
    monkeypatch.setattr(market_data.MarketCache, "get", lambda *a, **k: None)
    monkeypatch.setattr(market_data.MarketCache, "set", lambda *a, **k: None)

    results = []

    def worker():
        barrier.wait(timeout=10)
        results.append(market_data.fetch_fund_ter("12345"))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert len(calls) == 1, f"expected single-flight, got {len(calls)} downloads"
    assert results == [0.62] * 10, "waiters did not all observe the winner's result"


def test_ter_failure_is_negatively_cached(monkeypatch):
    """
    `if ter_map:` meant an empty parse was never stored, so a down AMFI endpoint was
    re-downloaded on every request forever.
    """
    calls = []

    def failing_fetch():
        calls.append(1)
        return {}

    monkeypatch.setattr(market_data, "_fetch_amfi_ter_all_uncached", failing_fetch)
    monkeypatch.setattr(market_data.MarketCache, "get", lambda *a, **k: None)
    monkeypatch.setattr(market_data.MarketCache, "set", lambda *a, **k: None)

    for _ in range(5):
        assert market_data.fetch_fund_ter("12345") is None

    assert len(calls) == 1, f"failed TER fetch retried {len(calls)} times; expected 1"


def test_ter_uses_the_daily_ttl_not_the_global_default():
    """AMFI publishes once a day; the global default is 60 minutes."""
    from shared.services.cache import ttl_for
    assert ttl_for("live_navs") >= 4 * 3600


# ── B6: the polled live quote ─────────────────────────────────────────────────

def test_market_summary_is_cached(monkeypatch):
    calls = []

    def fake():
        calls.append(1)
        return {"nifty": {"price": 24000.0, "change": 10.0, "change_pct": 0.04, "is_live": True}}

    monkeypatch.setattr(market_indices, "_fetch_live_market_summary_uncached", fake)

    first = market_indices.fetch_live_market_summary()
    for _ in range(5):
        market_indices.fetch_live_market_summary()

    assert len(calls) == 1, f"polled endpoint hit upstream {len(calls)} times"
    assert first["nifty"]["price"] == 24000.0


def test_market_summary_caches_the_failure_fallback(monkeypatch):
    """
    Caching only successes means a rate-limited Yahoo is re-hit on every request -
    precisely when hammering it is worst. The fallback dict must be cached too.
    """
    calls = []

    # The uncached function never raises - it swallows upstream errors and returns the
    # is_live=False fallback. So the thing to assert is that the *fallback* is cached.
    def returns_fallback():
        calls.append(1)
        return {"nifty": {"price": 0.0, "change": 0.0, "change_pct": 0.0, "is_live": False}}

    monkeypatch.setattr(market_indices, "_fetch_live_market_summary_uncached", returns_fallback)

    results = [market_indices.fetch_live_market_summary() for _ in range(4)]

    assert len(calls) == 1, f"fallback was recomputed {len(calls)} times"
    assert all(r["nifty"]["is_live"] is False for r in results)


# ── B7: cacheable-empty benchmarks ────────────────────────────────────────────

def test_empty_benchmark_fallback_is_cached(monkeypatch):
    """
    An empty cached series could not be distinguished from "not cached", so the
    uncached bounded-window fallback re-ran on every request - two Yahoo downloads
    each, four benchmarks per /benchmark-overlay.
    """
    import pandas as pd

    calls = []

    def always_empty(ticker, period_days):
        calls.append((ticker, period_days))
        return pd.Series(dtype=float)

    monkeypatch.setattr(market_indices, "_fetch_benchmark_series_uncached", always_empty)

    for _ in range(4):
        result = market_indices.fetch_benchmark_series("^DELISTED", 1855)
        assert result.empty

    # One full-history attempt plus one bounded-window fallback, then cached.
    assert len(calls) <= 2, f"dead ticker refetched {len(calls)} times"


def test_nselib_tier_is_gone():
    """
    The 'tier 4' NSE fallback was dead code holding the only untimeouted outbound
    HTTP call in the backend. If it comes back, it needs an explicit timeout.
    """
    assert not hasattr(market_indices, "_fetch_nselib_series")
    assert not hasattr(market_indices, "_NSELIB_MAP")


# ── dead module-level caches ───────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "_LIVE_NAV_CACHE", "_LIVE_NAV_CACHE_TS", "_NAV_SERIES_CACHE",
    "_NAV_CACHE_TTL", "_TER_CACHE", "_TER_CACHE_TS", "_HTTP_SESSION",
])
def test_unbudgeted_module_caches_are_gone(name):
    """
    These held a second copy of the AMFI bundle outside the 32 MB MARKET_CACHE
    budget, so the tier could report 20/32 MB while the process held roughly double.
    _LIVE_NAV_CACHE in particular was written twice and never read.
    """
    assert not hasattr(market_data, name), (
        f"{name} is back; it shadows the L1 byte budget with an unbounded copy"
    )
