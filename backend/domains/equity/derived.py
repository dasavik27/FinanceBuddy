"""
domains/equity/derived.py

Caching for derived equity artifacts - results computed *from* a portfolio rather than
fetched for it. The equity analogue of domains/mutual_funds/derived.py.

Why this exists
---------------
Equity had no server-side compute cache at all: every tab recomputed from scratch on
every request, where the mutual-fund side collapses its duplicate work. Two payloads
are worth memoizing.

**Sector allocation** is computed twice per dashboard load, by two different tabs from
the same inputs - Overview renders the top six sectors, and the Sector tab renders all
of them plus industries. Both call get_sector_allocation(); it is two groupbys over the
holdings frame, and the second one is pure waste.

**Realised capital gains** is the expensive one. FIFO lot matching walks the entire
tradebook per symbol, and a multi-year tradebook is the largest frame in the domain. It
is recomputed on every P&L tab render.

Invalidation
------------
None, deliberately - the same approach as the MF module. Keys are content-addressed
from a hash of the actual input frames, so if an input changes the key changes and a
stale entry becomes unreachable rather than wrong. Nothing has to remember to invalidate.

One deliberate asymmetry: the capital-gains key is derived from the **tradebook only**.
Realised gains are a function of executed trades, not of today's price, so a live-price
sync must not invalidate them. Keying on the holdings frame as well would have thrown
the entry away every five minutes for no reason.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pandas as pd

from shared.services.cache import DERIVED_CACHE, ttl_for

logger = logging.getLogger(__name__)

# The inputs are broker exports and executed trades; neither changes within a session
# except by re-upload, which changes the fingerprint anyway.
_TTL = ttl_for("holdings_detail")  # 15 min


def _frame_fingerprint(df: Optional[pd.DataFrame]) -> Optional[str]:
    """
    Content hash of a DataFrame, or None if it cannot be hashed safely.

    None means "cannot prove this is the same input", and callers then bypass the cache
    rather than risk serving another portfolio's numbers.
    """
    if df is None:
        return "none"
    if df.empty:
        return "empty"

    try:
        digest = int(pd.util.hash_pandas_object(df, index=True).sum())
        return f"{len(df)}x{len(df.columns)}:{digest & 0xFFFFFFFFFFFF:x}"
    except Exception as e:
        logger.debug("[EQ DERIVED] frame not hashable, bypassing cache: %s", e)
        return None


def _memo(key: Optional[str], compute: Callable[[], Any]) -> Any:
    """
    Serve `key` from the derived cache, computing once across concurrent callers.

    A None key means the inputs could not be fingerprinted; compute directly rather
    than guess at a cache key.
    """
    if key is None:
        return compute()
    return DERIVED_CACHE.get_or_compute(key, compute, _TTL)


def sector_allocation(
    df_holdings: pd.DataFrame, total_value: float, compute: Callable[[], Any]
) -> Any:
    """
    Memoized sector/industry breakdown.

    total_value is part of the key because the percentages are computed against it, and
    it moves with a price refresh even when the holdings rows do not.
    """
    fp = _frame_fingerprint(df_holdings)
    key = None if fp is None else f"eq_alloc_v1:{fp}:{round(float(total_value or 0.0), 2)}"
    return _memo(key, compute)


def capital_gains(df_trades: pd.DataFrame, compute: Callable[[], Any]) -> Any:
    """
    Memoized FIFO capital-gains computation.

    Keyed on the tradebook alone - see the note in the module docstring on why the
    holdings frame is deliberately excluded.
    """
    fp = _frame_fingerprint(df_trades)
    key = None if fp is None else f"eq_gains_v1:{fp}"
    return _memo(key, compute)


def insights(
    df_holdings: pd.DataFrame, total_value: float, compute: Callable[[], Any]
) -> Any:
    """Memoized insights payload (top movers, concentration, harvest candidates)."""
    fp = _frame_fingerprint(df_holdings)
    key = None if fp is None else f"eq_insights_v1:{fp}:{round(float(total_value or 0.0), 2)}"
    return _memo(key, compute)
