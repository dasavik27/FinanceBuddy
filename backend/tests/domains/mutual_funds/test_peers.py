"""
Tests for the peer-comparison path (domains/mutual_funds/tab_common.py).

get_diverse_category_peers was the largest remaining latency source in the domain:
up to eight uncached fund searches, thirty *sequential* NAV round-trips, and thirty
risk-metric computations — all re-run in full on every /compare/peers request.

These pin the three fixes: the whole result is cached and single-flighted, NAV fetches
are overlapped, and results are unchanged by the reordering that concurrency implies.
"""

import threading
import time

import pandas as pd
import pytest

from domains.mutual_funds import tab_common
from shared.services.cache import MARKET_CACHE


@pytest.fixture(autouse=True)
def clear_cache():
    MARKET_CACHE.clear()
    yield
    MARKET_CACHE.clear()


def _nav(seed: float, n: int = 2000) -> pd.Series:
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    return pd.Series([seed + (i * 0.01) for i in range(n)], index=idx)


@pytest.fixture
def stub_market(monkeypatch):
    """
    Replace every network entry point the peers path uses, and record calls.

    `fetch_delays` lets a test make each NAV fetch slow enough that sequential vs
    concurrent execution is distinguishable by wall-clock.
    """
    state = {"searches": [], "nav_fetches": [], "nav_delay": 0.0}

    catalogue = [
        {"symbol": str(100000 + i), "name": f"{amc} Large Cap Fund Direct Growth",
         "type": "Mutual Fund", "exchange": "PROVIDER"}
        for i, amc in enumerate(
            ["Axis", "SBI", "HDFC", "ICICI", "Kotak", "Nippon", "UTI", "Mirae"]
        )
    ]

    def fake_search(query):
        state["searches"].append(query)
        return list(catalogue)

    def fake_nav(code, days=0, **kwargs):
        state["nav_fetches"].append(str(code))
        if state["nav_delay"]:
            time.sleep(state["nav_delay"])
        return _nav(50.0 + (int(code) % 100))

    def fake_ter(code, plan=None):
        return 0.5

    def fake_bench(ticker, days=0, **kwargs):
        return _nav(1000.0)

    monkeypatch.setattr(tab_common, "search_mutual_funds", fake_search)
    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", fake_nav)
    monkeypatch.setattr(tab_common, "fetch_fund_ter", fake_ter)
    monkeypatch.setattr(tab_common, "fetch_benchmark_series", fake_bench)
    return state


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_repeat_calls_hit_the_cache(stub_market):
    tab_common.get_diverse_category_peers("Large Cap", "", 5)
    after_first = len(stub_market["nav_fetches"])
    assert after_first > 0

    for _ in range(5):
        tab_common.get_diverse_category_peers("Large Cap", "", 5)

    assert len(stub_market["nav_fetches"]) == after_first, (
        "repeat requests re-fetched NAV data instead of using the cache"
    )
    assert len(stub_market["searches"]) > 0


def test_cache_key_separates_categories(stub_market):
    tab_common.get_diverse_category_peers("Large Cap", "", 5)
    first = len(stub_market["nav_fetches"])
    tab_common.get_diverse_category_peers("Mid Cap", "", 5)
    assert len(stub_market["nav_fetches"]) > first, "different categories shared an entry"


def test_cache_key_separates_base_fund(stub_market):
    """base_fund_name excludes the fund itself, so it changes the result set."""
    a, _ = tab_common.get_diverse_category_peers("Large Cap", "Axis Large Cap Fund", 5)
    b, _ = tab_common.get_diverse_category_peers("Large Cap", "SBI Large Cap Fund", 5)
    a_names = {p["name"] for p in a}
    b_names = {p["name"] for p in b}
    assert not any("Axis" in n for n in a_names), "base fund was not excluded"
    assert not any("SBI" in n for n in b_names), "base fund was not excluded"


def test_concurrent_requests_compute_once(stub_market):
    stub_market["nav_delay"] = 0.01
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        tab_common.get_diverse_category_peers("Large Cap", "", 5)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Single-flight: one winner does the work, the other four read its result.
    unique_codes = set(stub_market["nav_fetches"])
    assert len(stub_market["nav_fetches"]) == len(unique_codes), (
        "concurrent callers duplicated NAV fetches instead of single-flighting"
    )


# ---------------------------------------------------------------------------
# Concurrency of the fetch fan-out
# ---------------------------------------------------------------------------

def test_nav_fetches_are_overlapped(monkeypatch):
    """
    Asserts concurrency *structurally* - by observing how many fetches are in flight
    simultaneously - rather than by wall-clock timing.

    Two earlier versions of this test were wrong in different ways, both worth
    recording. The first timed the whole endpoint, which conflates fetch latency with
    the per-peer risk-metric computation (real CPU work that swamps the signal) and
    so reported concurrent fetches as sequential. The second timed the helper alone
    but still asserted on elapsed time, which flakes on a loaded machine.

    An in-flight counter has neither problem: if the fan-out were sequential the peak
    would be exactly 1 no matter how slow the machine is.
    """
    codes = [str(200000 + i) for i in range(8)]
    lock = threading.Lock()
    state = {"in_flight": 0, "peak": 0}

    def tracking_fetch(code, days=0, **kwargs):
        with lock:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        try:
            time.sleep(0.05)  # hold the slot so any overlap is observable
            return _nav(50.0)
        finally:
            with lock:
                state["in_flight"] -= 1

    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", tracking_fetch)
    navs = tab_common._prefetch_peer_navs(codes)

    assert len(navs) == len(codes)
    assert state["peak"] >= 2, (
        f"peak concurrent fetches was {state['peak']} - fan-out is sequential"
    )
    assert state["peak"] <= tab_common._PEER_FETCH_WORKERS, (
        f"peak concurrent fetches was {state['peak']}, above the "
        f"{tab_common._PEER_FETCH_WORKERS}-worker cap that protects the upstream API"
    )


def test_prefetch_dedupes_repeated_codes(monkeypatch):
    calls = []

    def counting_fetch(code, days=0, **kwargs):
        calls.append(str(code))
        return _nav(50.0)

    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", counting_fetch)
    tab_common._prefetch_peer_navs(["111", "222", "111", "222", "111"])
    assert sorted(calls) == ["111", "222"]


def test_prefetch_handles_empty_input():
    assert tab_common._prefetch_peer_navs([]) == {}


def test_each_peer_is_fetched_at_most_once(stub_market):
    tab_common.get_diverse_category_peers("Large Cap", "", 5)
    fetches = stub_market["nav_fetches"]
    assert len(fetches) == len(set(fetches)), f"duplicate NAV fetches: {fetches}"


def test_self_match_is_not_fetched(stub_market):
    """No point spending a request on a fund we are about to skip."""
    tab_common.get_diverse_category_peers("Large Cap", "Axis Large Cap Fund Direct", 5)
    assert "100000" not in stub_market["nav_fetches"], (
        "fetched NAV history for the fund being excluded"
    )


def test_fetch_failure_degrades_gracefully(stub_market, monkeypatch):
    def flaky(code, days=0, **kwargs):
        stub_market["nav_fetches"].append(str(code))
        if str(code) in ("100001", "100003"):
            raise RuntimeError("upstream 503")
        return _nav(50.0 + (int(code) % 100))

    monkeypatch.setattr(tab_common, "fetch_nav_series_by_code", flaky)

    peers, _ = tab_common.get_diverse_category_peers("Large Cap", "", 5)
    assert isinstance(peers, list), "a failed peer fetch broke the whole response"
    names = {p["name"] for p in peers}
    assert not any("SBI" in n for n in names)


# ---------------------------------------------------------------------------
# Result shape preserved
# ---------------------------------------------------------------------------

def test_result_shape_and_ordering(stub_market):
    peers, fallback = tab_common.get_diverse_category_peers("Large Cap", "", 5)

    assert isinstance(fallback, bool)
    assert len(peers) <= 5

    for p in peers:
        for field in ("name", "symbol", "code", "er", "returns", "ret1y", "ret3y",
                      "ret5y", "consistency", "consistency_str", "alpha", "alpha_str",
                      "sharpe", "pe_ratio", "amc"):
            assert field in p, f"missing field {field!r} in peer payload"

    # Sorted by 1Y trailing, descending.
    ret1y = [p["ret1y"] for p in peers]
    assert ret1y == sorted(ret1y, reverse=True), f"ordering not preserved: {ret1y}"


def test_amc_diversity_is_enforced(stub_market):
    peers, _ = tab_common.get_diverse_category_peers("Large Cap", "", 5)
    amcs = [p["amc"] for p in peers]
    assert len(amcs) == len(set(amcs)), f"duplicate AMCs in peer set: {amcs}"


def test_consistency_string_matches_number(stub_market):
    """These came from two separate computations of the same thing; now one."""
    peers, _ = tab_common.get_diverse_category_peers("Large Cap", "", 5)
    for p in peers:
        assert p["consistency_str"] == f"{p['consistency']}/10"


def test_cached_result_is_not_shared_by_reference(stub_market):
    first, _ = tab_common.get_diverse_category_peers("Large Cap", "", 5)
    if not first:
        pytest.skip("no peers produced by the stub")
    first[0]["name"] = "MUTATED"

    second, _ = tab_common.get_diverse_category_peers("Large Cap", "", 5)
    assert second[0]["name"] != "MUTATED", "caller mutation leaked into the cached entry"


def test_no_peers_returns_empty_without_raising(stub_market, monkeypatch):
    monkeypatch.setattr(tab_common, "search_mutual_funds", lambda q: [])
    peers, fallback = tab_common.get_diverse_category_peers("Nonexistent Cap", "", 5)
    assert peers == []
    assert fallback is True
