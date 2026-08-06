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
resident at once (MAX_RESIDENT_SESSIONS) and let Postgres be the overflow. Eviction is
cheap because get_session() already rehydrates from disk on a miss.

Retention note
--------------
Sessions ARE persisted (Postgres, via shared/storage.py) for dedup, history and
rehydration. An earlier version of this docstring claimed "zero disk retention...
institutional privacy compliance", which was not true and is a claim worth being
accurate about. What is true: the uploaded PDF itself is never retained (the parser
deletes its temp file). Stored rows are NOT swept on a timer - purge_expired() below
bounds memory only. Deletion is the user's: DELETE /accounts/me or DELETE /history/{id}.
"""

import os
import threading
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException

from domains.mutual_funds.models import Portfolio
from shared import identity, janitor, session_stores, storage
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
# set for a single user is 1, and anything evicted is rebuilt from the database.
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
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        try:
            # Only worth it when values actually repeat, and only on frames big
            # enough for the saving to exceed the category dictionary's own overhead.
            if len(df) >= 16 and df[col].nunique(dropna=False) <= len(df) * 0.5:
                df[col] = df[col].astype("category")
        except Exception:  # pragma: no cover — defensive / hard to exercise in unit tests
            pass  # unhashable/mixed content - leave as-is  # pragma: no cover — defensive / hard to exercise in unit tests
    return df


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def _remember(session_id: str, portfolio: Portfolio, owner: Optional[str] = None) -> None:
    """
    Insert a session as most-recently-used and evict beyond the budget.

    The owner is stored alongside the portfolio so ownership can be checked from
    memory. That matters for two reasons: a resident hit must not depend on the database
    being reachable, and a session whose registry row has been deleted (by
    /history/{sid} DELETE or an account purge) must not become readable by anyone
    just because the registry can no longer say who owns it.
    """
    now = datetime.now()
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = {
            "portfolio": portfolio,
            "owner": owner,
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


def create_session(df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, statement_period: str = "", upload_type: str = 'mutual_funds') -> str:
    """
    Initializes a new portfolio session. Retroactively classifies holdings via the
    CategorizationEngine to ensure parity with AMFI & Morningstar categorization.
    """
    # The owner is the authenticated caller, never a value the request supplied.
    user_id = identity.current_user_id()

    # Deduplication check: if this owner already uploaded this exact ledger, reuse
    # the existing session. The hash is computed once here and threaded into
    # save_session, both because the dedup lookup and the registry row must agree
    # and because computing it twice ran a row-wise `df.apply` over the whole ledger
    # twice per upload.
    ledger_hash = storage.compute_ledger_hash(df_t, user_id)
    duplicate_id = storage.check_duplicate_upload(ledger_hash, user_id)
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
    # pandas versions, and the round-trip must preserve the label.
    final_session_id = storage.save_session(
        session_id, df_h, df_t, df_s, is_partial, statement_period, user_id, upload_type,
        ledger_hash=ledger_hash,
    )
    # save_session returns a different id if it adopted a concurrent duplicate.
    if final_session_id != session_id:
        return final_session_id

    for frame in (df_h, df_t, df_s):
        _compact_dtypes(frame)

    portfolio = Portfolio(df_h, df_t, df_s, is_partial)
    portfolio.update_live_navs()

    _remember(session_id, portfolio, owner=user_id)
    return session_id


# ── Automated Session Garbage Collector ───────────────────────────────────

def purge_expired() -> int:
    """
    Drop resident sessions idle beyond the TTL. Registered with the shared janitor.

    Memory only: stored rows are the user's data and are never swept on a timer.
    That used to happen here - every session older than 24 hours was deleted - back
    when the filesystem was ephemeral and keeping rows past a deploy was pointless.
    Storage is durable now, so a timer that deletes a user's parsed statements is data
    loss, not housekeeping. Retention belongs to the user: DELETE /accounts/me removes
    everything, DELETE /history/{id} removes one statement. Eviction here is a cache
    bound, and an evicted session is rehydrated from the database on next access.
    """
    now = datetime.now()
    with _SESSIONS_LOCK:
        expired = [
            sid for sid, data in _SESSIONS.items()
            if (now - data.get("last_accessed", data["created_at"])).total_seconds()
            > (SESSION_TTL_HOURS * 3600)
        ]
        for sid in expired:
            _SESSIONS.pop(sid, None)
    return len(expired)


# This module used to own the whole application's GC thread: it started a daemon at
# import and swept tax-expert rows and equity portfolios as well as its own sessions.
# That made two unrelated domains silently depend on this one being loaded. Each domain
# now registers its own sweep and shared/janitor.py runs them; main.py starts the
# thread.
janitor.register("mutual_funds.sessions", purge_expired)


_NOT_FOUND_DETAIL = "Session expired or not found. Please re-upload your CAS."


def _deny(session_id: str, owner: Optional[str]) -> "HTTPException":
    """
    Build the denial. 404 rather than 403 on purpose: a 403 confirms the session
    exists, which is exactly the signal an id-guessing caller is looking for.
    """
    caller = identity.current_user_id()
    logger.warning(
        "[AUTHZ] caller=%s denied access to session %s owned=%s (same PAN in different "
        "case is a bug, not an attack - both mask identically here)",
        identity.mask_pan(caller), session_id, identity.mask_pan(owner),
    )
    return HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


def get_session(session_id: str) -> Portfolio:
    """
    Retrieves the active portfolio session and updates the activity heartbeat.
    Raises HTTP 404 if the session has expired, does not exist, or belongs to
    somebody else.

    Ownership is resolved from whichever source is authoritative for the path taken:

    - **Resident hit** - from the entry itself. Not from the database, because a resident
      session must stay usable when the database is unreachable, and because a
      session whose registry row was deleted must not become readable by everyone
      merely because the registry can no longer name its owner.
    - **Disk miss** - from the registry, and the session must both exist and be
      owned by the caller. A lookup that *fails* (rather than returning "absent")
      denies with 503: an authorization check that cannot run must not default to
      allowing access.
    """
    with _SESSIONS_LOCK:
        entry = _SESSIONS.get(session_id)
        if entry is not None:
            if not identity.owns_record(entry.get("owner")):
                raise _deny(session_id, entry.get("owner"))
            entry["last_accessed"] = datetime.now()
            _SESSIONS.move_to_end(session_id)
            return entry["portfolio"]

    # Miss: authorize against the registry, then reconstruct from disk.
    try:
        exists, owner = storage.get_session_owner(session_id)
    except storage.OwnerLookupFailed:
        raise HTTPException(
            status_code=503,
            detail="Could not verify access to this session. Please retry.",
        )

    if not exists:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    if not identity.owns_record(owner):
        raise _deny(session_id, owner)

    disk_data = storage.load_session(session_id)
    if disk_data is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)

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

    _remember(session_id, portfolio, owner=owner)
    return portfolio


def forget(session_id: str) -> bool:
    """Drop one resident session. Returns whether it was present."""
    with _SESSIONS_LOCK:
        return _SESSIONS.pop(session_id, None) is not None


def evict_for_user(user_id: str) -> int:
    """
    Drop a user's resident sessions. Returns how many were dropped.

    Required by the purge path: deleting the rows left the portfolios sitting in
    memory, so data the user asked to have permanently deleted stayed readable for up
    to the session TTL by anyone holding the id - and, with the registry row gone, the
    registry could no longer say who owned it.

    Compared exactly, with no case folding. The owner used to be a PAN, which is
    conventionally upper-case, so this upper-cased before comparing; it is now a
    lower-case uuid, and that leftover `.upper()` made the comparison never match.
    Eviction silently became a no-op that still reported success - so a purge left
    every portfolio resident and readable, which is precisely the bug this function
    exists to prevent.
    """
    target = str(user_id or "")
    with _SESSIONS_LOCK:
        doomed = [
            sid for sid, entry in _SESSIONS.items()
            if str(entry.get("owner") or "") == target
        ]
        for sid in doomed:
            _SESSIONS.pop(sid, None)
    if doomed:
        logger.info("[SESSION] evicted %d resident session(s) for %s", len(doomed), user_id)
    return len(doomed)


def clear_all() -> int:
    """
    Drop every resident session. Returns how many were dropped.

    Exists so callers do not have to touch `_SESSIONS` directly - doing that skips
    _SESSIONS_LOCK and races the GC daemon.
    """
    with _SESSIONS_LOCK:
        count = len(_SESSIONS)
        _SESSIONS.clear()
    return count


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


# Logout, account purge and history-delete used to name this module explicitly from
# three shared routers. They iterate the registry instead; see shared/session_stores.py.
# Registered at the foot of the module because it references the functions above.
session_stores.register(session_stores.SessionStore(
    name="mutual_funds",
    evict_user=evict_for_user,
    forget_session=forget,
    clear_all=clear_all,
))
