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
import time
from collections import OrderedDict
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Storage Path ──────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "metadata.sqlite3"

# ── Bounds ────────────────────────────────────────────────────────────────────
# Each session holds a full parsed AIS (potentially hundreds of trades), so the
# ceiling here is effectively a memory budget. Tunable via env for deployments
# with more headroom than Render's free 512 MB.
MAX_SESSIONS = int(os.getenv("FINANCEBUDDY_MAX_TAX_SESSIONS", "40"))
SESSION_TTL_SECONDS = int(os.getenv("FINANCEBUDDY_TAX_SESSION_TTL", str(24 * 3600)))


def _connect():
    """Open a SQLite connection. Callers must close it.

    `with sqlite3.connect(...)` commits but does NOT close, so the previous code
    leaked a connection object and fd per operation until GC.
    """
    return sqlite3.connect(DB_PATH)


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
_tax_sessions: "OrderedDict[str, dict]" = OrderedDict()
_sessions_loaded: bool = False


# ── Persistence ───────────────────────────────────────────────────────────────

def _load_from_disk():
    """Load non-expired sessions from SQLite into memory, newest first."""
    global _tax_sessions, _sessions_loaded
    _tax_sessions = OrderedDict()
    cutoff = time.time() - SESSION_TTL_SECONDS
    conn = None
    try:
        conn = _connect()
        # Oldest-first so that the OrderedDict ends up most-recent-last, which is
        # the ordering LRU eviction expects.
        rows = conn.execute(
            "SELECT session_id, data, updated_at FROM tax_sessions "
            "ORDER BY updated_at ASC LIMIT ?",
            (MAX_SESSIONS,),
        ).fetchall()
        expired = []
        for sid, blob, updated_at in rows:
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


def _persist_one(session_id: str):
    """Write a single session through to SQLite."""
    session = _tax_sessions.get(session_id)
    if session is None:
        return
    conn = None
    try:
        now = time.time()
        # `_last_access` is bookkeeping for in-memory LRU and is excluded from the
        # stored blob; `_version` is kept so the computation cache stays correct
        # across a reload.
        blob = json.dumps(
            {k: v for k, v in session.items() if k != "_last_access"},
            ensure_ascii=False,
            default=str,
        )
        conn = _connect()
        conn.execute(
            """
            INSERT INTO tax_sessions (session_id, pan, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                data=excluded.data, pan=excluded.pan, updated_at=excluded.updated_at
            """,
            (session_id, session.get("pan", ""), blob, now, now),
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
    if not _sessions_loaded:
        _load_from_disk()


def _touch(session_id: str):
    """Mark a session as most-recently-used."""
    if session_id in _tax_sessions:
        _tax_sessions[session_id]["_last_access"] = time.time()
        _tax_sessions.move_to_end(session_id)


def _evict():
    """Drop idle-expired sessions, then LRU-trim to MAX_SESSIONS."""
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
        _delete_many(dropped)
        logger.info(f"Evicted {len(dropped)} tax session(s) (idle TTL / LRU cap).")


def _bump(session: dict):
    """Invalidate any cached computation derived from this session.

    The computation cache keys on this counter, so every mutation path must call
    it or memoized results go stale.
    """
    session["_version"] = session.get("_version", 0) + 1


def get_session_version(session_id: str) -> int:
    """Monotonic mutation counter, used as a computation-cache key component."""
    session = _tax_sessions.get(session_id)
    return session.get("_version", 0) if session else -1


# ── Public API ────────────────────────────────────────────────────────────────

def create_tax_session(ais_data: dict, pan_id: Optional[str] = None, flags: Optional[dict] = None) -> str:
    """Create a new tax session from parsed AIS data and persist it."""
    _ensure_loaded()
    session_id = str(uuid.uuid4())
    pan = pan_id or ais_data.get("personal", {}).get("pan", "")
    _tax_sessions[session_id] = {
        "ais_data": ais_data,
        "deductions": {},
        "overrides": {},
        "pan": pan,
        "reconciliation_flags": flags or {},
        "_version": 0,
        "_last_access": time.time(),
    }
    _evict()
    _persist_one(session_id)
    logger.info(f"Created tax session {session_id} for PAN {pan}")
    return session_id


def get_tax_session(session_id: str) -> Optional[dict]:
    """Retrieve a tax session by ID, refreshing its LRU position."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if session is not None:
        _touch(session_id)
    return session


def update_deductions(session_id: str, deductions: dict) -> bool:
    """Update user-provided deductions for a tax session."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["deductions"] = deductions
    _bump(session)
    _touch(session_id)
    _persist_one(session_id)
    return True


def update_ais_data(session_id: str, ais_data: dict) -> bool:
    """Update AIS data (e.g., manual cost patching) and persist."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["ais_data"] = ais_data
    _bump(session)
    _touch(session_id)
    _persist_one(session_id)
    return True


def update_overrides(session_id: str, overrides: dict) -> bool:
    """Update manual inputs (losses, deductions, schedule AL) and persist."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    if "overrides" not in session:
        session["overrides"] = {}

    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(session["overrides"].get(k), dict):
            session["overrides"][k].update(v)
        else:
            session["overrides"][k] = v

    _bump(session)
    _touch(session_id)
    _persist_one(session_id)
    return True


def delete_tax_session(session_id: str) -> bool:
    """Delete a tax session from memory and SQLite."""
    _ensure_loaded()
    if session_id in _tax_sessions:
        del _tax_sessions[session_id]
        _delete_many([session_id])
        _drop_cached_computations(session_id)
        return True
    return False


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

    Used by the admin cache-clear endpoint. Kept as a function so callers do not
    manipulate the private dict directly.
    """
    _tax_sessions.clear()


def list_sessions() -> list:
    """Public read-only view of stored sessions, as (session_id, session) pairs.

    Exists so cross-domain callers (shared/routers/accounts.py) stop reaching
    into the private `_tax_sessions` global.
    """
    _ensure_loaded()
    return list(_tax_sessions.items())


def get_sessions_by_pan(pan: str) -> list:
    """Get all tax sessions for a given PAN."""
    _ensure_loaded()
    target = pan.upper()
    results = []
    for sid, data in _tax_sessions.items():
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
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["itr_data"] = itr_data
    _bump(session)
    _touch(session_id)
    _persist_one(session_id)
    logger.info(f"ITR data saved for session {session_id}")
    return True


def get_itr_data(session_id: str) -> Optional[dict]:
    """Retrieve previously parsed ITR data for a session."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return None
    return session.get("itr_data")


def delete_all_for_pan(pan: str) -> int:
    """Delete all tax sessions for a given PAN from memory and disk."""
    _ensure_loaded()
    target = pan.upper()
    keys_to_delete = [
        sid for sid, data in _tax_sessions.items()
        if data.get("pan", "").upper() == target
    ]
    for sid in keys_to_delete:
        del _tax_sessions[sid]
        _drop_cached_computations(sid)
    if keys_to_delete:
        _delete_many(keys_to_delete)
    return len(keys_to_delete)
