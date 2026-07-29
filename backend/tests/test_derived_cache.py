"""
Tests for the derived-artifact cache (domains/mutual_funds/derived.py).

The behaviour that matters here is not just "it caches" but:
  - a dashboard load's eight identical simulations become one;
  - concurrent callers (the frontend fires every tab at once) collapse to one
    computation even on a cold cache;
  - a *different* portfolio never reads another portfolio's entry, which for
    financial data is a correctness requirement, not an optimisation.
"""

import threading

import pandas as pd
import pytest

from domains.mutual_funds import derived
from shared.services.cache import DERIVED_CACHE


@pytest.fixture(autouse=True)
def clear_cache():
    DERIVED_CACHE.clear()
    yield
    DERIVED_CACHE.clear()


@pytest.fixture
def spy(monkeypatch):
    """Replace the real simulation with a counter."""
    calls = []

    def fake(df_t, df_h, total_value, bench_series, period_days):
        calls.append({"total": total_value, "days": period_days, "rows": len(df_t)})
        return {"portfolio": [1.0, 2.0], "benchmark": [1.0, 1.5], "dates": ["a", "b"]}

    monkeypatch.setattr(derived, "compute_period_comparison", fake)
    return calls


def _ledger(n=5, fund="Axis Bluechip"):
    return pd.DataFrame({
        "Fund": [fund] * n,
        "Type": ["Purchase"] * n,
        "Amount": [1000.0 * (i + 1) for i in range(n)],
        "Units": [10.0 + i for i in range(n)],
        "Date": pd.date_range("2023-01-01", periods=n, freq="ME"),
    })


def _holdings(fund="Axis Bluechip", units=50.0):
    return pd.DataFrame({
        "Fund": [fund], "ISIN": ["INF001A01011"],
        "Units": [units], "Market Value": [12345.0],
    })


def _bench(n=100, start=100.0):
    return pd.Series(
        [start + i for i in range(n)],
        index=pd.date_range("2023-01-01", periods=n, freq="D"),
    )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_repeat_calls_compute_once(spy):
    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    for _ in range(8):
        derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    assert len(spy) == 1, f"expected 1 simulation for 8 identical calls, got {len(spy)}"


def test_dashboard_load_pattern_collapses(spy):
    """
    Mirrors the real call pattern: /overview, /performance, /drawdown and /journey
    all simulate the same portfolio. Only the distinct (benchmark, period) pairs
    should cost anything.
    """
    df_t, df_h = _ledger(), _holdings()
    nifty, gold = _bench(), _bench(start=500.0)

    derived.cached_period_comparison(df_t, df_h, 12345.0, nifty, 365)   # /overview
    derived.cached_period_comparison(df_t, df_h, 12345.0, nifty, 365)   # /performance
    derived.cached_period_comparison(df_t, df_h, 12345.0, nifty, 365)   # /drawdown
    derived.cached_period_comparison(df_t, df_h, 12345.0, nifty, 9999)  # /journey
    derived.cached_period_comparison(df_t, df_h, 12345.0, gold, 365)    # overlay: Gold

    assert len(spy) == 3, f"expected 3 distinct simulations, got {len(spy)}"


def test_concurrent_callers_collapse_to_one(spy, monkeypatch):
    """Single-flight: this is the win that survives a cold cache."""
    import time

    def slow(df_t, df_h, total_value, bench_series, period_days):
        spy.append(1)
        time.sleep(0.05)
        return {"portfolio": [1.0]}

    monkeypatch.setattr(derived, "compute_period_comparison", slow)

    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    barrier = threading.Barrier(6)

    def worker():
        barrier.wait()
        derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(spy) == 1, f"expected 1 computation across 6 concurrent callers, got {len(spy)}"


# ---------------------------------------------------------------------------
# Key correctness - must never cross portfolios
# ---------------------------------------------------------------------------

def test_different_ledger_gets_its_own_entry(spy):
    df_h, bench = _holdings(), _bench()
    derived.cached_period_comparison(_ledger(n=5), df_h, 12345.0, bench, 365)
    derived.cached_period_comparison(_ledger(n=6), df_h, 12345.0, bench, 365)
    assert len(spy) == 2, "two different ledgers shared a cache entry"


def test_same_shape_different_values_gets_its_own_entry(spy):
    """
    A shape-only fingerprint would collide here. Two portfolios can easily have the
    same row and column count.
    """
    df_h, bench = _holdings(), _bench()
    a = _ledger(n=5, fund="Axis Bluechip")
    b = _ledger(n=5, fund="SBI Small Cap")
    derived.cached_period_comparison(a, df_h, 12345.0, bench, 365)
    derived.cached_period_comparison(b, df_h, 12345.0, bench, 365)
    assert len(spy) == 2, "same-shape ledgers with different contents collided"


def test_changed_total_value_invalidates_implicitly(spy):
    """A live NAV refresh moves total_value, which must yield a fresh entry."""
    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    derived.cached_period_comparison(df_t, df_h, 12999.0, bench, 365)
    assert len(spy) == 2


def test_different_benchmark_gets_its_own_entry(spy):
    df_t, df_h = _ledger(), _holdings()
    derived.cached_period_comparison(df_t, df_h, 12345.0, _bench(start=100.0), 365)
    derived.cached_period_comparison(df_t, df_h, 12345.0, _bench(start=900.0), 365)
    assert len(spy) == 2


def test_different_period_gets_its_own_entry(spy):
    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 1825)
    assert len(spy) == 2


def test_different_holdings_gets_its_own_entry(spy):
    df_t, bench = _ledger(), _bench()
    derived.cached_period_comparison(df_t, _holdings(units=50.0), 12345.0, bench, 365)
    derived.cached_period_comparison(df_t, _holdings(units=75.0), 12345.0, bench, 365)
    assert len(spy) == 2


# ---------------------------------------------------------------------------
# Result integrity
# ---------------------------------------------------------------------------

def test_cached_result_matches_uncached(spy):
    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    first = derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    second = derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    assert first == second


def test_mutating_a_returned_result_does_not_poison_the_cache(spy):
    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    first = derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    first["portfolio"].append(999.0)

    second = derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    assert 999.0 not in second["portfolio"], (
        "a caller's mutation leaked into the cached entry"
    )


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

def test_empty_frames_are_handled(spy):
    out = derived.cached_period_comparison(
        pd.DataFrame(), pd.DataFrame(), 0.0, pd.Series(dtype=float), 365
    )
    assert out is not None
    assert len(spy) == 1


def test_unhashable_frame_bypasses_cache_rather_than_colliding(spy, monkeypatch):
    """
    If a fingerprint cannot be computed we must recompute, never guess. Serving a
    wrong-but-plausible portfolio would be far worse than being slow.
    """
    monkeypatch.setattr(derived, "_frame_fingerprint", lambda df: None)

    df_t, df_h, bench = _ledger(), _holdings(), _bench()
    derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)
    derived.cached_period_comparison(df_t, df_h, 12345.0, bench, 365)

    assert len(spy) == 2, "bypass path incorrectly reused a cache entry"


def test_fingerprint_is_stable_across_equal_frames():
    a, b = _ledger(), _ledger()
    assert derived._frame_fingerprint(a) == derived._frame_fingerprint(b)


def test_fingerprint_distinguishes_reordered_rows():
    a = _ledger(n=5)
    b = a.iloc[::-1].reset_index(drop=True)
    assert derived._frame_fingerprint(a) != derived._frame_fingerprint(b), (
        "row order changes the simulation, so it must change the key"
    )
