"""
Tests for the L2 disk cache (shared/cache.py) and the market-data layer built on it.

Like test_cache_core.py these are largely regression tests. The behaviours pinned
here were all previously broken:

  - key sanitization was lossy, so two different scheme codes could share one file
    and silently serve each other's NAV history;
  - writes were not atomic, so a concurrent reader could read a truncated file;
  - expired entries were reported as misses but never deleted, so the directory
    only grew;
  - invalidate() defaulted to an empty pattern, which wiped the whole cache;
  - the AMFI bundle was refetched and reparsed on every single call.
"""

import json
import os
import threading

import pytest

from shared import config
from shared.cache import MarketCache


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point both the config module and shared.cache at a throwaway directory."""
    d = tmp_path / ".cache"
    d.mkdir()
    monkeypatch.setattr(config, "CACHE_DIR", str(d))
    monkeypatch.setattr("shared.cache.CACHE_DIR", str(d))
    # The TTL is now read through the config module at each use site rather than bound
    # into shared.cache at import, so there is a single value to patch. (That binding
    # was the bug: POST /market/config mutated config but never reached the disk tier.)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    return d


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------

def test_keys_differing_only_in_punctuation_do_not_collide(cache_dir):
    """
    `a-b` and `a_b` both sanitized to `a_b` before, so one scheme's NAV history
    could be served for another. That is a correctness bug, not a perf one.
    """
    MarketCache.set("nav_series_a-b", {"01-01-2024": 100.0})
    MarketCache.set("nav_series_a_b", {"01-01-2024": 200.0})

    assert MarketCache.get("nav_series_a-b") == {"01-01-2024": 100.0}
    assert MarketCache.get("nav_series_a_b") == {"01-01-2024": 200.0}


def test_long_keys_remain_distinct(cache_dir):
    a = "portfolio_" + "X" * 300 + "_alpha"
    b = "portfolio_" + "X" * 300 + "_beta"
    MarketCache.set(a, "A")
    MarketCache.set(b, "B")
    assert MarketCache.get(a) == "A"
    assert MarketCache.get(b) == "B"


def test_filename_stays_within_filesystem_limits(cache_dir):
    MarketCache.set("k" * 500, "v")
    for name in os.listdir(cache_dir):
        assert len(name) < 255, "filename would break on most filesystems"


# ---------------------------------------------------------------------------
# Expiry and eviction
# ---------------------------------------------------------------------------

def test_expired_entry_is_deleted_not_merely_ignored(cache_dir):
    MarketCache.set("k", "v")
    assert len(os.listdir(cache_dir)) == 1

    # Age the entry rather than lowering the TTL: ttl <= 0 disables the cache
    # entirely, which would not exercise the expiry path.
    path = os.path.join(str(cache_dir), os.listdir(cache_dir)[0])
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_timestamp"] = 0  # epoch: long expired
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    assert MarketCache.get("k") is None
    assert os.listdir(cache_dir) == [], "expired entry was left on disk"


def test_sweep_enforces_size_budget(cache_dir, monkeypatch):
    monkeypatch.setattr("shared.cache.MAX_CACHE_BYTES", 4096)
    for i in range(60):
        MarketCache.set(f"key_{i}", "x" * 500)

    MarketCache.sweep()
    total = sum(
        os.stat(os.path.join(str(cache_dir), n)).st_size for n in os.listdir(cache_dir)
    )
    assert total <= 4096, f"size budget not enforced: {total} bytes remain"


def test_corrupt_file_is_treated_as_miss_and_removed(cache_dir):
    MarketCache.set("k", {"a": 1})
    path = os.path.join(str(cache_dir), os.listdir(cache_dir)[0])
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"_timestamp": 123, "payload": {"a"')  # truncated mid-write

    assert MarketCache.get("k") is None
    assert os.listdir(cache_dir) == []


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------

def test_no_temp_files_remain_after_writes(cache_dir):
    for i in range(20):
        MarketCache.set(f"k{i}", {"nav": i})
    leftovers = [n for n in os.listdir(cache_dir) if n.endswith(".tmp")]
    assert leftovers == [], f"temp files leaked: {leftovers}"


def test_concurrent_readers_never_see_a_partial_file(cache_dir):
    """
    With a plain open()+dump() a reader can observe a truncated file. The
    temp-file-plus-replace pattern makes every read see a complete document.
    """
    payload = {f"{d:02d}-01-2024": float(d) for d in range(1, 29)}
    MarketCache.set("hot", payload)

    errors = []
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            MarketCache.set("hot", payload)

    def reader():
        while not stop.is_set():
            got = MarketCache.get("hot")
            if got is not None and got != payload:
                errors.append(got)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader),
               threading.Thread(target=reader)]
    for t in threads:
        t.start()
    threading.Event().wait(0.5)
    stop.set()
    for t in threads:
        t.join()

    assert errors == [], f"observed {len(errors)} partial/corrupt reads"


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

def test_bare_invalidate_is_rejected(cache_dir):
    """An accidental bare invalidate() used to delete the entire cache."""
    MarketCache.set("keep_me", "v")
    with pytest.raises(ValueError):
        MarketCache.invalidate("")
    assert MarketCache.get("keep_me") == "v"


def test_invalidate_by_pattern_is_targeted(cache_dir):
    MarketCache.set("nav_series_111", "a")
    MarketCache.set("nav_series_222", "b")
    MarketCache.set("portfolio_XYZ", "c")

    MarketCache.invalidate("nav_series_111")

    assert MarketCache.get("nav_series_111") is None
    assert MarketCache.get("nav_series_222") == "b"
    assert MarketCache.get("portfolio_XYZ") == "c"


def test_invalidate_all_clears_everything(cache_dir):
    MarketCache.set("a", 1)
    MarketCache.set("b", 2)
    assert MarketCache.invalidate_all() == 2
    assert MarketCache.get("a") is None


def test_delete_is_exact_key_only(cache_dir):
    MarketCache.set("nav_series_11", "a")
    MarketCache.set("nav_series_111", "b")
    MarketCache.delete("nav_series_11")
    assert MarketCache.get("nav_series_11") is None
    assert MarketCache.get("nav_series_111") == "b", "delete matched a prefix, not the exact key"


# ---------------------------------------------------------------------------
# AMFI bundle: one download serves live NAVs, ISIN map and NAV dates
# ---------------------------------------------------------------------------

@pytest.fixture
def amfi_stub(monkeypatch, cache_dir):
    """Count how often the network parse actually runs."""
    from shared.services import market_data
    from shared.services.cache import MARKET_CACHE

    MARKET_CACHE.clear()
    market_data.clear_market_data_cache()

    calls = []

    def fake_uncached():
        calls.append(1)
        live = {"INF001A01011": 100.0, "INF002A01012": 250.0}
        isin = {"INF001A01011": "111111", "INF002A01012": "222222"}
        date = {"INF001A01011": "29-07-2026", "INF002A01012": "29-07-2026"}
        with market_data._CACHE_LOCK:
            market_data._ISIN_TO_CODE_CACHE.update(isin)
        return live, isin, date

    monkeypatch.setattr(market_data, "_fetch_amfi_data_uncached", fake_uncached)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    monkeypatch.setattr(market_data.config, "CACHE_TTL_MINUTES", 60)
    yield market_data, calls
    MARKET_CACHE.clear()
    market_data.clear_market_data_cache()


def test_amfi_bundle_downloaded_once_for_all_three_consumers(amfi_stub):
    """
    fetch_live_navs, fetch_live_navs_with_date and resolve_scheme_code_from_isin all
    need the same file. fetch_live_navs_with_date used to bypass the cache outright
    ("date mapping is not cached yet"), forcing a full multi-MB download on every
    upload and every /sync.
    """
    market_data, calls = amfi_stub

    market_data.fetch_live_navs()
    market_data.fetch_live_navs_with_date()
    market_data.resolve_scheme_code_from_isin("INF001A01011")
    market_data.fetch_live_navs()

    assert len(calls) == 1, f"expected 1 AMFI fetch across all consumers, got {len(calls)}"


def test_unresolvable_isin_is_negatively_cached(amfi_stub):
    """
    An ISIN absent from AMFI (closed scheme, segregated portfolio) used to fall
    through to a bundle refresh on every single lookup.
    """
    market_data, calls = amfi_stub

    assert market_data.resolve_scheme_code_from_isin("INF999Z99999") == ""
    first = len(calls)
    for _ in range(10):
        assert market_data.resolve_scheme_code_from_isin("INF999Z99999") == ""

    assert len(calls) == first, "repeated misses re-triggered the AMFI fetch"


def test_resolvable_isin_returns_code(amfi_stub):
    market_data, _ = amfi_stub
    assert market_data.resolve_scheme_code_from_isin("INF002A01012") == "222222"


def test_isin_resolution_is_case_and_space_insensitive(amfi_stub):
    market_data, _ = amfi_stub
    assert market_data.resolve_scheme_code_from_isin("  inf001a01011 ") == "111111"
