"""
core/storage.py

Data Lake Persistence & Transaction Ledger Reconciliation Engine
================================================================
Manages robust disk-level storage of CAS uploaded DataFrames using a unified SQLite database,
mapped against an SQLite metadata registry. Includes a deterministic row-level hashing
engine to prevent duplicate snapshots and allow semantic ledger reconciliation.
"""

import os
import json
import sqlite3
import uuid
import zlib
import numpy as np
import pandas as pd
import hashlib
from io import StringIO
from typing import Optional, Dict, Any, Tuple

from shared import db
from shared.identity import mask_pan as _mask_pan

import logging
logger = logging.getLogger(__name__)


# Connection management, the database location and the pragmas all live in shared/db.py
# now - it is the one place that knows which engine this is, so the Postgres migration
# is a change there rather than in every module that persists something.
#
# Re-exported because callers (and tests) refer to storage._connect / storage.DATA_DIR.
# _connect is a genuine alias, not a copy: rebinding db.DB_PATH redirects it, since
# db.connect() reads the path at call time.
_connect = db.connect
DATA_DIR = db.DATA_DIR


def _init_db():
    """Initializes the SQLite metadata registry and runs migrations."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                pan_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_value REAL,
                total_invested REAL,
                num_funds INTEGER,
                is_partial BOOLEAN
            )
        """)
        # Schema Migration: Add pan_id to sessions if missing
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN pan_id TEXT")
        except sqlite3.OperationalError:
            pass # Column already exists
            
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN upload_type TEXT DEFAULT 'mutual_funds'")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN statement_period TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        # The GC sweep scans for sessions older than 24h on every pass.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at)")

        # Every PAN-scoped read was a full scan of a table holding every session in
        # the system: get_history (the /history timeline), the accounts summary, and
        # the purge path. This covers the filter AND the sort, so get_history becomes a
        # SEARCH with no temp B-tree instead of a SCAN.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_pan_type "
            "ON sessions(pan_id, upload_type, created_at DESC)"
        )

        # The dedup lookup is now scoped by (data_hash, pan_id). data_hash already has
        # a UNIQUE index, which serves it.

        # One compressed blob per session, replacing the three implicit mf_* tables.
        # session_id is the PRIMARY KEY, so the lookup load_session() performs is
        # already indexed - the mf_* tables each needed an explicit index for the
        # same query, added in two places because to_sql created them lazily.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_payloads (
                session_id TEXT PRIMARY KEY,
                codec TEXT NOT NULL,
                holdings BLOB,
                transactions BLOB,
                sips BLOB,
                meta TEXT NOT NULL DEFAULT '{}',
                byte_size INTEGER
            )
        """)

        _ensure_mf_indexes(conn)


# LEGACY - the implicitly-created tables that `session_payloads` replaced. Nothing
# writes them any more; they are still read and deleted so a database predating the
# payload codec does not report its existing sessions as empty or leak rows past a
# purge. Remove along with _load_legacy_frames.
_MF_INDEXED_TABLES = ("mf_holdings", "mf_transactions", "mf_sips")


def _ensure_mf_indexes(conn: sqlite3.Connection) -> None:
    """
    Index the legacy mf_* tables on session_id, where they exist.

    Only matters for a database written before the payload codec: the legacy read
    path still runs `SELECT * FROM mf_* WHERE session_id=?`, and those tables hold
    every session's rows, so without the index each such read is a full scan over
    unrelated sessions' data.
    """
    for table in _MF_INDEXED_TABLES:
        try:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_session_id ON {table}(session_id)"
            )
        except sqlite3.OperationalError:
            pass  # table does not exist, i.e. this database never used the old format


_init_db()


# ── Session payload codec ─────────────────────────────────────────────────────
#
# A session's three frames are stored as ONE compressed blob rather than as rows in
# three implicitly-created tables. This replaced `DataFrame.to_sql`, which had three
# problems that all trace back to the mf_* tables having no explicit DDL:
#
#   - Schema was frozen from whatever columns the *first* upload happened to have, so
#     any parser change made `to_sql(if_exists="append")` fail on every subsequent
#     upload. The previous mitigation issued `ALTER TABLE ADD COLUMN` at runtime using
#     *document-controlled* identifiers, which is not a thing to do to a database.
#   - Rehydration cost four round trips (registry + three frame reads). It is now one.
#   - Postgres will not tolerate any of it. A strictly-typed database cannot have its
#     schema mutated by the contents of an uploaded PDF.
#
# The format is deliberately boring - JSON, so it is inspectable and portable across
# both SQLite and Postgres with no driver-specific types. zlib level 1 rather than the
# default 6: on ~0.1 shared vCPU the extra CPU of higher levels costs more than the
# bytes it saves, and level 1 still gets roughly 10x on this data. Compressing in the
# application rather than relying on Postgres TOAST also saves the *wire* bytes, since
# TOAST decompresses server-side before sending.
_PAYLOAD_CODEC = "zlib-json-split-v1"

_PAYLOAD_FRAMES = ("holdings", "transactions", "sips")

# Whitelisted so a corrupted or hand-edited `meta` cannot reach astype() with an
# arbitrary string; anything unrecognised falls back to the ISO parse.
_EPOCH_UNITS = frozenset(("s", "ms", "us", "ns"))


def _datetime_unit(dtype) -> str:
    """
    The resolution of a datetime dtype: 's', 'ms', 'us' or 'ns'.

    Two accessors are needed because two kinds of dtype reach this. pandas extension
    dtypes (DatetimeTZDtype) expose `.unit`; a tz-naive column is a plain numpy dtype
    which does not, and only answers to np.datetime_data. Relying on `.unit` alone
    silently returned the "ns" default for every naive column - which is exactly the
    case that matters, and on pandas 3 those columns are datetime64[us], so every
    timestamp came back divided by 1000.
    """
    unit = getattr(dtype, "unit", None)
    if unit:
        return unit
    try:
        return np.datetime_data(dtype)[0]
    except (TypeError, ValueError):
        return "ns"


def _encode_frame(df: Optional[pd.DataFrame]) -> Tuple[bytes, Dict[str, str]]:
    """
    Compress one frame, returning (blob, {datetime_column: restore_mode}).

    Two decisions here are performance-driven, both measured on a 20k-row ledger:

    Each frame is its own self-contained JSON document rather than a member of a
    larger one. Nesting them meant `to_json` -> `json.loads` -> `json.dumps`, which
    serializes every row three times - 2.5 s, or roughly 10-20 s on the deployment's
    ~0.1 shared vCPU. Standalone frames keep both directions on pandas' C JSON paths
    and never materialise rows as Python objects.

    Naive datetimes are written as integer epoch counts, not ISO strings.
    `date_format="iso"` spent 334 ms of a 564 ms encode formatting one 20k-row Date
    column, where `astype("int64")` is free - datetime64 is int64 underneath, so it is
    a view rather than a conversion - and reads back in 1 ms instead of 25 ms. It is
    also exact, where an ISO round trip is a lossy format-then-reparse.

    The column's *unit* is recorded alongside it and must be, because it is not
    always nanoseconds: pandas has supported non-nanosecond resolution since 2.0, and
    on pandas 3 `pd.to_datetime` yields datetime64[us]. Restoring a microsecond
    column as datetime64[ns] silently divides every timestamp by 1000 - 2023 becomes
    1970 - and nothing downstream would flag it as anything but bad data.

    Timezone-aware columns keep the ISO path: their integer value is UTC, so the
    round trip would drop the zone. No parser emits them today, but the fallback
    costs nothing and makes the wrong outcome unreachable rather than unlikely.

    orient="split" keeps column order and emits rows as lists, which is much smaller
    than orient="records" repeating every key on every row.
    """
    if df is None:
        df = pd.DataFrame()

    datetime_columns: Dict[str, str] = {}
    encodable = df
    epoch_columns = []
    for column in df.columns:
        dtype = df[column].dtype
        if not pd.api.types.is_datetime64_any_dtype(dtype):
            continue
        if getattr(dtype, "tz", None) is not None:
            datetime_columns[str(column)] = "iso"
            continue
        datetime_columns[str(column)] = f"epoch:{_datetime_unit(dtype)}"
        epoch_columns.append(column)

    if epoch_columns:
        # Shallow copy: only the rewritten columns are replaced, the rest are shared.
        encodable = df.copy(deep=False)
        for column in epoch_columns:
            # NaT becomes iNaT (INT64_MIN) and converts straight back to NaT, so this
            # emits no nulls at all.
            encodable[column] = df[column].astype("int64")

    encoded = encodable.to_json(orient="split", date_format="iso", index=False)
    return zlib.compress(encoded.encode("utf-8"), 1), datetime_columns


def _decode_frame(blob: Optional[bytes], datetime_columns: Optional[Dict[str, str]]) -> pd.DataFrame:
    """
    Inverse of _encode_frame.

    Datetime columns are restored from the recorded names rather than inferred. The
    old to_sql path wrote ISO strings (SQLite had no datetime type) and restored them
    with a hardcoded check for a column literally named "Date" - written for
    transactions, and only later duplicated for SIPs after the missing conversion
    there was found to misparse ambiguous days via dayfirst=True. Recording the
    columns makes it general instead of a list of names someone must remember to
    extend.

    Inference is switched off explicitly: left on, read_json would guess at dates and
    re-type axes, which is the ambiguity this exists to remove.
    """
    if blob is None:
        return pd.DataFrame()

    text = zlib.decompress(blob).decode("utf-8")
    df = pd.read_json(
        StringIO(text), orient="split", convert_dates=False, convert_axes=False
    )
    for column, mode in (datetime_columns or {}).items():
        if column not in df.columns:
            continue
        unit = mode.split(":", 1)[1] if mode.startswith("epoch:") else None
        if unit in _EPOCH_UNITS:
            df[column] = df[column].astype("int64").astype(f"datetime64[{unit}]")
        else:
            # errors="coerce": one unparseable cell should become NaT rather than
            # failing the whole rehydration and 404-ing a session that exists.
            df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def encode_payload(df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame) -> Dict[str, Any]:
    """
    Serialize a session's three frames.

    Returns the column values for one `session_payloads` row - three blobs plus a
    small metadata document. Still a single row and a single round trip; the split is
    only so each frame stays a standalone JSON document (see _encode_frame).
    """
    blobs = {}
    datetime_columns = {}
    for name, frame in zip(_PAYLOAD_FRAMES, (df_h, df_t, df_s)):
        blobs[name], datetime_columns[name] = _encode_frame(frame)

    return {
        "codec": _PAYLOAD_CODEC,
        "meta": json.dumps({"datetime_columns": datetime_columns}, separators=(",", ":")),
        "byte_size": sum(len(b) for b in blobs.values()),
        **blobs,
    }


def decode_payload(row: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Inverse of encode_payload. Returns (holdings, transactions, sips)."""
    try:
        meta = json.loads(row.get("meta") or "{}")
    except (ValueError, TypeError):
        meta = {}
    datetime_columns = meta.get("datetime_columns") or {}

    return tuple(
        _decode_frame(row.get(name), datetime_columns.get(name))
        for name in _PAYLOAD_FRAMES
    )


def compute_ledger_hash(df_t: pd.DataFrame, pan_id: Optional[str] = None) -> str:
    """
    Deterministic SHA-256 fingerprint of a transaction ledger, scoped to its owner.

    The fingerprint exists to skip re-processing a CAS the same user already
    uploaded. Two properties are load-bearing for that to be safe:

    1. An empty ledger gets a **unique** value, not a shared constant. It
       previously returned the literal string "empty_ledger", so every
       transaction-less CAS (a Summary statement carries holdings with no
       transaction rows) collided on one data_hash - and because the dedup lookup
       returned a session_id, the second user to upload one was handed the first
       user's portfolio. An unowned unique value means an empty ledger simply
       never dedups, which is the correct behaviour: there is nothing to compare.

    2. The owner is part of the hash. Dedup is a per-user optimisation; a hash
       match across two PANs must never resolve to the other user's session.
       check_duplicate_upload() filters on pan_id as well, so this is defence in
       depth rather than the only guard.
    """
    if df_t.empty:
        return f"empty_ledger_{uuid.uuid4().hex}"

    # Sort transactions chronologically to ensure deterministic ordering
    sorted_df = df_t.sort_values(by=["Date", "Fund", "Type"]).copy()

    # Create a string representation of the critical columns for each row
    # We round floats to prevent precision differences from failing the hash
    row_strings = sorted_df.apply(
        lambda row: f"{row['Date']}_{row.get('Fund', '')}_{row.get('Type', '')}_{round(row.get('Units', 0.0), 3)}_{round(row.get('Amount', 0.0), 2)}",
        axis=1
    )

    # Concatenate all rows into a single giant string and hash it, prefixed with the
    # owner so identical ledgers under different PANs produce different fingerprints.
    full_ledger_string = f"{pan_id or ''}|" + "|".join(row_strings.values.astype(str))
    return hashlib.sha256(full_ledger_string.encode('utf-8')).hexdigest()


def check_duplicate_upload(ledger_hash: str, pan_id: Optional[str] = None) -> Optional[str]:
    """
    Returns this owner's existing session_id for an identical ledger, else None.

    Takes a precomputed hash rather than the frame: the caller needs the same hash
    for save_session() anyway, and computing it twice per upload meant running a
    row-wise `df.apply` over the whole ledger twice.

    `pan_id IS ?` rather than `= ?` because SQLite's `=` never matches NULL, and
    sessions uploaded without a PAN header have pan_id NULL - those must still
    dedup against each other, and must not match a PAN-owned row.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT session_id FROM sessions WHERE data_hash = ? AND pan_id IS ?",
            (ledger_hash, pan_id),
        )
        row = cursor.fetchone()
        return row[0] if row else None


class OwnerLookupFailed(Exception):
    """
    The owner of a session could not be determined.

    Deliberately distinct from "no such session". This used to be swallowed into
    `(False, None)`, which the caller read as "nothing to authorize" and then served
    the data - so the authorization check silently became a no-op whenever SQLite
    errored. "database is locked" is precisely the condition WAL and busy_timeout were
    added to handle, so that path was reachable rather than theoretical.

    Authorization must fail closed: callers turn this into a 503, never into access.
    """


def get_session_owner(session_id: str) -> Tuple[bool, Optional[str]]:
    """
    (session_exists, owner_pan) for a session id.

    Returned as a pair so callers can tell "no such session" from "exists but
    unowned" - both are legitimate, and they must not be conflated when deciding
    whether to grant access.

    Raises OwnerLookupFailed if the question cannot be answered at all.
    """
    try:
        with _connect() as conn:
            cursor = conn.execute("SELECT pan_id FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row is None:
                return False, None
            return True, row[0]
    except Exception as e:
        logger.error(f"[STORAGE ERROR] owner lookup failed for {session_id}: {e}")
        raise OwnerLookupFailed(str(e)) from e

def save_session(session_id: str, df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, statement_period: str = "", pan_id: str = None, upload_type: str = 'mutual_funds', ledger_hash: Optional[str] = None) -> str:
    """
    Persists the dataframes to SQLite and registers the session, tied to a PAN.

    Write order is deliberate: the `sessions` registry row goes in **first**, then
    the mf_* frames. It used to be the other way round, in two separate
    transactions - so a failure between them (the UNIQUE constraint on data_hash
    is reachable via a concurrent duplicate upload) left mf_* rows committed under
    a session_id that appeared in no registry row. The 24h sweeper only finds rows
    *via* `sessions`, so those were unreachable and immortal.

    Registry-first inverts the failure mode: a later failure leaves a registry row
    whose frames are missing, which load_session() reports as empty and the
    sweeper purges normally. Full atomicity is not available here because
    DataFrame.to_sql commits its own transaction, so the goal is a *recoverable*
    partial state rather than none.
    """
    if ledger_hash is None:
        ledger_hash = compute_ledger_hash(df_t, pan_id)

    # 1. Extract quick metrics for the registry
    total_value = float(df_h["Market Value"].sum()) if not df_h.empty and "Market Value" in df_h.columns else 0.0
    total_invested = float(df_h["Invested"].sum()) if not df_h.empty and "Invested" in df_h.columns else 0.0
    num_funds = len(df_h)

    # 2. Claim the session id in the registry before writing any frame rows.
    with _connect() as conn:
        try:
            conn.execute("""
                INSERT INTO sessions (session_id, data_hash, total_value, total_invested, num_funds, is_partial, statement_period, pan_id, upload_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, ledger_hash, total_value, total_invested, num_funds, is_partial, statement_period, pan_id, upload_type))
            conn.commit()
        except sqlite3.IntegrityError:
            # data_hash is UNIQUE, so this means an identical ledger for this owner
            # landed between the caller's dedup check and now. Uploading the same
            # statement twice should be idempotent, not a 500, so adopt the winner.
            conn.rollback()
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE data_hash = ? AND pan_id IS ?",
                (ledger_hash, pan_id),
            ).fetchone()
            if existing:
                logger.info(
                    "[STORAGE] concurrent duplicate upload for %s; reusing session %s",
                    _mask_pan(pan_id), existing[0],
                )
                return existing[0]
            raise

    # 3. Save the frames as one compressed payload row.
    #
    # If this fails, the registry row from step 2 must be removed. Leaving it would be
    # worse than the orphan rows the old ordering produced: the row carries the real
    # data_hash, so check_duplicate_upload would match it and every retry of the same
    # CAS would be deduped into the broken empty session until the 24h sweep - a
    # permanently bricked upload path rather than a retryable failure. load_session
    # also returns empty frames rather than None for such a row, so it would surface as
    # a portfolio with no holdings instead of a clean 404.
    #
    # Unlike the previous to_sql version this is a single INSERT, so the write is
    # genuinely atomic rather than three self-committing statements that could leave a
    # session with holdings but no transactions.
    try:
        payload = encode_payload(df_h, df_t, df_s)
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_payloads "
                "(session_id, codec, holdings, transactions, sips, meta, byte_size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, payload["codec"], payload["holdings"],
                    payload["transactions"], payload["sips"],
                    payload["meta"], payload["byte_size"],
                ),
            )
    except Exception:
        logger.exception("[STORAGE] payload write failed for %s; rolling back registry row", session_id)
        try:
            delete_session(session_id)
        except Exception:
            logger.exception("[STORAGE] could not roll back registry row for %s", session_id)
        raise

    return session_id

def _load_legacy_frames(conn: sqlite3.Connection, session_id: str):
    """
    Read a session written before the payload codec, from the old mf_* tables.

    LEGACY - remove once no database predating `session_payloads` is in use. In
    production this is already unreachable (the disk is wiped on every deploy, and
    nothing survives the 24h sweep), but a developer's local database predates the
    change and would otherwise report every existing session as empty.
    """
    frames = []
    for table in _MF_INDEXED_TABLES:
        try:
            df = pd.read_sql(f"SELECT * FROM {table} WHERE session_id=?", conn, params=(session_id,))
            df.drop(columns=["session_id"], inplace=True, errors="ignore")
            # These tables stored datetimes as ISO strings, so restore the dtype every
            # downstream consumer (FIFO lots, XIRR, rolling returns) expects.
            if not df.empty and "Date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Date"]):
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        except Exception:
            df = pd.DataFrame()
        frames.append(df)
    return tuple(frames)


def load_session(session_id: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]]:
    """
    Reconstructs the portfolio from SQLite using the session_id.

    One round trip for the payload where the previous version took three, on a path
    that became routine rather than exceptional once the in-memory store gained a
    resident cap.
    """
    try:
        with _connect() as conn:
            cursor = conn.execute("SELECT is_partial FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            is_partial = bool(row[0])

            payload_row = conn.execute(
                "SELECT holdings, transactions, sips, meta FROM session_payloads "
                "WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if payload_row is None:
                df_h, df_t, df_s = _load_legacy_frames(conn, session_id)
            else:
                df_h, df_t, df_s = decode_payload({
                    "holdings": payload_row[0],
                    "transactions": payload_row[1],
                    "sips": payload_row[2],
                    "meta": payload_row[3],
                })

        return df_h, df_t, df_s, is_partial
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to load session {session_id}: {str(e)}")
        return None

def get_history(pan_id: str = None, upload_type: str = None) -> list:
    """
    Returns a chronological list of all uploaded CAS sessions for a given PAN and upload_type.
    """
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        
        if pan_id:
            query += " AND pan_id = ?"
            params.append(pan_id)
            
        if upload_type:
            query += " AND upload_type = ?"
            params.append(upload_type)
            
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def delete_session(session_id: str) -> bool:
    """
    Deletes a session from the SQLite registry and its associated dataframes.
    """
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM session_payloads WHERE session_id = ?", (session_id,))
            # LEGACY - see _load_legacy_frames. Rows only exist in databases that
            # predate the payload codec, but a purge must not leave them behind.
            for table in _MF_INDEXED_TABLES:
                try:
                    conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
                except sqlite3.OperationalError:
                    pass  # table never created
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to delete session {session_id}: {str(e)}")
        return False

def delete_all_for_pan(pan_id: str) -> int:
    """
    Deletes every session associated with a PAN, plus the PAN's own user row.
    Returns the number of sessions deleted.

    Two things were wrong here. It looped `delete_session(sid)` while holding an
    open connection, so N sessions meant 1 + 4N statements across N nested
    connections with N commits - the shape that produces `database is locked` the
    moment WAL and any concurrency are in play. And it left the `users` row behind,
    so a PAN that asked to have all its data "permanently deleted" stayed in the
    database forever. Both are fixed by collecting the ids, then issuing one
    executemany batch per table in a single transaction.
    """
    with _connect() as conn:
        session_ids = [
            row[0] for row in conn.execute(
                "SELECT session_id FROM sessions WHERE pan_id = ?", (pan_id,)
            ).fetchall()
        ]

        if session_ids:
            rows = [(sid,) for sid in session_ids]
            conn.executemany("DELETE FROM session_payloads WHERE session_id = ?", rows)
            # LEGACY - see _load_legacy_frames.
            for table in _MF_INDEXED_TABLES:
                try:
                    conn.executemany(f"DELETE FROM {table} WHERE session_id = ?", rows)
                except sqlite3.OperationalError:
                    pass  # table not created yet
            conn.executemany("DELETE FROM sessions WHERE session_id = ?", rows)

        # The point of a purge request is that nothing identifying survives it.
        conn.execute("DELETE FROM users WHERE pan_id = ?", (pan_id,))
        conn.commit()

    logger.info("[STORAGE] purged %d sessions for %s", len(session_ids), _mask_pan(pan_id))
    return len(session_ids)
