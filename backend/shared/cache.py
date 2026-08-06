"""
shared/cache.py - MarketCache, the L2 (disk) cache tier.

Holds raw network payloads as JSON so they survive a process restart. Parsed
objects belong in the L1 tier (shared/services/cache.py); this tier is deliberately
dumb and serialization-only.

Caveat worth knowing when reasoning about production behaviour: free-tier hosts
generally do not provide a persistent disk, so on those a restart clears this tier
too. Treat it as a warm-start optimisation, not as storage.
"""

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, List, Optional, Tuple

# Imported as a module, deliberately: NOT `from shared.config import CACHE_TTL_MINUTES`.
# That form binds the value at import time, while POST /market/config mutates the
# module attribute - so the disk tier kept expiring against the boot-time TTL forever
# while the in-process tier used the new one. Setting the TTL to 0 to disable caching
# left this tier fully active.
from shared import config, janitor
from shared.config import CACHE_DIR

logger = logging.getLogger(__name__)

# Total budget for the cache directory. Without a ceiling this directory only ever
# grows: expired entries were previously never removed, merely ignored on read.
MAX_CACHE_BYTES = int(os.getenv("FINANCEBUDDY_DISK_CACHE_MB", "64")) * 1024 * 1024

# Serialises writes and eviction within this process. Does not coordinate across
# processes, but we run a single worker; atomic renames keep readers safe regardless.
_IO_LOCK = threading.Lock()

_SWEEP_INTERVAL_SEC = 300
_last_sweep = 0.0


class MarketCache:
    """
    Persistent JSON cache for market data.

    Ensures repeat analysis is performant while allowing on-demand refreshes.
    """

    # -- key handling -------------------------------------------------------

    @staticmethod
    def _get_path(key: str) -> str:
        """
        Map a key to a filename.

        The readable prefix is for human debugging only; correctness comes from the
        appended hash. Sanitizing alone was lossy - `nav_series_a-b` and
        `nav_series_a_b` collapsed onto the same file, so two different schemes could
        silently serve each other's NAV history.
        """
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        readable = "".join(c if c.isalnum() else "_" for c in key)[:60]
        return os.path.join(CACHE_DIR, f"{readable}.{digest}.json")

    # -- read/write ---------------------------------------------------------

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Retrieve data from cache if present and not expired."""
        if config.CACHE_TTL_MINUTES <= 0:
            return None

        path = cls._get_path(key)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except Exception:
            # Corrupt or partially-written file: drop it so the next write is clean.
            cls._unlink(path)
            return None

        if (time.time() - data.get("_timestamp", 0)) > (config.CACHE_TTL_MINUTES * 60):
            # Delete rather than merely reporting a miss, otherwise expired entries
            # accumulate forever.
            cls._unlink(path)
            return None

        cls._maybe_sweep()
        return data.get("payload")

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        """
        Persist data to cache.

        Writes to a temp file and renames. os.replace is atomic on both POSIX and
        Windows, so a concurrent reader sees either the old file or the new one -
        never the truncated middle of a write, which the previous open()+dump()
        allowed.
        """
        if config.CACHE_TTL_MINUTES <= 0:
            return

        path = cls._get_path(key)
        payload = {"_timestamp": time.time(), "payload": value}

        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, path)
        except Exception as e:
            logger.error(f"[CACHE ERROR] Failed to persist {key}: {e}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            return

        cls._maybe_sweep()

    @classmethod
    def delete(cls, key: str) -> None:
        """Remove one entry by its exact key."""
        cls._unlink(cls._get_path(key))

    # -- invalidation -------------------------------------------------------

    @classmethod
    def invalidate(cls, key_pattern: str) -> int:
        """
        Remove entries whose readable prefix contains `key_pattern`.

        `key_pattern` is required and must be non-empty: it previously defaulted to
        "", and an accidental bare invalidate() wiped the entire cache directory.
        Use invalidate_all() when that is genuinely what you want.

        Returns the number of files removed.
        """
        if not key_pattern:
            raise ValueError(
                "invalidate() requires a non-empty pattern; call invalidate_all() "
                "to clear the whole cache deliberately."
            )

        needle = "".join(c if c.isalnum() else "_" for c in key_pattern)
        removed = 0
        for name in cls._listdir():
            if needle in name:
                cls._unlink(os.path.join(CACHE_DIR, name))
                removed += 1
        return removed

    @classmethod
    def invalidate_all(cls) -> int:
        """Clear the entire disk cache. Explicit by design."""
        removed = 0
        for name in cls._listdir():
            cls._unlink(os.path.join(CACHE_DIR, name))
            removed += 1
        return removed

    # -- maintenance --------------------------------------------------------

    @classmethod
    def _maybe_sweep(cls) -> None:
        """
        Occasionally enforce the size budget.

        Rate-limited because it stats every file: at most once per
        _SWEEP_INTERVAL_SEC, so a burst of cache writes does not turn into a burst
        of directory scans.
        """
        global _last_sweep
        now = time.time()
        if now - _last_sweep < _SWEEP_INTERVAL_SEC:
            return

        with _IO_LOCK:
            if now - _last_sweep < _SWEEP_INTERVAL_SEC:
                return  # pragma: no cover — defensive / hard to exercise in unit tests
            _last_sweep = now

        try:
            cls.sweep()
        except Exception as e:
            logger.error(f"[CACHE SWEEP ERROR] {e}")

    @classmethod
    def sweep(cls) -> Tuple[int, int]:
        """
        Drop expired entries, then evict oldest-first until under budget.

        Returns (expired_removed, evicted_for_size).
        """
        ttl_sec = config.CACHE_TTL_MINUTES * 60
        entries: List[Tuple[float, int, str]] = []  # (mtime, size, path)
        expired = 0
        now = time.time()

        for name in cls._listdir():
            path = os.path.join(CACHE_DIR, name)
            try:
                stat = os.stat(path)
            except OSError:  # pragma: no cover — defensive / hard to exercise in unit tests
                continue  # pragma: no cover — defensive / hard to exercise in unit tests

            if name.endswith(".tmp"):
                # Orphaned temp file from an interrupted write.
                if now - stat.st_mtime > 300:
                    cls._unlink(path)
                continue

            if ttl_sec > 0 and (now - stat.st_mtime) > ttl_sec:
                cls._unlink(path)
                expired += 1
                continue

            entries.append((stat.st_mtime, stat.st_size, path))

        total = sum(size for _, size, _ in entries)
        evicted = 0
        if total > MAX_CACHE_BYTES:
            entries.sort(key=lambda e: e[0])  # oldest first
            for _, size, path in entries:
                if total <= MAX_CACHE_BYTES:
                    break
                cls._unlink(path)
                total -= size
                evicted += 1

        if expired or evicted:
            logger.info(
                "[CACHE SWEEP] removed %d expired, evicted %d for size budget",
                expired, evicted,
            )
        return expired, evicted

    @classmethod
    def stats(cls) -> dict:
        """Directory-level metrics for /health/cache."""
        count = 0
        total = 0
        for name in cls._listdir():
            try:
                total += os.stat(os.path.join(CACHE_DIR, name)).st_size
                count += 1  # pragma: no cover — defensive / hard to exercise in unit tests
            except OSError:
                continue
        return {
            "name": "L2-disk",
            "dir": CACHE_DIR,
            "entries": count,
            "bytes": total,
            "bytes_budget": MAX_CACHE_BYTES,
            "ttl_minutes": config.CACHE_TTL_MINUTES,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _listdir() -> List[str]:
        try:
            return os.listdir(CACHE_DIR)
        except FileNotFoundError:
            return []
        except Exception:
            return []

    @staticmethod
    def _unlink(path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass


# The disk cache is bounded by a periodic sweep as well as opportunistically on write.
# That sweep used to be step 3 of the GC daemon inside domains/mutual_funds/sessions.py,
# so this shared cache was only trimmed if that domain happened to be loaded. It is
# shared infrastructure, so it registers itself.
janitor.register("shared.cache", MarketCache.sweep)
