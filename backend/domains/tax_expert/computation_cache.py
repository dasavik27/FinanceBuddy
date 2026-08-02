"""
domains/tax_expert/computation_cache.py

Memoization layer over compute_tax().

Why this exists
---------------
compute_tax() is ~590 lines of pure arithmetic over a session's AIS data, and it
was re-run from scratch on every request. A single dashboard load ran it three
times over identical inputs:

  GET /tax/summary          -> 1 run
  GET /tax/compare-regimes  -> 2 runs (old + new, in one handler)

On ~0.1 shared vCPU that is the dominant per-request cost. compute_tax is a pure
function of (ais_data, regime, overrides), so the results are cacheable.

Keying
------
Rather than hashing the (potentially large) ais_data and overrides dicts on every
request, the key uses the session's monotonic `_version` counter, which
tax_sessions._bump() increments on every mutation. Key = (session_id, version,
regime). That makes lookups O(1) regardless of session size, and any write to the
session automatically invalidates every derived entry.

IMPORTANT: get_computation() returns the *cached* dict. Callers that add fields
(e.g. attaching "overrides" to the response) must shallow-copy it first, or they
will mutate the cache. `summary_response()` does this for you.
"""

import logging
from collections import OrderedDict

from domains.tax_expert.tax_engine import compute_tax
from domains.tax_expert.tax_sessions import get_session_version

logger = logging.getLogger(__name__)

# Derived from the session store's own cap rather than picked independently.
#
# This used to be a flat 24 while the session store held 8, so the cache could pin three
# times as many AIS documents as the store was allowed to keep - each entry references
# the session's detail lists by reference, not by copy. An entry therefore kept an
# evicted session's ~2 MB payload alive, and the cache quietly defeated the bound the
# store exists to enforce. Two regimes (old/new) per resident session is the real working
# set; anything beyond that is holding memory for a session that is no longer resident.
#
# Eviction from the store now also invalidates here (see tax_sessions._evict_locked), so
# this cap is a backstop rather than the primary mechanism.
try:
    from domains.tax_expert.tax_sessions import MAX_SESSIONS as _MAX_RESIDENT_SESSIONS
except Exception:  # pragma: no cover - import-order safety only
    _MAX_RESIDENT_SESSIONS = 8

_REGIMES = 2
MAX_ENTRIES = _MAX_RESIDENT_SESSIONS * _REGIMES

_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_stats = {"hits": 0, "misses": 0}


def get_computation(session_id: str, session: dict, regime: str = "new") -> dict:
    """Return the tax computation for a session+regime, memoized.

    The returned dict is shared — treat it as read-only and copy before mutating.
    """
    key = (session_id, get_session_version(session_id), regime)

    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        _stats["hits"] += 1
        return cached

    _stats["misses"] += 1
    result = compute_tax(
        session["ais_data"],
        regime=regime,
        overrides=session.get("overrides", {}),
    )

    _cache[key] = result
    _cache.move_to_end(key)
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)

    return result


def invalidate_session(session_id: str):
    """Drop every cached regime for one session.

    Not needed for normal mutations (the version counter handles those), but used
    on delete so entries for a dead session do not linger until LRU eviction.
    """
    for key in [k for k in _cache if k[0] == session_id]:
        del _cache[key]


def clear_all():
    """Drop every cached computation."""
    _cache.clear()


def cache_stats() -> dict:
    """Hit/miss counters, for diagnosing cache effectiveness in production."""
    total = _stats["hits"] + _stats["misses"]
    return {
        **_stats,
        "entries": len(_cache),
        "max_entries": MAX_ENTRIES,
        "hit_rate": round(_stats["hits"] / total, 3) if total else 0.0,
    }
