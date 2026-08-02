"""
domains/budget/sessions.py - persistence and authorization for budget statements.

Authorization
-------------
get_budget_session() used to be `SELECT ... FROM budget_payloads WHERE session_id = %s`
with no owner predicate, reachable from three analytics routes with a caller-supplied
id. Any authenticated user who knew (or guessed) another user's session id got their
decrypted bank statement back. That is the same bug equity carried until bb5ab023, and
the fix here is deliberately the same shape as the one in domains/equity/sessions.py so
the two read alike.

The `identity.owns_record(user_id)` calls that were dotted around the routers did
nothing: they passed the *caller's own* id, so the comparison was caller-to-caller and
always true, and the return value was discarded. Ownership is enforced here instead -
at the data-access boundary, where it cannot be forgotten by a route added later. This
is the reasoning already written down in shared/identity.py.

Denial is 404, not 403, for the reason equity gives: a 403 confirms the session exists,
which is exactly what an id-guessing caller wants to learn.

Dedup
-----
`data_hash` was set to the session_id, which is a fresh uuid per upload. The unique
index `uq_sessions_hash_owner` can never fire against a value that is unique by
construction, so re-uploading the same statement always created another session. The
compensation was a `drop_duplicates` at read time - which silently deleted *genuine*
repeat transactions: two identical coffees on the same day at the same merchant became
one. Both halves are fixed here: a real content hash on write, and a read-time overlap
merge that preserves multiplicity.

Transactions and CPU
--------------------
db.connect() is one transaction for the whole `with` block and the pool holds six
connections. Compressing, encrypting and categorizing inside that block charges
hundreds of milliseconds of CPU to a connection somebody else is waiting for - and
reapply_rules_to_all_sessions additionally called categorize_transactions(), which
opened *two more* connections, from inside a block already holding one. Six concurrent
callers deadlocked until the 10s checkout timeout. Every function here now reads in one
short transaction, computes outside it, and writes in another.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import uuid
import zlib
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import HTTPException

from shared import crypto, db, identity, storage

logger = logging.getLogger(__name__)

# One message for "no such session" and "not yours". They must be indistinguishable or
# the difference itself is the leak.
_NOT_FOUND_DETAIL = "Session not found or you do not have access to it."

# Columns that identify the same real-world transaction across two overlapping
# statements. txn_id is deliberately absent: it is minted per parse, so it differs
# between two uploads of the same statement.
_IDENTITY_COLUMNS = ["date", "description", "amount", "type", "source_bank", "account_type"]


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def _compress_frame(df: pd.DataFrame) -> bytes:
    if df is None or df.empty:
        return b""
    df_copy = df.copy()
    if "date" in df_copy.columns:
        df_copy["date"] = df_copy["date"].astype(str)
    return zlib.compress(df_copy.to_json(orient="records").encode("utf-8"))


def _decompress_frame(b: Optional[bytes]) -> pd.DataFrame:
    if not b:
        return pd.DataFrame()
    json_str = zlib.decompress(b).decode("utf-8")
    df = pd.read_json(io.StringIO(json_str), orient="records")
    if not df.empty and "date" in df.columns:
        df["date"] = _normalise_dates(df["date"])
    return df


def _normalise_dates(series: pd.Series) -> pd.Series:
    """ISO date strings, falling back to the original text for anything unparseable."""
    try:
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed.dt.strftime("%Y-%m-%d").fillna(series.astype(str))
    except Exception:
        return series.astype(str)


def _budget_ledger_hash(df: pd.DataFrame, user_id: Optional[str]) -> str:
    """
    Content fingerprint of a parsed statement, salted with the owner.

    Order-independent (row hashes are summed) because two exports of the same statement
    are not guaranteed to be in the same order. The owner is in the pre-image so an
    identical statement uploaded by two people cannot resolve to the other's session -
    check_duplicate_upload also filters on user_id, so this is defence in depth.

    Mirrors _equity_ledger_hash in domains/equity/sessions.py.
    """
    if df is None or df.empty:
        # Never a shared constant: two different users' empty uploads must not dedup
        # onto one another. Same reasoning as storage.compute_ledger_hash.
        return f"budget_empty_{uuid.uuid4().hex}"

    cols = sorted(c for c in df.columns if c != "txn_id")
    subset = df[cols]
    try:
        digest = int(pd.util.hash_pandas_object(subset, index=False).sum())
    except Exception:
        rows = sorted(
            hashlib.sha256("\x1f".join(map(repr, row)).encode("utf-8")).hexdigest()
            for row in subset.itertuples(index=False, name=None)
        )
        digest = int(hashlib.sha256("|".join(rows).encode("utf-8")).hexdigest()[:16], 16)

    material = f"budget|{user_id or ''}|{len(subset)}x{len(cols)}:{digest & 0xFFFFFFFFFFFFFFFF:x}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

def _deny(session_id: str, owner: Optional[str]) -> HTTPException:
    caller = identity.current_user_id()
    logger.warning(
        "[AUTHZ] caller=%s denied access to budget session %s owned=%s",
        identity.mask_pan(caller), session_id, identity.mask_pan(owner),
    )
    return HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


def _authorized_owner(conn, session_id: str) -> Optional[str]:
    """
    Owner of a budget session, having checked the caller may see it.

    Raises 404 when the session does not exist or belongs to somebody else, and 503
    when the question could not be answered - an authorization check that cannot run
    must not default to allowing access.
    """
    try:
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE session_id = %s AND upload_type = 'budget'",
            (session_id,),
        ).fetchone()
    except Exception as e:
        logger.error("[budget] owner lookup failed for %s: %s", session_id, e)
        raise HTTPException(
            status_code=503,
            detail="Could not verify access to this session. Please retry.",
        )

    if row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)

    owner = str(row[0]) if row[0] is not None else None
    if not identity.owns_record(owner):
        raise _deny(session_id, owner)
    return owner


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_budget_session(
    session_id: str, user_id: str, df: pd.DataFrame, accounts: dict
) -> str:
    """
    Persist a parsed statement, reusing an existing session for an identical upload.

    Returns the session id that actually holds the data, which is not necessarily the
    one passed in - the same contract as equity's create_session, and for the same
    reason: returning an id with no registry row hands the caller something that 404s.
    """
    ledger_hash = _budget_ledger_hash(df, user_id)

    duplicate_id = storage.check_duplicate_upload(ledger_hash, user_id)
    if duplicate_id:
        logger.info("[budget] upload deduped onto existing session %s", duplicate_id)
        return duplicate_id

    # Compression and encryption are ~100ms of CPU on a large statement. Doing them here
    # keeps that off a pooled connection - see the module docstring.
    compressed = _compress_frame(df)
    encrypted_txns = crypto.encrypt(compressed, aad=session_id)

    debits = df[df["type"] == "debit"]["amount"].sum() if not df.empty else 0.0
    credits = df[df["type"] == "credit"]["amount"].sum() if not df.empty else 0.0
    metrics = {"total_income": float(credits), "total_expense": float(debits)}
    encrypted_metrics = crypto.encrypt_json(metrics, aad=session_id)

    accounts_json = json.dumps(accounts)
    period = _statement_period(df)

    with db.connect() as conn:
        # ON CONFLICT on the dedup index rather than the primary key: a concurrent
        # identical upload must resolve to the row that landed, not silently do nothing
        # and leave us returning an id with no payload.
        row = conn.execute(
            """
            INSERT INTO sessions (
                session_id, user_id, upload_type, data_hash,
                metrics, is_partial, statement_period
            ) VALUES (%s, %s, 'budget', %s, %s, false, %s)
            ON CONFLICT (data_hash, user_id) WHERE data_hash IS NOT NULL
            DO UPDATE SET updated_at = now()
            RETURNING session_id
            """,
            (session_id, user_id, ledger_hash, encrypted_metrics, period),
        ).fetchone()

        final_session_id = str(row[0]) if row else session_id

        # If a concurrent upload won, its payload is already encrypted under *its*
        # session_id as AAD. Re-encrypting under the winning id keeps the AAD honest.
        if final_session_id != session_id:
            encrypted_txns = crypto.encrypt(compressed, aad=final_session_id)

        conn.execute(
            """
            INSERT INTO budget_payloads (session_id, codec, transactions, accounts, byte_size)
            VALUES (%s, 'zlib_json', %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                transactions = EXCLUDED.transactions,
                accounts     = EXCLUDED.accounts,
                byte_size    = EXCLUDED.byte_size,
                updated_at   = now()
            """,
            (final_session_id, encrypted_txns, accounts_json, len(compressed)),
        )

    return final_session_id


def _statement_period(df: pd.DataFrame) -> str:
    """"YYYY-MM-DD..YYYY-MM-DD" for the rows, or "" when there are no usable dates."""
    if df is None or df.empty or "date" not in df.columns:
        return ""
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dates.empty:
        return ""
    return f"{dates.min():%Y-%m-%d}..{dates.max():%Y-%m-%d}"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def decode_budget_payload(
    encrypted_txns: Optional[bytes], accounts, session_id: str,
) -> Tuple[pd.DataFrame, dict]:
    """
    Turn a raw budget_payloads row into (transactions, accounts).

    Split out of get_budget_session so the account export can decode a budget session
    without re-implementing the decrypt/decompress/normalise sequence - a second copy
    would be one schema change away from silently exporting the wrong shape. Takes the
    already-fetched columns rather than a session id, because the export reads every
    domain in one join and must not issue a query per row.

    Does NO authorization: callers must have established ownership already. That is
    why it takes bytes rather than an id.
    """
    df = pd.DataFrame()
    if encrypted_txns:
        df = _decompress_frame(crypto.decrypt(encrypted_txns, aad=session_id))
    df = _ensure_columns(df, accounts)
    return df, (accounts if isinstance(accounts, dict) else json.loads(accounts or "{}"))


def get_budget_session(session_id: str) -> Tuple[pd.DataFrame, dict]:
    """
    The caller's transactions for one session.

    Raises 404 if the session does not exist or is not theirs, 503 if that could not
    be determined. Never returns another user's rows - see the module docstring.
    """
    with db.connect() as conn:
        _authorized_owner(conn, session_id)
        row = conn.execute(
            "SELECT transactions, accounts FROM budget_payloads WHERE session_id = %s",
            (session_id,),
        ).fetchone()

    if not row:
        # The registry row exists and is ours, but the payload does not. Treat as empty
        # rather than 404: the session is legitimately the caller's.
        return pd.DataFrame(), {}

    encrypted_txns, accounts = row
    return decode_budget_payload(encrypted_txns, accounts, session_id)


def get_all_budget_sessions(user_id: str) -> Tuple[pd.DataFrame, Dict]:
    """
    Every transaction the user has uploaded, with overlapping statements merged.

    Scoped by user_id in SQL, so this path was never the vulnerable one.
    """
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT b.transactions, s.session_id, b.accounts
            FROM budget_payloads b
            JOIN sessions s ON b.session_id = s.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
            ORDER BY s.created_at
            """,
            (user_id,),
        ).fetchall()

    frames: List[pd.DataFrame] = []
    all_accounts: Dict[str, Any] = {}

    for txns_bytes, sid, accounts_json in rows:
        if accounts_json:
            all_accounts.update(
                accounts_json if isinstance(accounts_json, dict) else json.loads(accounts_json)
            )
        if not txns_bytes:
            continue
        try:
            df = _decompress_frame(crypto.decrypt(txns_bytes, aad=sid))
        except Exception as e:
            logger.error("[budget] could not decode session %s: %s", sid, e)
            continue
        if df.empty:
            continue
        df["session_id"] = sid
        frames.append(_ensure_columns(df, accounts_json))

    if not frames:
        return pd.DataFrame(), all_accounts

    master = pd.concat(frames, ignore_index=True)
    return _merge_overlapping_statements(master), all_accounts


def _merge_overlapping_statements(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows duplicated by two statements covering the same period.

    The previous implementation was `drop_duplicates(subset=[...], keep="last")`, which
    also collapsed *legitimate* repeats: two ₹50 coffees at the same merchant on the
    same day are two transactions, and it kept one. That is a silent, unrecoverable
    loss of the user's data.

    The distinction it missed is that a genuine repeat appears twice **within one
    statement**, while an overlap appears once in each of two. So for each identifying
    key, keep the rows from whichever single session contributed the most of them: that
    drops the overlap and preserves multiplicity.
    """
    if df.empty or "session_id" not in df.columns or df["session_id"].nunique() < 2:
        return df

    key = [c for c in _IDENTITY_COLUMNS if c in df.columns]
    if not key:
        return df

    counts = df.groupby(key + ["session_id"], dropna=False).size().rename("n").reset_index()
    # Ties break on session_id so the choice is deterministic across requests - an
    # unstable pick would make the same query return different totals.
    winners = (
        counts.sort_values(["n", "session_id"], ascending=[False, True])
        .drop_duplicates(subset=key, keep="first")[key + ["session_id"]]
    )
    merged = df.merge(winners, on=key + ["session_id"], how="inner")

    dropped = len(df) - len(merged)
    if dropped:
        logger.info("[budget] merged %d overlapping rows across statements", dropped)
    return merged.reset_index(drop=True)


def _ensure_columns(df: pd.DataFrame, accounts_json) -> pd.DataFrame:
    """
    Backfill columns added after some sessions were written.

    Kept vectorised and cheap; this runs on every read of every session.
    """
    if df.empty:
        return df

    meta = {}
    if isinstance(accounts_json, dict):
        meta = accounts_json
    elif accounts_json:
        try:
            meta = json.loads(accounts_json)
        except (TypeError, ValueError):
            meta = {}

    filename = str(meta.get("filename") or "").lower()

    if "txn_id" not in df.columns:
        df["txn_id"] = [uuid.uuid4().hex for _ in range(len(df))]
    if "notes" not in df.columns:
        df["notes"] = ""
    if "category" not in df.columns:
        df["category"] = "Uncategorized"

    if "source_bank" not in df.columns or df["source_bank"].isna().all():
        df["source_bank"] = meta.get("bank") or _bank_from_filename(filename)
    else:
        df["source_bank"] = df["source_bank"].fillna("GENERIC").astype(str).str.upper()

    if "account_type" not in df.columns or df["account_type"].isna().all():
        df["account_type"] = meta.get("account_type") or _account_type_from_filename(filename)
    else:
        df["account_type"] = df["account_type"].fillna("Savings Account").astype(str)

    return df


def _bank_from_filename(filename: str) -> str:
    """
    Last-resort bank guess for sessions written before the bank was recorded.

    New uploads carry the bank explicitly; this only serves old rows.
    """
    if "acct" in filename or "hdfc" in filename:
        return "HDFC"
    if "optransaction" in filename or "icici" in filename:
        return "ICICI"
    if "sbi" in filename:
        return "SBI"
    if "axis" in filename:
        return "AXIS"
    if "kotak" in filename:
        return "KOTAK"
    return "GENERIC"


def _account_type_from_filename(filename: str) -> str:
    if any(w in filename for w in ("credit card", "creditcard", "cc_", "card")):
        return "Credit Card"
    if "current" in filename:
        return "Current Account"
    if "salary" in filename:
        return "Salary Account"
    return "Savings Account"


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def list_budget_sessions(user_id: str) -> list:
    """
    Metadata for the user's uploads.

    Does *not* select b.transactions. It used to, and then decrypted and JSON-parsed
    every payload the user owns just to print a row count and a bank name in a modal -
    the exact cost tax_sessions._summarise exists to avoid. Everything shown here comes
    from the accounts metadata and the encrypted metrics blob, both of which are small.
    """
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.created_at, b.accounts, s.metrics,
                   b.byte_size, s.statement_period
            FROM sessions s
            JOIN budget_payloads b ON s.session_id = b.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
            ORDER BY s.created_at DESC
            """,
            (user_id,),
        ).fetchall()

    results = []
    for sid, created_at, accounts_json, enc_metrics, byte_size, period in rows:
        acc = accounts_json if isinstance(accounts_json, dict) else json.loads(accounts_json or "{}")
        filename = acc.get("filename", "Bank Statement")

        income = expense = 0.0
        try:
            if enc_metrics:
                metrics = crypto.decrypt_json(enc_metrics, aad=sid)
                income = float(metrics.get("total_income", 0.0))
                expense = float(metrics.get("total_expense", 0.0))
        except Exception as e:
            logger.warning("[budget] metrics unreadable for session %s: %s", sid, e)

        bank = str(acc.get("bank") or _bank_from_filename(filename.lower())).upper()
        account_type = acc.get("account_type") or _account_type_from_filename(filename.lower())

        results.append({
            "session_id": sid,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            "filename": filename,
            "bank": bank,
            "account_type": account_type,
            "rows": int(acc.get("rows", 0) or 0),
            "byte_size": int(byte_size or 0),
            "statement_period": period or "",
            "total_income": income,
            "total_expense": expense,
            "net_savings": income - expense,
        })
    return results


# ---------------------------------------------------------------------------
# Mutation
# ---------------------------------------------------------------------------

def update_budget_transactions(user_id: str, session_id: str, updates: list) -> bool:
    """
    Apply category/notes edits to rows within one session.

    Read and write are separate transactions with the decrypt/mutate/re-encrypt in
    between, so the connection is not held across that work.
    """
    with db.connect() as conn:
        _authorized_owner(conn, session_id)
        row = conn.execute(
            "SELECT transactions FROM budget_payloads WHERE session_id = %s",
            (session_id,),
        ).fetchone()

    if not row or not row[0]:
        return False

    df = _decompress_frame(crypto.decrypt(row[0], aad=session_id))
    if df.empty or "txn_id" not in df.columns:
        return False

    by_id = {u.get("txn_id"): u for u in updates if u.get("txn_id")}
    if not by_id:
        return True

    # Vectorised: build the whole mapping and apply it in two assignments rather than
    # running a boolean scan of the frame per update, which was O(updates x rows).
    if "category" not in df.columns:
        df["category"] = "Uncategorized"
    if "notes" not in df.columns:
        df["notes"] = ""

    ids = df["txn_id"]
    cat_map = {k: v["category"] for k, v in by_id.items() if v.get("category") is not None}
    note_map = {k: v["notes"] for k, v in by_id.items() if v.get("notes") is not None}
    if cat_map:
        df["category"] = ids.map(cat_map).fillna(df["category"])
    if note_map:
        df["notes"] = ids.map(note_map).fillna(df["notes"])

    compressed = _compress_frame(df)
    payload = crypto.encrypt(compressed, aad=session_id)

    with db.connect() as conn:
        conn.execute(
            "UPDATE budget_payloads SET transactions = %s, byte_size = %s, updated_at = now() "
            "WHERE session_id = %s",
            (payload, len(compressed), session_id),
        )
    return True


def reapply_rules_to_all_sessions(user_id: str) -> int:
    """
    Re-run categorization across every session the user owns.

    Structured as read-all / compute-all / write-all. The previous version held one
    transaction open across the whole loop *and* called categorize_transactions() from
    inside it, which opened two further connections per session - with a six-connection
    pool, six concurrent callers deadlocked until the checkout timeout fired.
    """
    from domains.budget.categorizer import categorize_transactions, load_user_rules

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, b.transactions
            FROM sessions s
            JOIN budget_payloads b ON s.session_id = b.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
            """,
            (user_id,),
        ).fetchall()

    # Rules are fetched once for the whole run, not once per session.
    rules = load_user_rules(user_id)

    recoded: List[Tuple[str, bytes, int]] = []
    total = 0
    for sid, txns_bytes in rows:
        if not txns_bytes:
            continue
        try:
            df = _decompress_frame(crypto.decrypt(txns_bytes, aad=sid))
        except Exception as e:
            logger.error("[budget] skipping unreadable session %s: %s", sid, e)
            continue
        if df.empty:
            continue
        df, _ = categorize_transactions(df, rules=rules)
        compressed = _compress_frame(df)
        recoded.append((sid, crypto.encrypt(compressed, aad=sid), len(compressed)))
        total += len(df)

    if recoded:
        with db.connect() as conn:
            for sid, payload, size in recoded:
                conn.execute(
                    "UPDATE budget_payloads SET transactions = %s, byte_size = %s, "
                    "updated_at = now() WHERE session_id = %s",
                    (payload, size, sid),
                )

    return total


def delete_budget_session(user_id: str, session_id: str) -> bool:
    """
    Delete one session and its payload.

    The payload delete used to run unscoped, with the owner check only on the second
    statement - so a cross-user call destroyed the victim's transactions and left their
    session row behind. Ownership is now established before anything is deleted, and
    the payload goes via the FK cascade rather than a separate unscoped statement.
    """
    with db.connect() as conn:
        _authorized_owner(conn, session_id)
        conn.execute(
            "DELETE FROM sessions WHERE session_id = %s AND user_id = %s",
            (session_id, user_id),
        )
    return True
