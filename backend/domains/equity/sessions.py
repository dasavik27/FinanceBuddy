"""
domains/equity/sessions.py

Session store for equity portfolios: encrypt/compress the payload to Postgres and
keep a bounded LRU of hot portfolios in process.

This mirrors domains/mutual_funds/sessions.py, and the important half of that
mirroring is authorization. Ownership in this application is enforced at the data
access boundary rather than per route (see shared/identity.py) - the argument being
that a check inside get_session() cannot be forgotten "because there is no other way
to reach a portfolio". This module used to be that other way: it looked the session
up by primary key and returned it, so any caller holding an id - including an
unauthenticated one - could read somebody else's holdings. Both paths now authorize,
and there is a test for each.
"""

import logging
import os
import threading
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException

from domains.equity.models import EquityPortfolio
from shared import identity, janitor, session_stores, storage

logger = logging.getLogger(__name__)


# Resident portfolios, LRU-ordered (most recently used last). Each entry carries its
# owner so a cache hit can be authorized without a database round trip - and so a
# session whose registry row has been deleted does not become readable by everyone
# merely because the registry can no longer name its owner.
_SESSIONS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_SESSIONS_LOCK = threading.RLock()

# Matches the MF budget. Was 20 here, bounded by entry count, which on a 512 MB box
# is a weak bound: an EquityPortfolio holds both a holdings frame and a tradebook,
# and 20 multi-year tradebooks have no meaningful ceiling. The working set for one
# user is 1, and anything evicted is rebuilt from Postgres.
MAX_RESIDENT_SESSIONS = int(os.getenv("FINANCEBUDDY_MAX_RESIDENT_EQUITY_SESSIONS", "3"))

# Idle timeout for resident portfolios. Memory only - stored rows are the user's data
# and are never swept on a timer. Swept by the GC daemon in mutual_funds/sessions.py
# via purge_expired(), and also enforced lazily on read so an expired entry is never
# served even if the daemon is not running (e.g. under test).
SESSION_TTL_HOURS = 4

_NOT_FOUND_DETAIL = "Session expired or not found. Please re-upload your holdings."


# ---------------------------------------------------------------------------
# dtype compaction
# ---------------------------------------------------------------------------

# Equity columns whose values repeat across rows. `symbol` is deliberately excluded:
# it is near-unique per row, so a category dictionary would cost more than the object
# column it replaces. Monetary columns are left as float64 - float32 holds only ~7
# significant digits, which is not enough for a cost basis.
_CATEGORICAL_COLUMNS = ("sector", "industry", "exchange", "broker", "type")


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
            # Only worth it when values actually repeat, and only on frames big enough
            # for the saving to exceed the category dictionary's own overhead.
            if len(df) >= 16 and df[col].nunique(dropna=False) <= len(df) * 0.5:
                df[col] = df[col].astype("category")
        except Exception:
            pass  # unhashable/mixed content - leave as-is
    return df


# ---------------------------------------------------------------------------
# Resident store
# ---------------------------------------------------------------------------

def _remember(session_id: str, portfolio: EquityPortfolio, owner: Optional[str] = None) -> None:
    """Insert as most-recently-used and evict beyond the budget."""
    now = datetime.now()
    with _SESSIONS_LOCK:
        _SESSIONS[session_id] = {
            "portfolio": portfolio,
            "owner": owner,
            "created_at": now,
            "last_accessed": now,
        }
        _SESSIONS.move_to_end(session_id)

        # `while`, not `if`: a lowered cap has to converge, not shed one entry.
        while len(_SESSIONS) > MAX_RESIDENT_SESSIONS:
            evicted_id, _ = _SESSIONS.popitem(last=False)  # least recently used
            logger.info(
                "[EQUITY SESSION EVICT] %s dropped from memory (resident cap %d); "
                "will rehydrate from Postgres if requested again",
                evicted_id, MAX_RESIDENT_SESSIONS,
            )


def _deny(session_id: str, owner: Optional[str]) -> HTTPException:
    """
    Build the denial. 404 rather than 403 on purpose: a 403 confirms the session
    exists, which is exactly the signal an id-guessing caller is looking for.
    """
    caller = identity.current_user_id()
    logger.warning(
        "[AUTHZ] caller=%s denied access to equity session %s owned=%s",
        identity.mask_pan(caller), session_id, identity.mask_pan(owner),
    )
    return HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


def _expired(entry: dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    last = entry.get("last_accessed") or entry.get("created_at")
    if last is None:
        return False
    return (now - last).total_seconds() > SESSION_TTL_HOURS * 3600


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def _equity_ledger_hash(
    df_holdings: pd.DataFrame, df_trades: pd.DataFrame, user_id: Optional[str]
) -> str:
    """
    Dedup fingerprint for an equity upload, over **both** frames.

    storage.compute_ledger_hash cannot be used directly here. It hashes transactions and
    only falls back to holdings when the transaction frame is empty - which is right for
    a CAS, where the ledger *is* the data. For equity it is wrong in a way that quietly
    breaks the product: a tradebook changes only when you trade, while holdings change
    with every price move. Hashing trades alone means a user who re-syncs daily with the
    same tradebook dedups onto their first upload forever and never sees current
    holdings.

    So both frames go in. Two uploads dedup only if the holdings *and* the trades match,
    which is the condition under which reusing the session is actually correct.
    """
    import hashlib

    def fp(df: pd.DataFrame, label: str) -> str:
        if df is None or df.empty:
            return f"{label}:empty"

        # Columns are sorted (cheap, canonical) but rows are NOT. Summing per-row hashes
        # is order-independent by construction, which is what we need - brokers do not
        # guarantee row order between exports - and it avoids sort_values(), which raises
        # on a column holding unorderable values and costs O(n log n) for nothing.
        cols = sorted(df.columns.tolist())
        subset = df[cols]
        try:
            digest = int(pd.util.hash_pandas_object(subset, index=False).sum())
        except Exception:
            # Unhashable cell content (e.g. a dict). Fall back to a sorted digest of
            # per-row text: still order-independent, still deterministic. Deterministic
            # matters more than elegance here - a random value would defeat dedup
            # entirely, and a constant one would collide across different uploads.
            rows = sorted(
                hashlib.sha256("\x1f".join(map(repr, row)).encode("utf-8")).hexdigest()
                for row in subset.itertuples(index=False, name=None)
            )
            digest = int(hashlib.sha256("|".join(rows).encode("utf-8")).hexdigest()[:16], 16)
        return f"{label}:{len(subset)}x{len(cols)}:{digest & 0xFFFFFFFFFFFFFFFF:x}"

    # The owner is part of the hash so an identical portfolio under two accounts cannot
    # resolve to the other user's session. check_duplicate_upload also filters on
    # user_id, so this is defence in depth rather than the only guard.
    material = f"equity|{user_id or ''}|{fp(df_holdings, 'h')}|{fp(df_trades, 't')}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def create_session(
    df_holdings: pd.DataFrame,
    df_trades: pd.DataFrame,
    source: str = "csv",
    kite_access_token: str | None = None,
    upload_type: str = "equity",
) -> str:
    """
    Persist an equity portfolio to Postgres and cache it in process.

    Returns the session_id - which is not necessarily the one generated here. If this
    owner already uploaded this exact ledger, the existing session is reused, and if a
    concurrent duplicate won the insert, save_session() reports the id that landed.
    Returning our own uuid regardless (as this used to) hands back an id with no
    registry row: it works from cache until eviction and then 404s a portfolio the
    user just uploaded.
    """
    from shared import crypto  # noqa: F401  (ensures the key is configured before we write)

    user_id = identity.current_user_id()

    portfolio = EquityPortfolio(
        df_holdings, df_trades, source=source, kite_access_token=kite_access_token
    )
    # Prices right after creation. Never fatal: a provider outage must not fail an
    # upload the user has already paid the parse cost for.
    try:
        portfolio.update_live_prices()
    except Exception as e:
        logger.warning("[EQUITY SESSION] live price refresh failed on create: %s", e)

    df_trades = df_trades if df_trades is not None else pd.DataFrame()

    ledger_hash = _equity_ledger_hash(portfolio.df_holdings, df_trades, user_id)
    duplicate_id = storage.check_duplicate_upload(ledger_hash, user_id)
    if duplicate_id:
        _remember(duplicate_id, portfolio, owner=user_id)
        return duplicate_id

    # Adapt equity holdings columns to the storage layer's expected schema. The
    # storage layer reads "Market Value" and "Invested" for its metrics extraction;
    # renamed for persistence only, leaving portfolio.df_holdings untouched.
    df_h_store = portfolio.df_holdings.copy()
    if "current_value" in df_h_store.columns:
        df_h_store["Market Value"] = df_h_store["current_value"]
    if "invested" in df_h_store.columns:
        df_h_store["Invested"] = df_h_store["invested"]

    session_id = str(uuid.uuid4())
    final_session_id = storage.save_session(
        session_id=session_id,
        df_h=df_h_store,
        df_t=df_trades,
        df_s=pd.DataFrame(),
        is_partial=False,
        statement_period=f"equity:{source}",
        user_id=user_id,
        upload_type=upload_type,
        ledger_hash=ledger_hash,
    )

    for frame in (portfolio.df_holdings, portfolio.df_trades):
        _compact_dtypes(frame)

    _remember(final_session_id, portfolio, owner=user_id)
    return final_session_id


def get_session(session_id: str) -> EquityPortfolio:
    """
    Return the caller's EquityPortfolio for this session.

    Raises HTTP 404 if the session has expired, does not exist, or belongs to somebody
    else. Ownership is resolved from whichever source is authoritative for the path:

    - **Resident hit** - from the entry itself, not the database. A resident session
      must stay usable when Postgres is unreachable, and a session whose registry row
      was deleted must not become readable by everyone because the registry can no
      longer name its owner.
    - **Disk miss** - from the registry, and the session must both exist and be owned
      by the caller. A lookup that *fails* (rather than returning "absent") denies
      with 503: an authorization check that cannot run must not default to allowing
      access.
    """
    with _SESSIONS_LOCK:
        entry = _SESSIONS.get(session_id)
        if entry is not None:
            if _expired(entry):
                _SESSIONS.pop(session_id, None)
                entry = None
            else:
                if not identity.owns_record(entry.get("owner")):
                    raise _deny(session_id, entry.get("owner"))
                entry["last_accessed"] = datetime.now()
                _SESSIONS.move_to_end(session_id)
                return entry["portfolio"]

    # Miss: authorize against the registry, then reconstruct from Postgres.
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

    # load_session returns (holdings, transactions, sips, is_partial). This used to
    # unpack the fourth element as `meta` and read `meta.get("source")` behind an
    # isinstance(dict) guard - which is always False for a bool, so `source` was
    # permanently "csv" and Kite-sourced portfolios silently relabelled themselves.
    # The broker is a column on the frame, so it survives the round trip honestly.
    df_h, df_t, _df_s, _is_partial = disk_data
    for frame in (df_h, df_t):
        _compact_dtypes(frame)

    source = "csv"
    if df_h is not None and not df_h.empty and "broker" in df_h.columns:
        first = df_h["broker"].iloc[0]
        if pd.notna(first) and str(first):
            source = str(first)

    portfolio = EquityPortfolio(df_h, df_t, source=source)
    try:
        portfolio.update_live_prices()
    except Exception as e:
        logger.warning(
            "[EQUITY SESSION REHYDRATE] live price refresh failed for %s: %s", session_id, e
        )

    _remember(session_id, portfolio, owner=owner)
    return portfolio


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------

def forget(session_id: str) -> bool:
    """
    Drop one resident session. Returns whether it was present.

    Called by DELETE /history/{sid}. Defining this without calling it - which is how
    it shipped - meant deleting a session removed the rows and left the portfolio in
    memory, readable by anyone holding the id.
    """
    with _SESSIONS_LOCK:
        return _SESSIONS.pop(session_id, None) is not None


def evict_for_user(user_id: str) -> int:
    """
    Drop a user's resident sessions. Returns how many were dropped.

    Required by the account purge and by logout: deleting the rows otherwise leaves
    the portfolios in memory, so data the user asked to have permanently deleted stays
    readable for up to the TTL. Compared exactly, with no case folding - the owner is
    a lower-case uuid, and an `.upper()` here would make the comparison never match
    and turn eviction into a no-op that still reports success.
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
        logger.info("[EQUITY SESSION] evicted %d resident session(s) for %s", len(doomed), user_id)
    return len(doomed)


def clear_all() -> int:
    """
    Drop every resident session. Returns how many were dropped.

    Exists so callers do not touch _SESSIONS directly - doing that skips the lock and
    races the GC daemon.
    """
    with _SESSIONS_LOCK:
        count = len(_SESSIONS)
        _SESSIONS.clear()
    return count


def purge_expired() -> int:
    """
    Drop resident sessions idle beyond the TTL.

    Registered with the shared janitor below. This used to be called by a daemon owned
    by domains/mutual_funds/sessions.py, which meant equity's memory was only bounded
    as long as the mutual-funds module happened to be imported.

    The TTL is also enforced lazily on read, so this is about releasing memory from
    sessions nobody comes back to, not about correctness.
    """
    now = datetime.now()
    with _SESSIONS_LOCK:
        expired = [sid for sid, entry in _SESSIONS.items() if _expired(entry, now)]
        for sid in expired:
            _SESSIONS.pop(sid, None)
    return len(expired)


janitor.register("equity.sessions", purge_expired)


def session_stats() -> dict[str, Any]:
    """Resident-session metrics, for health reporting."""
    with _SESSIONS_LOCK:
        return {
            "resident": len(_SESSIONS),
            "resident_cap": MAX_RESIDENT_SESSIONS,
            "ttl_hours": SESSION_TTL_HOURS,
        }


# Logout, account purge and history-delete used to name this module explicitly from
# three shared routers; they iterate the registry instead. Equity was once missing from
# one of those hardcoded lists, and a purge deleted the rows while leaving the stock
# portfolios resident and readable. See shared/session_stores.py.
session_stores.register(session_stores.SessionStore(
    name="equity",
    evict_user=evict_for_user,
    forget_session=forget,
    clear_all=clear_all,
))
