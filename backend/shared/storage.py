"""
shared/storage.py

Session persistence and transaction-ledger reconciliation.
==========================================================
Stores an uploaded CAS as one compressed payload row against a registry entry, and
fingerprints ledgers so re-uploading the same statement is idempotent.

Owner column
------------
Rows are keyed on `user_id` (a uuid this application issues), not on a PAN. PAN was
previously the login credential, the owner column and the CAS PDF password all at
once - and it is printed on documents, so "anyone who knows a PAN can read that
user's data" was the real posture rather than an edge case. It is now an attribute
on `profiles`.

Schema lives in migrations/, not here. DDL used to run at import time, which is
tolerable against a local file and not against a pooled network database: every
process start would race the same CREATE statements, and there is nowhere sensible
to put a failure.
"""

import json
import uuid
import zlib
import numpy as np
import pandas as pd
import hashlib
from io import StringIO
from typing import Optional, Dict, Any, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from shared import crypto, db

import logging
logger = logging.getLogger(__name__)


# Connection handling lives in shared/db.py - the one module that knows the engine.
# Re-exported because callers and tests refer to storage._connect.
_connect = db.connect


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
# any engine with no driver-specific types. zlib level 1 rather than the
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

    # psycopg hands back a memoryview for bytea. zlib accepts any buffer, but the
    # view keeps the whole result row alive until it is released, so materialise it.
    text = zlib.decompress(bytes(blob)).decode("utf-8")
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
        # A plain dict, not a JSON string: the column is jsonb, and psycopg adapts a
        # dict directly. Pre-serialising would store a jsonb *string* containing JSON.
        "meta": {"datetime_columns": datetime_columns},
        "byte_size": sum(len(b) for b in blobs.values()),
        **blobs,
    }


def decode_payload(row: Dict[str, Any]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Inverse of encode_payload. Returns (holdings, transactions, sips)."""
    # jsonb comes back already decoded; the str branch is for a caller passing the
    # encode_payload output straight through without a database round trip.
    meta = row.get("meta") or {}
    if isinstance(meta, (str, bytes)):
        try:
            meta = json.loads(meta)
        except (ValueError, TypeError):
            meta = {}
    datetime_columns = meta.get("datetime_columns") or {}

    return tuple(
        _decode_frame(row.get(name), datetime_columns.get(name))
        for name in _PAYLOAD_FRAMES
    )


def compute_ledger_hash(df_t: pd.DataFrame, user_id: Optional[str] = None) -> str:
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
       match across two accounts must never resolve to the other user's session.
       check_duplicate_upload() filters on user_id as well, so this is defence in
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
    full_ledger_string = f"{user_id or ''}|" + "|".join(row_strings.values.astype(str))
    return hashlib.sha256(full_ledger_string.encode('utf-8')).hexdigest()


def check_duplicate_upload(ledger_hash: str, user_id: Optional[str] = None) -> Optional[str]:
    """
    Returns this owner's existing session_id for an identical ledger, else None.

    Takes a precomputed hash rather than the frame: the caller needs the same hash
    for save_session() anyway, and computing it twice per upload meant running a
    row-wise `df.apply` over the whole ledger twice.

    `IS NOT DISTINCT FROM` rather than `=` because `=` never matches NULL. Sessions
    saved with no owner have user_id NULL, and those must still dedup against each
    other while never matching an owned row.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "SELECT session_id FROM sessions "
            "WHERE data_hash = %s AND user_id IS NOT DISTINCT FROM %s",
            (ledger_hash, user_id),
        )
        row = cursor.fetchone()
        return row[0] if row else None


class OwnerLookupFailed(Exception):
    """
    The owner of a session could not be determined.

    Deliberately distinct from "no such session". This used to be swallowed into
    `(False, None)`, which the caller read as "nothing to authorize" and then served
    the data - so the authorization check silently became a no-op whenever the database
    errored. "database is locked" is precisely the condition WAL and busy_timeout were
    added to handle, so that path was reachable rather than theoretical.

    Authorization must fail closed: callers turn this into a 503, never into access.
    """


def get_session_owner(session_id: str) -> Tuple[bool, Optional[str]]:
    """
    (session_exists, owner_user_id) for a session id.

    Returned as a pair so callers can tell "no such session" from "exists but
    unowned" - both are legitimate, and they must not be conflated when deciding
    whether to grant access.

    Raises OwnerLookupFailed if the question cannot be answered at all.
    """
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "SELECT user_id FROM sessions WHERE session_id = %s", (session_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return False, None
            return True, str(row[0]) if row[0] is not None else None
    except Exception as e:
        logger.error(f"[STORAGE ERROR] owner lookup failed for {session_id}: {e}")
        raise OwnerLookupFailed(str(e)) from e

def save_session(session_id: str, df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, statement_period: str = "", user_id: str = None, upload_type: str = 'mutual_funds', ledger_hash: Optional[str] = None) -> str:
    """
    Persist the frames and register the session against its owner.

    The registry row and the payload go in as **one transaction**. Under SQLite this
    was two, because DataFrame.to_sql committed its own - so the code had to write
    the registry first and hand-roll a compensating delete if the frames then failed,
    aiming for a recoverable partial state rather than none. Postgres removes the
    problem instead of mitigating it: either both rows land or neither does.

    Concurrent duplicate uploads are resolved by ON CONFLICT rather than by catching
    the unique violation. Catching it would not work here anyway - a failed statement
    aborts the whole Postgres transaction, so the follow-up SELECT on the same
    connection would itself error with "current transaction is aborted".
    """
    if ledger_hash is None:
        ledger_hash = compute_ledger_hash(df_t, user_id)

    # total_value is the user's net worth, so these are encrypted alongside the
    # payload rather than left as queryable doubles. Nothing filters or sorts on them
    # in SQL - the history timeline just displays them.
    metrics = {
        "total_value": float(df_h["Market Value"].sum()) if not df_h.empty and "Market Value" in df_h.columns else 0.0,
        "total_invested": float(df_h["Invested"].sum()) if not df_h.empty and "Invested" in df_h.columns else 0.0,
        "num_funds": len(df_h),
    }

    # Compressing and encrypting outside the transaction keeps ~300 ms of CPU-bound
    # work off the connection, which would otherwise hold it (and its share of a
    # small pool) idle.
    payload = encode_payload(df_h, df_t, df_s)
    # Bound to the session id: a ciphertext copied into another session's row fails
    # to decrypt rather than being served to the wrong owner.
    encrypted = {
        name: crypto.encrypt(payload[name], aad=session_id)
        for name in _PAYLOAD_FRAMES
    }
    encrypted_metrics = crypto.encrypt_json(metrics, aad=session_id)

    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, upload_type, data_hash,
                metrics, is_partial, statement_period
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (data_hash, user_id) WHERE data_hash IS NOT NULL
            DO NOTHING
            RETURNING session_id
            """,
            (
                session_id, user_id, upload_type, ledger_hash,
                encrypted_metrics, is_partial, statement_period,
            ),
        ).fetchone()

        if row is None:
            # An identical ledger for this owner landed between the caller's dedup
            # check and now. Uploading the same statement twice is idempotent, not a
            # 500, so adopt whichever write won.
            existing = conn.execute(
                "SELECT session_id FROM sessions "
                "WHERE data_hash = %s AND user_id IS NOT DISTINCT FROM %s",
                (ledger_hash, user_id),
            ).fetchone()
            if existing:
                logger.info(
                    "[STORAGE] duplicate upload; reusing session %s", existing[0]
                )
                return existing[0]
            # No conflicting row either - the insert was skipped for a reason we do
            # not model, and silently returning would strand the caller with an id
            # that does not exist.
            raise RuntimeError(f"session {session_id} was neither inserted nor found")

        conn.execute(
            """
            INSERT INTO session_payloads
                (session_id, codec, holdings, transactions, sips, meta, byte_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                codec = EXCLUDED.codec,
                holdings = EXCLUDED.holdings,
                transactions = EXCLUDED.transactions,
                sips = EXCLUDED.sips,
                meta = EXCLUDED.meta,
                byte_size = EXCLUDED.byte_size
            """,
            (
                session_id, payload["codec"], encrypted["holdings"],
                encrypted["transactions"], encrypted["sips"],
                # meta stays plaintext jsonb: it holds column names and datetime
                # units, which is schema rather than data.
                Jsonb(payload["meta"]), payload["byte_size"],
            ),
        )

    return session_id

def load_session(session_id: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]]:
    """
    Reconstruct a session's frames.

    One round trip for the payload, and one for the registry flag. The mf_* version
    took four, on a path that became routine rather than exceptional once the
    in-memory store gained a resident cap.
    """
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT s.is_partial, p.holdings, p.transactions, p.sips, p.meta
                FROM sessions s
                LEFT JOIN session_payloads p ON p.session_id = s.session_id
                WHERE s.session_id = %s
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        is_partial, holdings, transactions, sips, meta = row
        # A LEFT JOIN with no payload means the registry row exists but its frames do
        # not. Reported as empty rather than missing, so the 404 stays reserved for
        # "no such session".
        df_h, df_t, df_s = decode_payload({
            "holdings": crypto.decrypt(holdings, aad=session_id),
            "transactions": crypto.decrypt(transactions, aad=session_id),
            "sips": crypto.decrypt(sips, aad=session_id),
            "meta": meta,
        })
        return df_h, df_t, df_s, bool(is_partial)
    except crypto.DecryptionFailed:
        # Deliberately not folded into the generic handler below. Returning None here
        # renders as "session not found", which for a decryption failure would mean a
        # misconfigured key silently looks like an empty account across every session
        # at once. Re-raised so it surfaces as a 500 with the reason in the log.
        logger.exception(
            "[STORAGE] cannot decrypt session %s - check FINANCEBUDDY_ENCRYPTION_KEYS",
            session_id,
        )
        raise
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to load session {session_id}: {e}")
        return None


def get_history(user_id: str = None, upload_type: str = None) -> list:
    """
    The caller's uploads, newest first.

    Selects named columns rather than `*`, and flattens the encrypted `metrics` blob
    back into the same keys the timeline has always read - so the API contract is
    unchanged by the columns having moved inside encryption.
    """
    query = [
        "SELECT session_id, user_id, upload_type, created_at, updated_at,",
        "       is_partial, statement_period, metrics",
        "FROM sessions WHERE TRUE",
    ]
    params = []

    if user_id:
        query.append("AND user_id = %s")
        params.append(user_id)
    if upload_type:
        query.append("AND upload_type = %s")
        params.append(upload_type)
    query.append("ORDER BY created_at DESC")

    with _connect(row_factory=dict_row) as conn:
        rows = conn.execute(" ".join(query), params).fetchall()

    for row in rows:
        # user_id is a uuid; stringify so the response serialises without a custom
        # encoder.
        if row.get("user_id") is not None:
            row["user_id"] = str(row["user_id"])

        # Flatten metrics back to top-level keys. A row whose metrics will not
        # decrypt still lists - the timeline degrades to showing the date and the
        # restore button rather than the whole history vanishing, which is the more
        # useful failure when one row is damaged.
        blob = row.pop("metrics", None)
        try:
            metrics = crypto.decrypt_json(blob, aad=row["session_id"]) or {}
        except crypto.DecryptionFailed:
            logger.exception(
                "[STORAGE] cannot decrypt metrics for session %s", row["session_id"]
            )
            metrics = {}
        row["total_value"] = metrics.get("total_value")
        row["total_invested"] = metrics.get("total_invested")
        row["num_funds"] = metrics.get("num_funds")
        row["summary"] = metrics.get("summary") or {}
    return rows


def delete_session(session_id: str) -> bool:
    """
    Delete one session and everything hanging off it.

    session_payloads and tax_payloads declare ON DELETE CASCADE, so this is a single
    statement where the SQLite version had to name each child table and tolerate the
    ones that did not exist yet.
    """
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
        return True
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to delete session {session_id}: {e}")
        return False


def delete_all_for_user(user_id: str) -> int:
    """
    Delete every session belonging to a user, plus the account itself.

    The point of a purge request is that nothing identifying survives it, so this
    removes the `users` row too - `identities`, `profiles` and `sessions` all cascade
    from it, and `session_payloads` / `tax_payloads` cascade from those. One
    statement, where the SQLite version fanned out across five tables and used to
    loop `delete_session()` inside an open connection.
    """
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user_id,)
        ).fetchone()[0]
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))

    logger.info("[STORAGE] purged account %s and %d session(s)", user_id, count)
    return count
