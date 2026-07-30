"""
domains/mutual_funds/derived.py

Caching for derived portfolio artifacts - results computed *from* a portfolio rather
than fetched for it.

Why this exists
---------------
compute_period_comparison() is the most expensive function in the codebase: it
simulates the portfolio day by day over its whole history. It is called from five
places, and a single dashboard load triggers roughly eight invocations of it:

    /overview            1
    /benchmark-overlay   4   (the default query is "Nifty 50,S&P 500,Gold", plus
                              one for the default benchmark)
    /performance         1
    /drawdown            1   (runs the whole simulation only to read comp["portfolio"])
    /journey             1   (at days=9999)

Those eight are computing the *same thing* from the same inputs. On a single worker
with ~0.1 shared vCPU they run one after another. Caching the result collapses them
to one; single-flight collapses them even on a cold cache, because the frontend
fires all of those endpoints concurrently and the seven late arrivals wait for the
first rather than starting their own simulation.

Invalidation
------------
There is none, deliberately. The key is content-addressed: it is derived from a hash
of the actual input frames plus the portfolio value and the benchmark series
identity. If any input changes the key changes, so a stale entry is unreachable
rather than incorrect. That removes a whole class of bug - the previous approach
relied on remembering to call MarketCache.invalidate() from the right places, and
its empty-pattern default silently wiped the entire cache.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

from domains.mutual_funds.finance import compute_period_comparison
from shared.services.cache import DERIVED_CACHE, ttl_for

logger = logging.getLogger(__name__)

_TTL = ttl_for("performance_metrics")  # 15 min; the underlying NAV data is EOD anyway


def _frame_fingerprint(df: Optional[pd.DataFrame]) -> Optional[str]:
    """
    Content hash of a DataFrame, or None if it cannot be hashed safely.

    Uses pandas' vectorized row hasher: O(rows) in C, microseconds for a ledger of a
    few thousand rows, versus seconds for the simulation it guards. Returning None on
    failure means "cannot prove this is the same input", and callers then skip the
    cache rather than risk serving another portfolio's numbers.
    """
    if df is None:
        return "none"
    if df.empty:
        return "empty"

    try:
        digest = int(pd.util.hash_pandas_object(df, index=True).sum())
        return f"{len(df)}x{len(df.columns)}:{digest & 0xFFFFFFFFFFFF:x}"
    except Exception as e:
        logger.debug("[DERIVED] frame not hashable, bypassing cache: %s", e)
        return None


def _series_fingerprint(series: Optional[pd.Series]) -> Optional[str]:
    """
    Cheap identity for a benchmark series.

    Length plus both endpoints (dates and values) is enough to distinguish the
    series we actually see here - different indices differ in value, and the same
    index at a different horizon differs in length and start date. Avoids hashing a
    ~3700-point series on every request.
    """
    if series is None:
        return "none"
    if len(series) == 0:
        return "empty"

    try:
        return (
            f"{len(series)}:{series.index[0].value}:{series.index[-1].value}:"
            f"{float(series.iloc[0]):.6f}:{float(series.iloc[-1]):.6f}"
        )
    except Exception as e:
        logger.debug("[DERIVED] series not fingerprintable, bypassing cache: %s", e)
        return None


def cached_xirr_by_fy(df_t: pd.DataFrame, df_h: pd.DataFrame) -> Any:
    """
    compute_xirr_by_fy() with the same content-addressed cache.

    Worth caching even though it is one endpoint: the function is
    O(financial_years x funds x transactions) - it rebuilds FIFO lots per (FY x fund)
    and re-slices the full ledger per snapshot - and it was called directly, so every
    reload of the Insights tab paid the whole cost again.

    Two lines rather than an algorithmic rewrite, deliberately: the complexity is
    still there, but a revisit is now a dict lookup. Reducing the complexity means
    touching FIFO lot construction, which is the most numerically sensitive code in
    the repo and wants its own change with the equivalence tests in front of it.
    """
    from domains.mutual_funds.finance import compute_xirr_by_fy

    t_fp = _frame_fingerprint(df_t)
    h_fp = _frame_fingerprint(df_h)

    if t_fp is None or h_fp is None:
        return compute_xirr_by_fy(df_t, df_h)

    return DERIVED_CACHE.get_or_compute(
        f"xirr_by_fy|{t_fp}|{h_fp}",
        lambda: compute_xirr_by_fy(df_t, df_h),
        _TTL,
    )


def cached_period_comparison(
    df_t: pd.DataFrame,
    df_h: pd.DataFrame,
    total_value: float,
    bench_series: pd.Series,
    period_days: int,
) -> Dict[str, Any]:
    """
    compute_period_comparison() with a content-addressed cache and single-flight.

    Drop-in replacement: same arguments, same return value. Callers that pass
    filtered frames get their own cache entry automatically, because the fingerprint
    is taken from the frames actually passed rather than from the session.
    """
    t_fp = _frame_fingerprint(df_t)
    h_fp = _frame_fingerprint(df_h)
    b_fp = _series_fingerprint(bench_series)

    if t_fp is None or h_fp is None or b_fp is None:
        # Could not build a trustworthy key - compute directly rather than guess.
        return compute_period_comparison(df_t, df_h, total_value, bench_series, period_days)

    # total_value is part of the key rather than something we invalidate on: a live
    # NAV refresh changes it, which naturally yields a new entry.
    key = f"period_cmp|{t_fp}|{h_fp}|{total_value:.2f}|{b_fp}|{period_days}"

    return DERIVED_CACHE.get_or_compute(
        key,
        lambda: compute_period_comparison(df_t, df_h, total_value, bench_series, period_days),
        _TTL,
    )


def derived_cache_stats() -> Dict[str, Any]:
    """Hit-rate metrics for the derived tier."""
    return DERIVED_CACHE.stats()
