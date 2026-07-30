"""
core/tax_sessions.py

Session store for Tax Expert AIS data: an in-memory dict of record, written
through to SQLite per session.

Design notes
------------
Writes are per-session. The previous implementation re-serialized *every*
session on every mutation (json.dumps per session plus a rebuilt
`DELETE ... NOT IN (?,?,...)`), so editing one 80C field with N sessions stored
cost O(N x blob_size). The deduction form hits that path on every save.

The cache is bounded. It previously had no TTL, no size limit and no eviction,
and `_load_from_disk` pulled every session of every user into RAM on first
access and kept them resident forever — unusable on a 512 MB instance. Sessions
now expire by idle age and the store is capped, evicting least-recently-used.

Persistence is best-effort. On Render's free tier the filesystem is ephemeral
(wiped on redeploy and on spin-down), so SQLite is a within-process-lifetime
convenience, not durable storage. Callers must treat a missing session as
normal — the API returns 404 and the UI prompts for re-upload.
"""

import uuid
import json
import os
import sqlite3
import logging
import threading
import time
from collections import OrderedDict
from typing import Optional
from pathlib import Path

from shared import identity
from shared.identity import mask_pan
from shared.storage import _apply_pragmas

logger = logging.getLogger(__name__)

# ── Storage Path ──────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "metadata.sqlite3"

# ── Bounds ────────────────────────────────────────────────────────────────────
# Each session holds a full parsed AIS (potentially thousands of trade dicts at
# ~500-900 bytes each, so ~1.5-2 MB per session for an active trader). At the previous
# default of 40 that was a 60-80 MB resident budget on a 512 MB box with a ~50 MB
# baseline - and the bound is on entry count, which is a poor proxy when entry size
# varies this much.
#
# Lowered to 8 now that eviction is non-destructive: _rehydrate() restores an evicted
# session from SQLite on the next request, so a low cap costs a disk read rather than
# the user's uploaded data. Do not raise this without checking that rehydration still
# works. The mutual-funds store caps at 3 for the same reason.
MAX_SESSIONS = int(os.getenv("FINANCEBUDDY_MAX_TAX_SESSIONS", "8"))
SESSION_TTL_SECONDS = int(os.getenv("FINANCEBUDDY_TAX_SESSION_TTL", str(24 * 3600)))


def _connect():
    """Open a SQLite connection. Callers must close it.

    `with sqlite3.connect(...)` commits but does NOT close, so the previous code
    leaked a connection object and fd per operation until GC.

    Shares the same pragmas as shared/storage.py - this is the *same database file*,
    so WAL and the busy timeout have to be consistent or a tax write can still block
    mutual-fund readers.
    """
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    _apply_pragmas(conn)
    return conn


def _init_db():
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tax_sessions (
                session_id TEXT PRIMARY KEY,
                pan TEXT,
                data TEXT
            )
        """)
        # Migrate older databases that predate the timestamp columns. Without a
        # created_at/updated_at nothing could ever expire by age, which is why
        # the store grew without bound.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tax_sessions)")}
        if "created_at" not in existing:
            conn.execute("ALTER TABLE tax_sessions ADD COLUMN created_at REAL DEFAULT 0")
        if "updated_at" not in existing:
            conn.execute("ALTER TABLE tax_sessions ADD COLUMN updated_at REAL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tax_sessions_pan ON tax_sessions(pan)")
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize tax_sessions schema: {e}")
    finally:
        conn.close()


_init_db()

# In-memory record of truth. OrderedDict so eviction can be least-recently-used.
#
# Guarded by _SESSIONS_LOCK. Every endpoint in this domain is a sync `def`, which
# FastAPI runs in a threadpool, so these globals are genuinely touched concurrently.
# Without the lock, _evict()/get_sessions_by_pan()/list_sessions() iterate while
# another thread inserts or calls move_to_end - and because move_to_end mutates
# OrderedDict's internal link state, CPython raises
# "RuntimeError: OrderedDict mutated during iteration" with no size change at all.
# GET /accounts/summary concurrent with any tax request was a reachable 500.
#
# The mutual-funds store (domains/mutual_funds/sessions.py) already had this lock;
# this module received the "bounded" half of that fix without the "locked" half.
_tax_sessions: "OrderedDict[str, dict]" = OrderedDict()
_sessions_loaded: bool = False
_SESSIONS_LOCK = threading.RLock()


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_from_disk_locked():
    """
    Populate the in-memory store from SQLite. Caller must hold _SESSIONS_LOCK.

    Two fixes over the original:

    - It **clears in place** instead of rebinding `_tax_sessions` to a fresh
      OrderedDict. Rebinding meant two concurrent first-requests after boot each
      installed their own dict, so the second silently discarded the session the
      first had just created.
    - It selects the **newest** MAX_SESSIONS rows, not the oldest. `ORDER BY
      updated_at ASC LIMIT 40` returned the 40 *stalest* sessions, so a restart
      restored the ones most likely to be expiring and dropped the one the user was
      actively working in. Rows are re-inserted oldest-first afterwards, because
      that is the ordering LRU eviction expects.
    """
    global _sessions_loaded
    _tax_sessions.clear()
    cutoff = time.time() - SESSION_TTL_SECONDS
    conn = None
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT session_id, data, updated_at FROM tax_sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (MAX_SESSIONS,),
        ).fetchall()
        expired = []
        # Oldest-first insertion => most-recently-used ends up last.
        for sid, blob, updated_at in reversed(rows):
            if updated_at and updated_at < cutoff:
                expired.append(sid)
                continue
            try:
                session = json.loads(blob)
            except (ValueError, TypeError) as e:
                logger.warning(f"Discarding unreadable tax session {sid}: {e}")
                expired.append(sid)
                continue
            session.setdefault("_version", 0)
            session["_last_access"] = updated_at or time.time()
            _tax_sessions[sid] = session
        if expired:
            conn.executemany(
                "DELETE FROM tax_sessions WHERE session_id = ?", [(s,) for s in expired]
            )
            conn.commit()
            logger.info(f"Purged {len(expired)} expired/unreadable tax session(s).")
        logger.info(f"Loaded {len(_tax_sessions)} tax session(s) from SQLite.")
    except Exception as e:
        logger.error(f"Failed to load tax sessions from SQLite: {e}")
    finally:
        if conn:
            conn.close()
    _sessions_loaded = True


def _rehydrate(session_id: str) -> Optional[dict]:
    """
    Load a single session from SQLite after an in-memory miss.

    This is what makes LRU eviction non-destructive. Eviction used to call
    _delete_many(), deleting the only durable copy - so an evicted session was
    permanently gone and the user had to re-upload their AIS. The mutual-funds store
    could safely evict precisely because rehydration already existed; this is the
    equivalent.

    The SQLite read happens outside the lock; only the insert is guarded.
    """
    conn = None
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT data, updated_at FROM tax_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    except Exception as e:
        logger.error(f"Failed to rehydrate tax session {session_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

    if row is None:
        return None

    blob, updated_at = row
    if updated_at and updated_at < time.time() - SESSION_TTL_SECONDS:
        return None
    try:
        session = json.loads(blob)
    except (ValueError, TypeError) as e:
        logger.warning(f"Discarding unreadable tax session {session_id}: {e}")
        return None

    session.setdefault("_version", 0)
    session["_last_access"] = time.time()

    with _SESSIONS_LOCK:
        # Another thread may have won the race; prefer the resident copy so two
        # callers never hold different dicts for one session.
        if session_id in _tax_sessions:
            _touch_locked(session_id)
            return _tax_sessions[session_id]
        _tax_sessions[session_id] = session
        _evict_locked()
    logger.info(f"Rehydrated tax session {session_id} from SQLite.")
    return session


def purge_expired_from_disk() -> int:
    """
    Delete rows past their TTL. Returns how many were removed.

    Needed now that eviction no longer deletes from disk: without a periodic sweep
    the table would only ever grow between restarts. Called from the session GC
    daemon in domains/mutual_funds/sessions.py, which already runs every 10 minutes.
    """
    cutoff = time.time() - SESSION_TTL_SECONDS
    conn = None
    try:
        conn = _connect()
        cursor = conn.execute(
            "DELETE FROM tax_sessions WHERE updated_at > 0 AND updated_at < ?", (cutoff,)
        )
        conn.commit()
        removed = cursor.rowcount or 0
        if removed:
            logger.info(f"Swept {removed} expired tax session row(s) from disk.")
        return removed
    except Exception as e:
        logger.error(f"Failed to sweep expired tax sessions: {e}")
        return 0
    finally:
        if conn:
            conn.close()


def _persist_one(session_id: str):
    """
    Write a single session through to SQLite.

    The top-level snapshot is taken under the lock: serializing the live dict meant
    json.dumps could iterate it while another thread replaced a key, raising
    "dictionary changed size during iteration". A shallow copy is enough here because
    every mutation path assigns a whole top-level value rather than editing nested
    structures in place.

    The dumps and the write happen outside the lock, so disk I/O does not block
    other readers.
    """
    with _SESSIONS_LOCK:
        session = _tax_sessions.get(session_id)
        if session is None:
            return
        # `_last_access` is bookkeeping for in-memory LRU and is excluded from the
        # stored blob; `_version` is kept so the computation cache stays correct
        # across a reload.
        snapshot = {k: v for k, v in session.items() if k != "_last_access"}
        pan = session.get("pan", "")

    conn = None
    try:
        now = time.time()
        blob = json.dumps(snapshot, ensure_ascii=False, default=str)
        conn = _connect()
        conn.execute(
            """
            INSERT INTO tax_sessions (session_id, pan, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                data=excluded.data, pan=excluded.pan, updated_at=excluded.updated_at
            """,
            (session_id, pan, blob, now, now),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist tax session {session_id}: {e}")
    finally:
        if conn:
            conn.close()


def _delete_many(session_ids: list):
    if not session_ids:
        return
    conn = None
    try:
        conn = _connect()
        conn.executemany(
            "DELETE FROM tax_sessions WHERE session_id = ?", [(s,) for s in session_ids]
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to delete tax sessions {session_ids}: {e}")
    finally:
        if conn:
            conn.close()


def _ensure_loaded():
    """
    Load from disk on first use.

    Guarded: `if not _sessions_loaded: _load_from_disk()` was an unsynchronized
    check-then-act, so two concurrent cold-start requests both entered it.
    """
    with _SESSIONS_LOCK:
        if not _sessions_loaded:
            _load_from_disk_locked()


def _touch_locked(session_id: str):
    """Mark a session most-recently-used. Caller must hold _SESSIONS_LOCK."""
    if session_id in _tax_sessions:
        _tax_sessions[session_id]["_last_access"] = time.time()
        _tax_sessions.move_to_end(session_id)


def _evict_locked():
    """
    Drop idle-expired sessions, then LRU-trim to MAX_SESSIONS.
    Caller must hold _SESSIONS_LOCK.

    Deliberately does NOT delete from SQLite. It used to, which made eviction
    destructive: the row was the only durable copy, so an LRU-evicted session was
    unrecoverable and the user's uploaded AIS was simply gone. Disk rows are instead
    bounded by purge_expired_from_disk() on the GC sweep, and an evicted session is
    restored on demand by _rehydrate().
    """
    now = time.time()
    dropped = [
        sid for sid, s in _tax_sessions.items()
        if now - s.get("_last_access", now) > SESSION_TTL_SECONDS
    ]
    while len(_tax_sessions) - len(dropped) > MAX_SESSIONS:
        for sid in _tax_sessions:
            if sid not in dropped:
                dropped.append(sid)
                break
    for sid in dropped:
        _tax_sessions.pop(sid, None)
    if dropped:
        logger.info(
            f"Evicted {len(dropped)} tax session(s) from memory "
            f"(idle TTL / LRU cap {MAX_SESSIONS}); recoverable from SQLite."
        )


def _bump(session: dict):
    """Invalidate any cached computation derived from this session.

    The computation cache keys on this counter, so every mutation path must call
    it or memoized results go stale.
    """
    session["_version"] = session.get("_version", 0) + 1


def get_session_version(session_id: str) -> int:
    """
    Monotonic mutation counter, used as a computation-cache key component.

    Rehydrates on a miss. It used to read only the resident store and return -1
    otherwise, which became dangerous once eviction stopped being destructive and the
    resident cap dropped 40 -> 8: an evicted-but-alive session reported -1, so the
    computation cache keyed a result at (sid, -1, regime). After a rehydrate, an edit,
    and another eviction, the key was (sid, -1, regime) again - a hit that returned the
    *pre-edit* tax computation.

    -1 now means only "no such session", which can never collide with a real version.
    """
    with _SESSIONS_LOCK:
        session = _tax_sessions.get(session_id)
        if session is not None:
            return session.get("_version", 0)

    restored = _rehydrate(session_id)
    return restored.get("_version", 0) if restored else -1


# ── Public API ────────────────────────────────────────────────────────────────

def create_tax_session(ais_data: dict, pan_id: Optional[str] = None, flags: Optional[dict] = None) -> str:
    """Create a new tax session from parsed AIS data and persist it."""
    _ensure_loaded()
    session_id = str(uuid.uuid4())
    # Normalized, and preferring the *caller's* identity over the PAN printed in the
    # document. Two bugs came from not doing this: a raw lowercase header stored an
    # owner that no normalized read could match, and falling back to the AIS PDF's own
    # PAN made an anonymous upload immediately unreadable by the anonymous uploader -
    # which surfaced as a 500 after a multi-second parse.
    pan = (
        identity.normalize_pan(pan_id)
        or identity.current_pan()
        or identity.normalize_pan(ais_data.get("personal", {}).get("pan", ""))
        or ""
    )
    with _SESSIONS_LOCK:
        _tax_sessions[session_id] = {
            "ais_data": ais_data,
            "deductions": {},
            "overrides": {},
            "pan": pan,
            "reconciliation_flags": flags or {},
            "_version": 0,
            "_last_access": time.time(),
        }
        _evict_locked()
    _persist_one(session_id)
    logger.info(f"Created tax session {session_id} for PAN {mask_pan(pan)}")
    return session_id


def _owned_or_none(session: Optional[dict]) -> Optional[dict]:
    """
    Gate a session on the calling PAN.

    Returns None for somebody else's session, so every caller's existing "not found"
    branch handles it - and the response cannot distinguish "wrong owner" from
    "no such session", which is what stops session-id guessing from being useful.
    """
    if session is None:
        return None
    owner = session.get("pan") or None
    if not identity.owns_record(owner):
        logger.warning(
            "[AUTHZ] %s denied access to tax session owned by %s",
            mask_pan(identity.current_pan()), mask_pan(owner),
        )
        return None
    return session


def get_tax_session(session_id: str) -> Optional[dict]:
    """
    Retrieve a tax session by ID, refreshing its LRU position.

    Returns None if the session does not exist, has expired, or belongs to a
    different PAN.
    """
    _ensure_loaded()
    with _SESSIONS_LOCK:
        session = _tax_sessions.get(session_id)
        if session is not None:
            _touch_locked(session_id)
            return _owned_or_none(session)

    # Miss: it may have been LRU-evicted while its disk row survives.
    return _owned_or_none(_rehydrate(session_id))


def _mutate(session_id: str, apply) -> bool:
    """
    Shared read-modify-write path for the update_* functions.

    `apply(session)` mutates the session dict under the lock. Persistence happens
    after the lock is released, so SQLite I/O does not serialize every other reader.

    Deliberately does NOT re-insert the session into the store before writing. An
    earlier version did, to close a lost-update window (evicted between the read and
    the write, after which `_persist_one` finds nothing and silently skips). That guard
    was wrong on balance: it turned a concurrent delete into an **undelete** - an
    in-flight override racing `DELETE /accounts/{pan}` or `/auth/logout` re-persisted
    the whole AIS blob and the PAN back to SQLite, defeating a purge the user was told
    was permanent. Silently dropping one edit is bad; silently resurrecting data
    someone asked to have deleted is worse.

    So `_persist_one` is authoritative: if the session is no longer live, the write is
    skipped. The lost-update window remains, is narrow (it needs an eviction between
    two lock acquisitions), and is the correct trade against resurrection.
    """
    _ensure_loaded()
    with _SESSIONS_LOCK:
        session = _tax_sessions.get(session_id)
    if session is None:
        session = _rehydrate(session_id)
    if session is None or _owned_or_none(session) is None:
        return False

    with _SESSIONS_LOCK:
        # Re-check liveness: it may have been deleted or purged while we were
        # authorizing. Mutating a dropped session must not write it back.
        if session_id not in _tax_sessions:
            logger.info("[TAX] dropping write to %s: no longer live", session_id)
            return False
        apply(session)
        _bump(session)
        _touch_locked(session_id)
    _persist_one(session_id)
    return True


def update_deductions(session_id: str, deductions: dict) -> bool:
    """Update user-provided deductions for a tax session."""
    def apply(session):
        session["deductions"] = deductions
    return _mutate(session_id, apply)


def update_ais_data(session_id: str, ais_data: dict) -> bool:
    """Update AIS data (e.g., manual cost patching) and persist."""
    def apply(session):
        session["ais_data"] = ais_data
    return _mutate(session_id, apply)


def update_overrides(session_id: str, overrides: dict) -> bool:
    """Update manual inputs (losses, deductions, schedule AL) and persist."""
    def apply(session):
        if "overrides" not in session:
            session["overrides"] = {}
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(session["overrides"].get(k), dict):
                session["overrides"][k].update(v)
            else:
                session["overrides"][k] = v
    return _mutate(session_id, apply)


def delete_tax_session(session_id: str) -> bool:
    """Delete a tax session from memory and SQLite."""
    _ensure_loaded()
    with _SESSIONS_LOCK:
        present = session_id in _tax_sessions
        if present:
            del _tax_sessions[session_id]
    # Delete the row even on an in-memory miss: it may simply have been evicted.
    _delete_many([session_id])
    _drop_cached_computations(session_id)
    return present


def _drop_cached_computations(session_id: str):
    """Purge memoized computations for a deleted session.

    Imported lazily to avoid a circular import: computation_cache imports this
    module for get_session_version().
    """
    try:
        from domains.tax_expert.computation_cache import invalidate_session
        invalidate_session(session_id)
    except Exception:  # pragma: no cover - cache purging must never break deletion
        pass


def clear_all():
    """Drop every in-memory session (does not touch SQLite).

    Resets `_sessions_loaded` too. Without that, this bricked the store: the flag
    stayed True, so _ensure_loaded() never reloaded and every tax session 404'd
    until the process restarted - even though the rows were intact on disk.
    """
    global _sessions_loaded
    with _SESSIONS_LOCK:
        _tax_sessions.clear()
        _sessions_loaded = False


def list_sessions() -> list:
    """Public read-only view of stored sessions, as (session_id, session) pairs.

    Exists so cross-domain callers (shared/routers/accounts.py) stop reaching
    into the private `_tax_sessions` global. Returns a snapshot list built under the
    lock, so the caller can iterate it safely while other threads mutate the store.
    """
    _ensure_loaded()
    with _SESSIONS_LOCK:
        return list(_tax_sessions.items())


def get_sessions_by_pan(pan: str) -> list:
    """Get all tax sessions for a given PAN."""
    _ensure_loaded()
    target = pan.upper()
    results = []
    with _SESSIONS_LOCK:
        snapshot = list(_tax_sessions.items())
    for sid, data in snapshot:
        if data.get("pan", "").upper() == target:
            ais = data.get("ais_data", {})
            results.append({
                "session_id": sid,
                "pan": data.get("pan", ""),
                "name": ais.get("personal", {}).get("name", ""),
                "fy": ais.get("fy", ""),
                "gross_salary": ais.get("salary", {}).get("gross", 0),
            })
    return results


def update_itr_data(session_id: str, itr_data: dict) -> bool:
    """Persist parsed ITR data into a tax session for comparison."""
    def apply(session):
        session["itr_data"] = itr_data
    saved = _mutate(session_id, apply)
    if saved:
        logger.info(f"ITR data saved for session {session_id}")
    return saved


def get_itr_data(session_id: str) -> Optional[dict]:
    """Retrieve previously parsed ITR data for a session."""
    session = get_tax_session(session_id)
    return session.get("itr_data") if session else None


def delete_all_for_pan(pan: str) -> int:
    """
    Delete all tax sessions for a given PAN from memory and disk.

    Deletes by PAN directly in SQL as well as in memory, so sessions that are on
    disk but not currently resident (LRU-evicted) are also removed - otherwise a
    purge would silently leave them behind to be rehydrated later.
    """
    _ensure_loaded()
    target = pan.upper()
    with _SESSIONS_LOCK:
        keys_to_delete = [
            sid for sid, data in _tax_sessions.items()
            if data.get("pan", "").upper() == target
        ]
        for sid in keys_to_delete:
            del _tax_sessions[sid]
    for sid in keys_to_delete:
        _drop_cached_computations(sid)

    conn = None
    try:
        conn = _connect()
        cursor = conn.execute("DELETE FROM tax_sessions WHERE UPPER(pan) = ?", (target,))
        conn.commit()
        removed = max(cursor.rowcount or 0, len(keys_to_delete))
    except Exception as e:
        logger.error(f"Failed to delete tax sessions for PAN {mask_pan(pan)}: {e}")
        removed = len(keys_to_delete)
    finally:
        if conn:
            conn.close()
    return removed
