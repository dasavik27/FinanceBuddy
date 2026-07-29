"""
core/sessions.py

In-Memory State Management & Portfolio Concurrency Engine
=========================================================
Manages thread-safe session storage for multi-tab financial state, with automatic
background garbage collection and DataFrame-to-record JSON serialization.

Memory model
------------
A session holds three live DataFrames (holdings, the full transaction ledger, SIPs).
The ledger is the large one and cannot be trimmed: XIRR and FIFO cost basis both
need every transaction. So instead of shrinking a session, we bound how many are
resident at once (MAX_RESIDENT_SESSIONS) and let SQLite be the overflow. Eviction is
cheap because get_session() already rehydrates from disk on a miss.

Retention note
--------------
Sessions ARE written to disk (SQLite, via shared/storage.py) for dedup, history and
rehydration. An earlier version of this docstring claimed "zero disk retention...
institutional privacy compliance", which was not true and is a claim worth being
accurate about. What is true: the uploaded PDF itself is never retained (the parser
deletes its temp file), and disk rows are purged after 24 hours by the sweeper below.
"""

import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException

from domains.mutual_funds.models import Portfolio
from shared import storage
import logging
logger = logging.getLogger(__name__)


# Session store, bounded and LRU-ordered (most recently used last).
#
# Previously an unbounded plain dict, mutated from both request threads and the GC
# daemon without a lock. On a 512 MB box its steady-state size was "however many
# uploads happened in the last 4 hours", which is a slow memory leak with extra
# steps.
_SESSIONS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_SESSIONS_LOCK = threading.RLock()

# Session Time-To-Live (4 hours) prevents premature timeout during deep reviews.
SESSION_TTL_HOURS = 4

# How many portfolios may be resident simultaneously. Small on purpose: the working
# set for a single user is 1, and anything evicted is rebuilt from SQLite on demand.
MAX_RESIDENT_SESSIONS = int(os.getenv("FINANCEBUDDY_MAX_RESIDENT_SESSIONS", "3"))


# ---------------------------------------------------------------------------
# dtype compaction
# ---------------------------------------------------------------------------

# Columns whose values repeat heavily across rows. A fund name stored as `object` is
# a separate ~90-byte Python string per row; as `category` it is one small integer
# per row plus a single copy of each distinct value. On a multi-year ledger this is
# the dominant memory win.
_CATEGORICAL_COLUMNS = ("Fund", "AMC", "Category", "Type", "Cap Type", "Plan", "ISIN")

# Deliberately NOT downcasting float64 -> float32 on monetary columns. float32 holds
# only ~7 significant digits, and an amount like 10000000.50 needs 10 - so the
# "obvious" memory saving would silently corrupt cost basis and XIRR inputs. The
# category conversion above gets the bulk of the saving without touching precision.


def _compact_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert repeated string columns to `category` in place. Returns the frame."""
    if df is None or df.empty:
        return df

    for col in _CATEGORICAL_COLUMNS:
        if col not in df.columns:
            continue
        if df[col].dtype.name == "category":
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        try:
            # Only worth it when values actually repeat, and only on frames big
            # enough for the saving to exceed the category dictionary's own overhead.
            if len(df) >= 16 and df[col].nunique(dropna=False) <= len(df) * 0.5:
                df[col] = df[col].astype("category")
        except Exception:
            pass  # unhashable/mixed content - leave as-is
    return df


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def _remember(session_id: str, portfolio: Portfolio) -> None:
    """Insert a session as most-recently-used and evict beyond the budget."""
    now = datetime.now()
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = {
            "portfolio": portfolio,
            "created_at": now,
            "last_accessed": now,
        }
        _SESSIONS.move_to_end(session_id)

        while len(_SESSIONS) > MAX_RESIDENT_SESSIONS:
            evicted_id, _ = _SESSIONS.popitem(last=False)  # least recently used
            logger.info(
                "[SESSION EVICT] %s dropped from memory (resident cap %d); "
                "will rehydrate from disk if requested again",
                evicted_id, MAX_RESIDENT_SESSIONS,
            )


def create_session(df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, pan_id: str = None, upload_type: str = 'mutual_funds') -> str:
    """
    Initializes a new portfolio session. Retroactively classifies holdings via the
    CategorizationEngine to ensure parity with AMFI & Morningstar categorization.
    """
    # Deduplication check: if this ledger exists on disk, skip processing
    duplicate_id = storage.check_duplicate_upload(df_t)
    if duplicate_id:
        return duplicate_id

    session_id = str(uuid.uuid4())

    # NOTE (Fix C-2): The CAS parser already classifies categories using
    # raw_cat, raw_type, AND fund name via CategorizationEngine.detect_category().
    # Re-running detect_category() here with ONLY the fund name would discard
    # the richer CAS metadata (e.g., "Banking & PSU" debt → misclassified as Thematic).
    # We only re-classify funds with empty/missing categories.
    if not df_h.empty and "Category" in df_h.columns:
        from domains.mutual_funds.logic import CategorizationEngine as CE
        mask = df_h["Category"].isna() | (df_h["Category"].astype(str).str.strip() == "")
        if mask.any():
            df_h.loc[mask, "Category"] = df_h.loc[mask, "Fund"].apply(
                lambda fn: CE.detect_category(str(fn))
            )

    # Persist BEFORE compacting: to_sql writes categoricals as their codes in some
    # pandas/SQLite combinations, and the round-trip must preserve the label.
    final_session_id = storage.save_session(session_id, df_h, df_t, df_s, is_partial, pan_id, upload_type)

    for frame in (df_h, df_t, df_s):
        _compact_dtypes(frame)

    portfolio = Portfolio(df_h, df_t, df_s, is_partial)
    portfolio.update_live_navs()

    _remember(session_id, portfolio)
    return session_id


# ── Automated Session Garbage Collector ───────────────────────────────────

def _session_purge_worker():
    """
    Daemon thread executing periodic background purges of abandoned sessions.
    Evaluates expiration against last active API interaction heartbeat.
    Also sweeps SQLite for disk-level retention limit (24 hours).
    """
    while True:
        try:
            now = datetime.now()

            # 1. In-Memory Purge (4 hours idle)
            with _SESSIONS_LOCK:
                expired = [
                    sid for sid, data in _SESSIONS.items()
                    if (now - data.get("last_accessed", data["created_at"])).total_seconds()
                    > (SESSION_TTL_HOURS * 3600)
                ]
                for sid in expired:
                    _SESSIONS.pop(sid, None)

            # 2. Disk-Level Purge (24 hours) for CAS
            from shared.storage import DB_PATH, delete_session
            import sqlite3
            if storage.os.path.exists(DB_PATH):
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.execute("SELECT session_id FROM sessions WHERE created_at < datetime('now', '-24 hours')")
                    for row in cursor.fetchall():
                        delete_session(row[0])

            # 3. Trim the disk cache alongside sessions, so the .cache directory
            #    cannot outgrow its budget on a long-lived instance.
            try:
                from shared.cache import MarketCache
                MarketCache.sweep()
            except Exception as e:
                logger.error(f"[GC CACHE SWEEP ERROR] {e}")

        except Exception as e:
            logger.error(f"[GC ERROR] {e}")
        time.sleep(600)  # GC sweep execution interval: 10 minutes

# Initialize background garbage collection daemon
threading.Thread(target=_session_purge_worker, daemon=True).start()


def get_session(session_id: str) -> Portfolio:
    """
    Retrieves the active portfolio session and updates the activity heartbeat.
    Raises HTTP 404 if the session has expired or does not exist.
    """
    with _SESSIONS_LOCK:
        entry = _SESSIONS.get(session_id)
        if entry is not None:
            entry["last_accessed"] = datetime.now()
            _SESSIONS.move_to_end(session_id)
            return entry["portfolio"]

    # Miss: reconstruct from disk. Done outside the lock because it does I/O.
    disk_data = storage.load_session(session_id)
    if disk_data is None:
        raise HTTPException(status_code=404, detail="Session expired or not found. Please re-upload your CAS.")

    df_h, df_t, df_s, is_partial = disk_data
    for frame in (df_h, df_t, df_s):
        _compact_dtypes(frame)

    portfolio = Portfolio(df_h, df_t, df_s, is_partial)

    # Refresh live NAVs on rehydration. This used to be skipped "to save API calls",
    # which left disk-restored portfolios valued at CAS-era NAVs - a correctness
    # problem that memory-bounded eviction would otherwise make routine. It is now
    # affordable: the AMFI file is a single cached bundle shared by every consumer,
    # so this is normally a dictionary lookup rather than a download.
    try:
        portfolio.update_live_navs()
    except Exception as e:
        logger.warning(f"[SESSION REHYDRATE] live NAV refresh failed for {session_id}: {e}")

    _remember(session_id, portfolio)
    return portfolio


def session_stats() -> Dict[str, Any]:
    """Resident-session metrics, for health reporting."""
    with _SESSIONS_LOCK:
        return {
            "resident": len(_SESSIONS),
            "resident_cap": MAX_RESIDENT_SESSIONS,
            "ttl_hours": SESSION_TTL_HOURS,
        }


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def df_to_records(df: pd.DataFrame) -> list:
    """
    DataFrame serializer. Converts timestamps to ISO date strings and sanitizes
    NaN / Inf into JSON-compliant None literals prior to API delivery.

    Vectorized per column. The previous implementation ran a Python lambda over
    every cell (`df.apply` on each column in turn), i.e. rows x columns interpreter
    calls on every /holdings and /transactions request; the work below happens in
    pandas' C layer instead.
    """
    if df is None or df.empty:
        return []

    df2 = df.copy()

    # Datetime columns → ISO date strings. NaT becomes null and is handled below.
    for col in df2.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df2[col] = df2[col].dt.strftime("%Y-%m-%d")

    # Fold infinities into NaN first, so a single missingness mask covers both.
    numeric_cols = df2.select_dtypes(include=["number"]).columns
    if len(numeric_cols):
        df2[numeric_cols] = df2[numeric_cols].replace([np.inf, -np.inf], np.nan)

    # Compute the mask on the typed frame (vectorized), then widen to object in one
    # pass so None actually survives. Substituting None column-by-column does not
    # work: assigning an object block back into a float column re-coerces None to
    # NaN, and NaN is not valid JSON.
    mask = df2.notna()
    return df2.astype(object).where(mask, None).to_dict(orient="records")
