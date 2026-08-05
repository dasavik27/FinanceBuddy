"""
test_shared_janitor_and_cache_full.py

Comprehensive unit tests for:
- shared/janitor.py (registration, deduplication, error isolation, daemon lifecycle)
- shared/cache.py (key hashing, get/set, TTL expiration, corrupt payload unlinking, invalidation, size-based eviction, stats)
"""

import json
import os
import threading
import time
from unittest.mock import MagicMock
import pytest

from shared import janitor, config
from shared.cache import MarketCache


def test_janitor_lifecycle_and_error_isolation(monkeypatch):
    # 1. Register & deduplicate
    sweep1 = MagicMock(return_value="ok1")
    sweep2 = MagicMock(return_value="ok2")
    sweep_fail = MagicMock(side_effect=RuntimeError("Sweep exploded"))

    janitor.register("test_sweep_1", sweep1)
    janitor.register("test_sweep_fail", sweep_fail)
    assert "test_sweep_1" in janitor.registered()
    assert "test_sweep_fail" in janitor.registered()

    # Re-register same name replaces existing
    janitor.register("test_sweep_1", sweep2)
    assert janitor.registered().count("test_sweep_1") == 1

    # 2. run_once isolation
    results = janitor.run_once()
    assert results["test_sweep_1"] == "ok2"
    assert results["test_sweep_fail"] is None  # Error caught safely

    # 3. _worker execution
    called = []
    def fake_sleep(sec):
        called.append(sec)
        if len(called) >= 1:
            raise KeyboardInterrupt("Stop worker loop")

    monkeypatch.setattr(time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        janitor._worker(5)

    # 4. start daemon thread
    assert janitor.start(interval=600) is True
    # Second start is idempotent
    assert janitor.start(interval=600) is False


def test_market_cache_get_set_and_ttl(tmp_path, monkeypatch):
    test_cache_dir = str(tmp_path / "market_cache")
    monkeypatch.setattr(config, "CACHE_DIR", test_cache_dir)
    monkeypatch.setattr("shared.cache.CACHE_DIR", test_cache_dir)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 5)

    # 1. Normal round-trip
    MarketCache.set("scheme_123", {"nav": 45.67})
    data = MarketCache.get("scheme_123")
    assert data == {"nav": 45.67}

    # 2. Disabled TTL (<= 0)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 0)
    MarketCache.set("scheme_disabled", {"val": 1})
    assert MarketCache.get("scheme_123") is None
    assert MarketCache.get("scheme_disabled") is None

    # Reset TTL
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 5)

    # 3. Nonexistent key
    assert MarketCache.get("missing_key_xyz") is None

    # 4. Corrupted JSON file
    path = MarketCache._get_path("corrupt_key")
    os.makedirs(test_cache_dir, exist_ok=True)
    with open(path, "w") as f:
        f.write("{not-json")
    assert MarketCache.get("corrupt_key") is None
    assert not os.path.exists(path)  # unlinked

    # 5. Expired timestamp
    expired_path = MarketCache._get_path("expired_key")
    with open(expired_path, "w") as f:
        json.dump({"_timestamp": time.time() - 1000, "payload": {"old": True}}, f)
    assert MarketCache.get("expired_key") is None
    assert not os.path.exists(expired_path)

    # 6. Delete
    MarketCache.set("to_delete", {"del": True})
    assert MarketCache.get("to_delete") == {"del": True}
    MarketCache.delete("to_delete")
    assert MarketCache.get("to_delete") is None


def test_market_cache_invalidation_and_eviction(tmp_path, monkeypatch):
    test_cache_dir = str(tmp_path / "market_cache_2")
    monkeypatch.setattr(config, "CACHE_DIR", test_cache_dir)
    monkeypatch.setattr("shared.cache.CACHE_DIR", test_cache_dir)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)

    MarketCache.set("stock_infy", {"price": 1800})
    MarketCache.set("stock_tcs", {"price": 3900})
    MarketCache.set("mf_hdfc", {"nav": 120})

    # Invalidate with empty string raises ValueError
    with pytest.raises(ValueError):
        MarketCache.invalidate("")

    # Invalidate pattern
    removed = MarketCache.invalidate("stock")
    assert removed == 2
    assert MarketCache.get("stock_infy") is None
    assert MarketCache.get("mf_hdfc") == {"nav": 120}

    # Invalidate all
    all_removed = MarketCache.invalidate_all()
    assert all_removed == 1
    assert MarketCache.get("mf_hdfc") is None


def test_market_cache_sweep_and_stats(tmp_path, monkeypatch):
    test_cache_dir = str(tmp_path / "market_cache_3")
    monkeypatch.setattr(config, "CACHE_DIR", test_cache_dir)
    monkeypatch.setattr("shared.cache.CACHE_DIR", test_cache_dir)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 10)
    monkeypatch.setattr("shared.cache.MAX_CACHE_BYTES", 50)  # Very small budget to force eviction

    # Create orphaned .tmp files and expired files
    os.makedirs(test_cache_dir, exist_ok=True)
    old_tmp = os.path.join(test_cache_dir, "test.tmp")
    with open(old_tmp, "w") as f:
        f.write("temporary data")
    os.utime(old_tmp, (time.time() - 400, time.time() - 400))

    expired_file = os.path.join(test_cache_dir, "expired.json")
    with open(expired_file, "w") as f:
        json.dump({"payload": "old"}, f)
    os.utime(expired_file, (time.time() - 1000, time.time() - 1000))

    # Add entries
    MarketCache.set("entry_1", {"content": "large content chunk number 1"})
    MarketCache.set("entry_2", {"content": "large content chunk number 2"})

    # Run sweep
    expired, evicted = MarketCache.sweep()
    assert os.path.exists(old_tmp) is False
    assert os.path.exists(expired_file) is False
    assert evicted >= 1

    # Stats
    stats = MarketCache.stats()
    assert stats["name"] == "L2-disk"
    assert stats["dir"] == test_cache_dir
    assert isinstance(stats["bytes"], int)
    assert isinstance(stats["entries"], int)

    # _maybe_sweep coverage with exception
    monkeypatch.setattr("shared.cache._last_sweep", 0.0)
    monkeypatch.setattr(MarketCache, "sweep", MagicMock(side_effect=RuntimeError("Sweep error")))
    MarketCache._maybe_sweep()


def test_market_cache_filesystem_errors_and_edge_cases(tmp_path, monkeypatch):
    test_cache_dir = str(tmp_path / "market_cache_err")
    monkeypatch.setattr(config, "CACHE_DIR", test_cache_dir)
    monkeypatch.setattr("shared.cache.CACHE_DIR", test_cache_dir)
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 10)

    # 1. Write error in set()
    monkeypatch.setattr(os, "replace", MagicMock(side_effect=OSError("Disk write failure")))
    MarketCache.set("write_err_key", {"data": 123})
    assert MarketCache.get("write_err_key") is None

    # 2. _listdir exception
    monkeypatch.setattr(os, "listdir", MagicMock(side_effect=OSError("Read error")))
    assert MarketCache._listdir() == []

    # 3. _unlink exception
    monkeypatch.setattr(os, "remove", MagicMock(side_effect=OSError("Permission denied")))
    MarketCache._unlink("/nonexistent/path/xyz")

