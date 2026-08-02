"""
domains/budget/derived.py - memoization for computed budget artifacts.

The budget domain shipped with no server-side cache at all. Every one of /overview,
/categories and /transactions independently decrypted, zlib-decompressed and JSON-parsed
*every session the user owns*, concatenated them, re-parsed the dates and merged
overlaps - and the dashboard fires all three on mount and again on every filter change.
One keystroke in the search box was three full decrypt-and-rebuild passes over the
user's entire financial history.

The engines added since (transfer pairing, recurring detection, anomalies, forecast,
reconciliation) are heavier still: pairing buckets every transaction, and recurring
detection groups and sorts per merchant.

This is the same arrangement equity and mutual funds already use - see
domains/equity/derived.py, which this deliberately mirrors.

Invalidation
------------
None, deliberately. Keys are content-addressed from a hash of the input frame, so a
changed input produces a changed key and a stale entry becomes unreachable rather than
wrong. Nothing has to remember to invalidate, which is what makes it safe to memoize
across a re-upload or a category edit.

A fingerprint that cannot be computed returns None, and a None key means "compute
directly". Guessing at a key is how one user's ledger gets served to another - see the
UnsafeCacheKey note in shared/services/cache.py.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pandas as pd

from shared.services.cache import DERIVED_CACHE, ttl_for

logger = logging.getLogger(__name__)

# Transactions change only by upload or edit, both of which change the fingerprint.
_TTL = ttl_for("holdings_detail")  # 15 min

# Bumped when the shape of a cached payload changes, so a deploy cannot serve the old
# shape to new frontend code out of a warm process.
_VERSION = "v1"


def frame_fingerprint(df: Optional[pd.DataFrame]) -> Optional[str]:
    """
    Content hash of a transaction frame, or None if it cannot be hashed safely.

    Order-sensitive, deliberately. `hash_pandas_object(...).sum()` - the form used by
    the equity and mutual-fund modules, and the obvious thing to write - is
    order-*independent*: reversing the rows moves each row hash to a different position
    but leaves the total identical, so two differently ordered frames collide on one
    cache entry.

    That is correct for those modules, whose dedup hash wants order independence
    because brokers do not guarantee export order. It is the wrong default here. The
    engines this cache serves happen to sort internally today, so nothing is currently
    broken by a collision - but "safe as long as no future engine reads the frame in
    order" is a trap, and weighting each row hash by its position costs nothing.
    """
    if df is None:
        return "none"
    if df.empty:
        return "empty"
    try:
        import numpy as np

        rows = pd.util.hash_pandas_object(df, index=True).to_numpy(dtype="uint64", copy=False)
        # uint64 multiply and sum wrap silently, which is exactly what is wanted from a
        # mixing function.
        positions = np.arange(1, rows.size + 1, dtype="uint64")
        digest = int((rows * positions).sum())
        return f"{len(df)}x{len(df.columns)}:{digest & 0xFFFFFFFFFFFF:x}"
    except Exception as e:
        logger.debug("[BUDGET DERIVED] frame not hashable, bypassing cache: %s", e)
        return None


def _memo(key: Optional[str], compute: Callable[[], Any]) -> Any:
    if key is None:
        return compute()
    return DERIVED_CACHE.get_or_compute(key, compute, _TTL)


def _keyed(name: str, fingerprint: Optional[str], *parts: Any) -> Optional[str]:
    if fingerprint is None:
        return None
    suffix = ":".join(str(p) for p in parts)
    return f"budget_{name}_{_VERSION}:{fingerprint}" + (f":{suffix}" if suffix else "")


def transfers(df: pd.DataFrame, flags_signature: str, compute: Callable[[], Any]) -> Any:
    """
    Memoized transfer pairing.

    `flags_signature` is part of the key because user overrides change the answer
    without changing the frame.
    """
    return _memo(_keyed("transfers", frame_fingerprint(df), flags_signature), compute)


def recurring(df: pd.DataFrame, compute: Callable[[], Any]) -> Any:
    return _memo(_keyed("recurring", frame_fingerprint(df)), compute)


def anomalies(df: pd.DataFrame, compute: Callable[[], Any]) -> Any:
    return _memo(_keyed("anomalies", frame_fingerprint(df)), compute)


def reconciliation(df: pd.DataFrame, compute: Callable[[], Any]) -> Any:
    return _memo(_keyed("reconcile", frame_fingerprint(df)), compute)


def sankey(df: pd.DataFrame, compute: Callable[[], Any]) -> Any:
    return _memo(_keyed("sankey", frame_fingerprint(df)), compute)


def account_summary(df: pd.DataFrame, meta_signature: str, compute: Callable[[], Any]) -> Any:
    """Memoized per-account rollup. Metadata edits change the answer, so they are keyed."""
    return _memo(_keyed("accounts", frame_fingerprint(df), meta_signature), compute)


def overview(df: pd.DataFrame, filter_signature: str, compute: Callable[[], Any]) -> Any:
    """
    Memoized dashboard overview.

    The filter signature must capture *every* argument that changes the result. It is
    built by the caller with a stable ordering rather than from a dict, because two
    dicts with the same contents in a different insertion order would otherwise produce
    two keys for one answer - a miss, not a correctness problem, but the whole point is
    the hit.
    """
    return _memo(_keyed("overview", frame_fingerprint(df), filter_signature), compute)


def stats() -> dict:
    """Cache counters, for the diagnostics endpoint."""
    return DERIVED_CACHE.stats()
