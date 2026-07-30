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
import pandas as pd
import hashlib
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple

from shared.identity import mask_pan as _mask_pan

import logging
logger = logging.getLogger(__name__)


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "metadata.sqlite3")

os.makedirs(DATA_DIR, exist_ok=True)


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """
    Configure a connection for a concurrent web server.

    Under the default rollback journal a writer takes an EXCLUSIVE lock over the whole
    database, so a 20k-row CAS upload (~0.7 s, plus fsyncs) blocked every reader - and
    past the busy timeout those requests failed with "database is locked" as a 500.
    WAL lets readers proceed during a write, which is the single most important setting
    here.

    - journal_mode=WAL is persistent (stored in the file header), so setting it on any
      connection is enough; it is applied per-connection anyway because a fresh
      database needs it once and this is the cheapest place to guarantee it.
    - synchronous=NORMAL rather than FULL: FULL fsyncs on every commit, and on a
      deployment whose disk is wiped on restart that durability buys nothing.
    - busy_timeout gives a blocked writer time to wait rather than failing instantly.

    WAL needs shared-memory mmap on the database's filesystem. That is fine on a
    container's local disk but can fail on some network mounts, so a failure here is
    logged and tolerated rather than fatal.
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except sqlite3.DatabaseError as e:
        logger.warning("[STORAGE] could not apply pragmas (WAL unsupported here?): %s", e)


@contextmanager
def _connect():
    """
    A configured connection that is always closed.

    `with sqlite3.connect(...)` commits but does NOT close - it is a transaction
    context, not a resource context. On an exception path the traceback keeps the
    frame (and therefore the connection) alive for an indeterminate time, holding
    locks. This wrapper commits on success, rolls back on failure, and closes either
    way.
    """
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    _apply_pragmas(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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

        _ensure_mf_indexes(conn)


# The mf_* tables are created implicitly by DataFrame.to_sql, so they may not exist
# when _init_db runs on a fresh database. Indexes are therefore ensured in two places:
# here (for databases where the tables already exist) and again after to_sql in
# save_session (for the first upload). CREATE INDEX IF NOT EXISTS makes both idempotent.
_MF_INDEXED_TABLES = ("mf_holdings", "mf_transactions", "mf_sips")


def _ensure_mf_indexes(conn: sqlite3.Connection) -> None:
    """
    Index the mf_* tables on session_id.

    Every load_session() runs `SELECT * FROM mf_* WHERE session_id=?`, and these tables
    hold *every* session's rows until the 24h purge - so without an index each
    rehydration is three full table scans over unrelated sessions' data. This became a
    hot path when the in-memory session store gained a resident cap, which makes
    rehydration routine rather than exceptional.
    """
    for table in _MF_INDEXED_TABLES:
        try:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_session_id ON {table}(session_id)"
            )
        except sqlite3.OperationalError:
            pass  # table not created yet - save_session will index it after to_sql


_init_db()

def _quote_ident(name: str) -> str:
    """
    Escape a SQL identifier for use inside double quotes.

    Table and column names here are not constants: column names come from the CAS/AIS
    parser and therefore from the uploaded document. Doubling embedded quotes is the
    SQLite-correct escape.
    """
    return str(name).replace('"', '""')


def _align_frame_to_table(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Reconcile a frame's columns with an existing table's before `to_sql`.

    The mf_* tables have no explicit DDL - their schema is frozen from whatever
    columns the *first* upload happened to have. So the moment the parser gains,
    renames or drops a field, `to_sql(if_exists="append")` fails with
    `DatabaseError: Execution failed`, which says nothing about the real cause. The
    live schema has already drifted once: `mf_holdings` carries a "CAS NAV" column
    the current parser no longer emits, and has no "Type" column.

    On ephemeral disk this self-heals (the table is recreated each deploy), which is
    exactly why it stayed hidden - attach a persistent volume and every upload
    starts failing after any parser change.

    Handling, in the additive direction, so no data is silently discarded:
      - a column the frame has and the table lacks -> ALTER TABLE ADD COLUMN
      - a column the table has and the frame lacks -> filled with NULL
    Returns the frame reordered to the table's column order.
    """
    existing = [row[1] for row in conn.execute(f'PRAGMA table_info("{_quote_ident(table)}")').fetchall()]
    if not existing:
        return df  # table does not exist yet; to_sql will create it from this frame

    for column in df.columns:
        if column in existing:
            continue
        # Keep the new field rather than dropping it on the floor. SQLite infers no
        # type here, which is fine: it is dynamically typed per value.
        #
        # The identifier is escaped because column names come from the CAS/AIS parser,
        # i.e. they are document-controlled. A name containing a double quote used to
        # produce `OperationalError: unrecognized token` - an unhandled 500 on upload -
        # and was only prevented from being worse by sqlite3's one-statement-per-execute
        # rule, which is luck rather than a guard.
        conn.execute(f'ALTER TABLE "{_quote_ident(table)}" ADD COLUMN "{_quote_ident(column)}"')
        existing.append(column)
        logger.info("[STORAGE] added column %r to %s (parser drift)", column, table)

    aligned = df.copy()
    for column in existing:
        if column not in aligned.columns:
            aligned[column] = None

    return aligned[existing]


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

    # 3. Save DataFrames to SQLite.
    #
    # If this fails, the registry row from step 2 must be removed. Leaving it would be
    # worse than the orphan rows the old ordering produced: the row carries the real
    # data_hash, so check_duplicate_upload would match it and every retry of the same
    # CAS would be deduped into the broken empty session until the 24h sweep - a
    # permanently bricked upload path rather than a retryable failure. load_session
    # also returns empty frames rather than None for such a row, so it would surface as
    # a portfolio with no holdings instead of a clean 404.
    try:
        with _connect() as conn:
            for frame, table in ((df_h, "mf_holdings"), (df_t, "mf_transactions"), (df_s, "mf_sips")):
                if frame.empty:
                    continue
                frame_copy = frame.copy()
                frame_copy['session_id'] = session_id
                frame_copy = _align_frame_to_table(conn, table, frame_copy)
                frame_copy.to_sql(table, conn, if_exists="append", index=False)

            # to_sql has just created any missing tables, so this is where a fresh
            # database actually gets its session_id indexes. _init_db cannot do it:
            # the mf_* tables do not exist yet at import time.
            _ensure_mf_indexes(conn)
    except Exception:
        logger.exception("[STORAGE] frame write failed for %s; rolling back registry row", session_id)
        try:
            delete_session(session_id)
        except Exception:
            logger.exception("[STORAGE] could not roll back registry row for %s", session_id)
        raise

        # to_sql has just created any missing tables, so this is where a fresh
        # database actually gets its session_id indexes.
        _ensure_mf_indexes(conn)
        conn.commit()

    return session_id

def load_session(session_id: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]]:
    """
    Reconstructs the portfolio from SQLite using the session_id.
    """
    try:
        with _connect() as conn:
            # Check if session exists
            cursor = conn.execute("SELECT is_partial FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            is_partial = bool(row[0])
            
            # Read dataframes (parameterized — session_id is untrusted input)
            try:
                df_h = pd.read_sql("SELECT * FROM mf_holdings WHERE session_id=?", conn, params=(session_id,))
                df_h.drop(columns=['session_id'], inplace=True, errors='ignore')
            except Exception:
                df_h = pd.DataFrame()

            try:
                df_t = pd.read_sql("SELECT * FROM mf_transactions WHERE session_id=?", conn, params=(session_id,))
                df_t.drop(columns=['session_id'], inplace=True, errors='ignore')
                # SQLite has no native datetime type — to_sql wrote "Date" as ISO (year-first)
                # strings, so it comes back as plain object dtype, not datetime64. Every
                # downstream consumer (FIFO lots, XIRR, rolling returns) expects datetime64;
                # restore it here once instead of forcing every caller to defend against it.
                if not df_t.empty and "Date" in df_t.columns and not pd.api.types.is_datetime64_any_dtype(df_t["Date"]):
                    df_t["Date"] = pd.to_datetime(df_t["Date"])
            except Exception:
                df_t = pd.DataFrame()

            try:
                df_s = pd.read_sql("SELECT * FROM mf_sips WHERE session_id=?", conn, params=(session_id,))
                df_s.drop(columns=['session_id'], inplace=True, errors='ignore')
                # Same restore as df_t above. mf_sips.Date is stored as the identical
                # ISO string, but only df_t was being converted back - so downstream
                # code got object dtype and papered over it with
                # `pd.to_datetime(..., dayfirst=True)`, which misparses a
                # "YYYY-MM-DD HH:MM:SS" string the moment the day is ambiguous.
                if not df_s.empty and "Date" in df_s.columns and not pd.api.types.is_datetime64_any_dtype(df_s["Date"]):
                    df_s["Date"] = pd.to_datetime(df_s["Date"])
            except Exception:
                df_s = pd.DataFrame()
                
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
            try:
                conn.execute("DELETE FROM mf_holdings WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM mf_transactions WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM mf_sips WHERE session_id = ?", (session_id,))
            except sqlite3.OperationalError:
                pass # Tables might not exist yet
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
