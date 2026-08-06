"""
core/tax_sessions.py

Session store for Tax Expert AIS data: an in-memory dict of record, written
through to Postgres per session.

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

Persistence is durable. Rows live in Postgres and survive restarts, so an evicted
session is a cache miss rather than data loss — _rehydrate() restores it. The
document is encrypted at rest (shared/crypto.py); only the session_id, owner and
timestamps are readable in the database.
"""

import uuid
import json
import hashlib
import os
import logging
import threading
import time
from collections import OrderedDict
from typing import Optional

from shared import crypto, db, identity, session_stores
from shared.identity import mask_pan

logger = logging.getLogger(__name__)

# Connection handling lives in shared/db.py. This module used to open its own, via a
# second DB_PATH constant naming the same SQLite file - so a test redirecting
# storage.DB_PATH to a throwaway database left this store writing to the real one.

# ── Bounds ────────────────────────────────────────────────────────────────────
# Each session holds a full parsed AIS (potentially thousands of trade dicts at
# ~500-900 bytes each, so ~1.5-2 MB per session for an active trader). At the previous
# default of 40 that was a 60-80 MB resident budget on a 512 MB box with a ~50 MB
# baseline - and the bound is on entry count, which is a poor proxy when entry size
# varies this much.
#
# Lowered to 8 now that eviction is non-destructive: _rehydrate() restores an evicted
# session from the database on the next request, so a low cap costs a read rather than
# the user's uploaded data. Do not raise this without checking that rehydration still
# works. The mutual-funds store caps at 3 for the same reason.
MAX_SESSIONS = int(os.getenv("FINANCEBUDDY_MAX_TAX_SESSIONS", "8"))
SESSION_TTL_SECONDS = int(os.getenv("FINANCEBUDDY_TAX_SESSION_TTL", str(24 * 3600)))


# In-memory record of truth. OrderedDict so eviction can be least-recently-used.
#
# Guarded by _SESSIONS_LOCK. Every endpoint in this domain is a sync `def`, which
# FastAPI runs in a threadpool, so these globals are genuinely touched concurrently.
# Without the lock, _evict()/list_sessions() iterate while
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
    Populate the in-memory store from the database. Caller must hold _SESSIONS_LOCK.

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
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, data, EXTRACT(EPOCH FROM updated_at)
                FROM tax_payloads
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (MAX_SESSIONS,),
            ).fetchall()
            # Oldest-first insertion => most-recently-used ends up last.
            for sid, blob, updated_at in reversed(rows):
                try:
                    session = crypto.decrypt_json(blob, aad=sid)
                    if not isinstance(session, dict):
                        raise TypeError(f"expected an object, got {type(session).__name__}")
                except (crypto.DecryptionFailed, ValueError, TypeError) as e:
                    # Not deleted: an undecryptable row is far more likely a
                    # misconfigured key than a corrupt session, and dropping it would
                    # turn a recoverable config mistake into permanent data loss.
                    logger.error(f"Skipping unreadable tax session {sid}: {e}")
                    continue
                session.setdefault("_version", 0)
                session["_last_access"] = updated_at or time.time()
                _tax_sessions[sid] = session
        logger.info(f"Loaded {len(_tax_sessions)} tax session(s) from the database.")
    except Exception as e:
        logger.error(f"Failed to load tax sessions: {e}")
    _sessions_loaded = True


def _rehydrate(session_id: str) -> Optional[dict]:
    """
    Load a single session from the database after an in-memory miss.

    This is what makes LRU eviction non-destructive. Eviction used to call
    _delete_many(), deleting the only durable copy - so an evicted session was
    permanently gone and the user had to re-upload their AIS. The mutual-funds store
    could safely evict precisely because rehydration already existed; this is the
    equivalent.

    The read happens outside the lock; only the insert is guarded.
    """
    try:
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT data, EXTRACT(EPOCH FROM updated_at)
                FROM tax_payloads WHERE session_id = %s
                """,
                (session_id,),
            ).fetchone()
    except Exception as e:
        logger.error(f"Failed to rehydrate tax session {session_id}: {e}")
        return None

    if row is None:
        return None

    blob, _ = row
    try:
        session = crypto.decrypt_json(blob, aad=session_id)
        if not isinstance(session, dict):
            raise TypeError(f"expected an object, got {type(session).__name__}")  # pragma: no cover — defensive / hard to exercise in unit tests
    except (crypto.DecryptionFailed, ValueError, TypeError) as e:
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
    logger.info(f"Rehydrated tax session {session_id} from the database.")
    return session


# purge_expired_from_disk() was here. It had already been reduced to `return 0`, and
# its docstring said it survived only because the GC daemon in
# domains/mutual_funds/sessions.py called it on every sweep. That daemon is gone (see
# shared/janitor.py), so this is the tidy-up it asked for.
#
# Nothing replaces it deliberately: a stored tax session is the user's parsed AIS, and
# deleting it on a timer is data loss, not housekeeping. The in-memory TTL in
# _evict_locked() still applies - that is a cache bound, and an evicted session is
# restored by _rehydrate() on next access. Explicit deletion is
# DELETE /tax-expert/tax-history/{id} or DELETE /accounts/me.


def _summarise(session: dict) -> dict:
    """
    The few fields the history timeline needs, denormalised onto the registry row.

    Without this, listing a user's tax sessions means decompressing and parsing every
    payload just to print a heading. The mutual-funds side has carried
    total_value/num_funds on its registry row for exactly this reason.
    """
    ais = session.get("ais_data") or {}
    return {
        "name": (ais.get("personal") or {}).get("name", ""),
        "fy": ais.get("fy", ""),
        "gross_salary": (ais.get("salary") or {}).get("gross", 0),
    }


def _persist_one(session_id: str):
    """
    Write a single session through to the database.

    Two rows, one transaction: the registry entry in `sessions` (which is what makes
    a tax session visible to /history alongside CAS uploads) and the document itself
    in `tax_payloads`. They used to live in a private `tax_sessions` table that no
    shared query could see.

    The top-level snapshot is taken under the lock: serializing the live dict meant
    json.dumps could iterate it while another thread replaced a key, raising
    "dictionary changed size during iteration". A shallow copy is enough because every
    mutation path assigns a whole top-level value rather than editing nested
    structures in place.

    The dumps and the write happen outside the lock, so I/O does not block readers.
    """
    with _SESSIONS_LOCK:
        session = _tax_sessions.get(session_id)
        if session is None:
            return  # pragma: no cover — defensive / hard to exercise in unit tests
        # `_last_access` is bookkeeping for in-memory LRU and is excluded from the
        # stored blob; `_version` is kept so the computation cache stays correct
        # across a reload.
        snapshot = {k: v for k, v in session.items() if k != "_last_access"}
        user_id = session.get("user_id") or None
        version = session.get("_version", 0)
        summary = _summarise(session)
        fingerprint = _ais_fingerprint(session.get("ais_data") or {}, user_id)

    try:
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, user_id, upload_type, data_hash, metrics, updated_at)
                VALUES (%s, %s, 'tax_expert', %s, %s, now())
                ON CONFLICT (session_id) DO UPDATE SET
                    data_hash = EXCLUDED.data_hash,
                    metrics = EXCLUDED.metrics,
                    updated_at = now()
                """,
                # gross_salary lives in here, so the timeline summary is encrypted
                # alongside the document rather than left queryable.
                (session_id, user_id, fingerprint,
                 crypto.encrypt_json({"summary": summary}, aad=session_id)),
            )
            conn.execute(
                """
                INSERT INTO tax_payloads (session_id, data, version, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (session_id) DO UPDATE SET
                    data = EXCLUDED.data,
                    version = EXCLUDED.version,
                    updated_at = now()
                """,
                (session_id, crypto.encrypt_json(snapshot, aad=session_id), version),
            )
    except Exception as e:
        logger.error(f"Failed to persist tax session {session_id}: {e}")


def _delete_many(session_ids: list):
    if not session_ids:
        return  # pragma: no cover — defensive / hard to exercise in unit tests
    try:
        with db.connect() as conn:
            # One statement, not 2N. The tax_payloads row goes with it: its
            # session_id is `REFERENCES sessions(session_id) ON DELETE CASCADE`
            # (migrations/0001_initial.sql:120), so deleting it explicitly was a
            # redundant round trip per id.
            #
            # Note the explicit cursor: in psycopg 3 `executemany` is a *cursor*
            # method. psycopg.Connection offers the convenience `execute()` used
            # elsewhere in this module but has no `executemany`, so calling it on the
            # connection raises AttributeError - and this path is only reachable with
            # a live database, so the test suite cannot catch that.
            with conn.cursor() as cur:
                cur.executemany(
                    "DELETE FROM sessions WHERE session_id = %s",
                    [(s,) for s in session_ids],
                )
    except Exception as e:
        logger.error(f"Failed to delete tax sessions {session_ids}: {e}")


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

    Deliberately does NOT delete the stored row. It used to, which made eviction
    destructive: the row was the only durable copy, so an LRU-evicted session was
    unrecoverable and the user's uploaded AIS was simply gone. Disk rows are instead
    not bounded by any timer (a stored AIS is the user's data), and an evicted session is
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
        # Drop the memoized computations too. Each cache entry holds the session's AIS
        # detail lists *by reference*, so evicting the session here freed nothing while a
        # cached computation still pointed at it - and the cache holds up to 24 entries
        # against this store's 8, so it could pin three times as many AIS documents as
        # the store is allowed to. Imported locally: computation_cache imports this
        # module for get_session_version, so a top-level import would be circular.
        try:
            from domains.tax_expert.computation_cache import invalidate_session
            for sid in dropped:
                invalidate_session(sid)
        except Exception as e:  # pragma: no cover — defensive / hard to exercise in unit tests
            logger.warning("Could not invalidate computations for evicted sessions: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

        logger.info(
            f"Evicted {len(dropped)} tax session(s) from memory "
            f"(idle TTL / LRU cap {MAX_SESSIONS}); recoverable from the database."
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

def _ais_fingerprint(ais_data: dict, user_id: Optional[str]) -> str:
    """
    A deterministic fingerprint of a parsed AIS, scoped to its owner.

    Mirrors what the mutual-funds side does with a transaction ledger. Without it,
    re-uploading the same AIS made a new session every time - and since the resident
    store caps at 8, a few re-uploads would evict the session the user was actually
    working in.

    Owner-scoped for the same reason the ledger hash is: two people must never dedup
    onto each other's session. sort_keys makes it stable across dict ordering.
    """
    body = json.dumps(ais_data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{user_id or ''}|{body}".encode("utf-8")).hexdigest()


def find_duplicate(ais_data: dict, user_id: Optional[str]) -> Optional[str]:
    """This owner's existing session for an identical AIS, if there is one."""
    if not user_id:
        return None
    try:
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT session_id FROM sessions
                WHERE data_hash = %s AND user_id = %s AND upload_type = 'tax_expert'
                """,
                (_ais_fingerprint(ais_data, user_id), user_id),
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        # A dedup miss costs a duplicate session; a raised exception costs the upload.
        logger.error(f"Tax dedup lookup failed: {e}")
        return None


def create_tax_session(ais_data: dict, flags: Optional[dict] = None) -> str:
    """Create a new tax session from parsed AIS data and persist it.

    The owner is the authenticated caller, full stop. It used to be derived from a
    header, then the identity, then finally the PAN printed inside the uploaded PDF -
    and that last fallback meant an anonymous upload was owned by whoever the document
    named, so the person who uploaded it could not read it back. That surfaced as a
    500 after a multi-second parse.
    """
    _ensure_loaded()
    user_id = identity.current_user_id()

    # Re-uploading the same AIS returns the existing session rather than making a new
    # one. The mutual-funds side has always short-circuited identical ledgers; without
    # the equivalent here, a few re-uploads would push the session the user is working
    # in out of the 8-slot resident cap.
    existing = find_duplicate(ais_data, user_id)
    if existing:
        logger.info("Duplicate AIS upload; reusing tax session %s", existing)
        return existing

    session_id = str(uuid.uuid4())

    with _SESSIONS_LOCK:
        _tax_sessions[session_id] = {
            "ais_data": ais_data,
            "deductions": {},
            "overrides": {},
            "user_id": user_id,
            "reconciliation_flags": flags or {},
            "_version": 0,
            "_last_access": time.time(),
        }
        _evict_locked()
    _persist_one(session_id)
    logger.info("Created tax session %s for user %s", session_id, user_id)
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
    owner = session.get("user_id") or None
    if not identity.owns_record(owner):
        logger.warning(
            "[AUTHZ] %s denied access to tax session owned by %s",
            identity.current_user_id(), owner,
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
    after the lock is released, so database I/O does not serialize every other reader.

    Deliberately does NOT re-insert the session into the store before writing. An
    earlier version did, to close a lost-update window (evicted between the read and
    the write, after which `_persist_one` finds nothing and silently skips). That guard
    was wrong on balance: it turned a concurrent delete into an **undelete** - an
    in-flight override racing `DELETE /accounts/{pan}` or `/auth/logout` re-persisted
    the whole AIS blob and the PAN back to the database, defeating a purge the user was told
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
            logger.info("[TAX] dropping write to %s: no longer live", session_id)  # pragma: no cover — defensive / hard to exercise in unit tests
            return False  # pragma: no cover — defensive / hard to exercise in unit tests
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
    """Delete a tax session from memory and the database."""
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
    """Drop every in-memory session (does not touch stored rows).

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


#: Default and maximum page size for tax history. The router needs the clamped value
#: too, to decide `has_more` - expressed once here so the two cannot drift.
HISTORY_PAGE_SIZE = 50
HISTORY_MAX_PAGE_SIZE = 200


def clamp_history_limit(limit: int) -> int:
    """The effective page size for a requested limit."""
    return max(1, min(int(limit), HISTORY_MAX_PAGE_SIZE))


def get_sessions_by_user(user_id: str, limit: int = HISTORY_PAGE_SIZE, offset: int = 0) -> list:
    """
    A page of the user's tax sessions, newest first.

    Queried from the registry, not from memory. The previous version scanned the
    resident dict - capped at 8 entries, and populated at cold start by the newest
    rows *across all users* - so a user's older sessions existed on disk and were
    simply invisible to their own history. Anything LRU-evicted vanished from the
    list too, despite still being restorable.

    Reads the denormalised `summary` rather than the payload, so listing does not
    decompress and parse every stored AIS document just to render headings.

    Paged. Each row still costs an AES-GCM decrypt of its metrics blob, so an
    unbounded query made this endpoint grow linearly slower for the life of the
    account - which matters more now that expired rows are no longer purged.
    idx_sessions_owner_type covers the ORDER BY, so the LIMIT is served from the
    index rather than by sorting the whole history.
    """
    if not user_id:
        return []
    limit = clamp_history_limit(limit)
    offset = max(0, int(offset))
    try:
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, created_at, updated_at, metrics
                FROM sessions
                WHERE user_id = %s AND upload_type = 'tax_expert'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            ).fetchall()
    except Exception as e:
        logger.error(f"Failed to list tax sessions: {e}")
        return []

    results = []
    for session_id, created_at, updated_at, metrics_blob in rows:
        try:
            summary = (crypto.decrypt_json(metrics_blob, aad=session_id) or {}).get("summary") or {}
        except crypto.DecryptionFailed:
            # One damaged row must not hide the rest of the history; it lists with
            # blank fields and a working timestamp.
            logger.exception("Cannot decrypt metrics for tax session %s", session_id)
            summary = {}
        results.append({
            "session_id": session_id,
            # Timestamps were absent from this response entirely, which is why the
            # accounts summary hardcoded created_at: None and no timeline could sort.
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "name": summary.get("name", ""),
            "fy": summary.get("fy", ""),
            "gross_salary": summary.get("gross_salary", 0),
        })
    return results


def evict_for_user(user_id: str) -> int:
    """
    Drop a user's sessions from memory, leaving the stored copies alone.

    This is what logout calls. It used to delete from disk as well, which made
    signing out destroy the user's tax history - tolerable when the filesystem was
    wiped on every deploy, and straightforward data loss now that it is not. An
    evicted session is restored by _rehydrate() on next access.
    """
    with _SESSIONS_LOCK:
        doomed = [
            sid for sid, data in _tax_sessions.items()
            if str(data.get("user_id") or "") == str(user_id)
        ]
        for sid in doomed:
            del _tax_sessions[sid]
    for sid in doomed:
        _drop_cached_computations(sid)
    return len(doomed)


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


# delete_all_for_pan() is gone. A purge deletes the `users` row, and sessions ->
# tax_payloads cascade from it, so there is nothing domain-specific left to
# coordinate. The accounts router had to call it separately only because the tax
# table was invisible to shared storage; evict_for_user() above covers the
# memory half.


def _clear_all_with_computations() -> int:
    """
    Empty the session store *and* the memoized computations that reference it.

    Both, together, because a computation outlives the session it was derived from:
    dropping only the sessions leaves the cached tax results resident until LRU
    eviction pushes them out. The two shared routers that cleared caches had to know
    to call both; registering them as one operation means the registry cannot be wired
    up half-right.
    """
    dropped = clear_all()
    from domains.tax_expert.computation_cache import clear_all as clear_computations
    clear_computations()
    return dropped


# Logout, account purge and history-delete used to name this module explicitly from
# three shared routers. They iterate the registry instead; see shared/session_stores.py.
session_stores.register(session_stores.SessionStore(
    name="tax_expert",
    evict_user=evict_for_user,
    forget_session=delete_tax_session,
    clear_all=_clear_all_with_computations,
))
