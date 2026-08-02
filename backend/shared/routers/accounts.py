"""
routers/accounts.py

Vault Manager API Gateway.
Lists the caller's own sessions across modules, and permanently deletes an account.
"""

from fastapi import APIRouter, HTTPException
import logging

from psycopg.rows import dict_row

from shared import crypto, db, identity, storage, users

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/summary")
def get_accounts_summary():
    """
    The caller's own sessions, across both modules.

    Scoped to the caller. This previously took no parameters and returned every PAN
    paired with every session_id on the deployment - and since a session_id is all
    that is needed to read a portfolio, that made full disclosure a two-request
    operation: enumerate here, then read.

    One query now covers both modules. The tax store used to keep its rows in a
    private table that shared SQL could not see, so its sessions had to be collected
    separately from an in-memory scan - which also meant they carried no created_at.
    """
    caller = identity.current_user_id()
    if not caller:
        raise HTTPException(status_code=401, detail="Sign in to view your accounts.")

    with db.connect(row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT session_id, upload_type, created_at
            FROM sessions
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (caller,),
        ).fetchall()

    pan = identity.current_pan()
    return {
        "status": "ok",
        "accounts": [{
            "user_id": caller,
            "pan": pan,
            "sessions": [{
                "session_id": row["session_id"],
                "module": row["upload_type"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            } for row in rows],
        }] if rows or pan else [],
    }


@router.get("/me/export")
def export_account_data():
    """
    Everything held about the caller, as one JSON document.

    The counterpart to DELETE /me. Storage is durable now and this handles Indian
    financial data, so the DPDP Act's access and portability rights are in scope -
    and a delete button without an export is a deletion the user cannot review first.

    Payloads are decompressed and returned as records rather than as opaque blobs,
    because an export the user cannot read is not portability.
    """
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Sign in to export your data.")

    with db.connect(row_factory=dict_row) as conn:
        account = conn.execute(
            """
            SELECT u.id, u.created_at, u.last_seen_at, p.pan_encrypted, p.display_name
            FROM users u
            LEFT JOIN profiles p ON p.user_id = u.id
            WHERE u.id = %s
            """,
            (caller.user_id,),
        ).fetchone()

        linked = conn.execute(
            "SELECT issuer, email, created_at FROM identities WHERE user_id = %s",
            (caller.user_id,),
        ).fetchall()

        rows = conn.execute(
            """
            SELECT s.session_id, s.upload_type, s.created_at, s.statement_period,
                   s.metrics,
                   p.holdings, p.transactions, p.sips, p.meta,
                   t.data AS tax_data
            FROM sessions s
            LEFT JOIN session_payloads p ON p.session_id = s.session_id
            LEFT JOIN tax_payloads     t ON t.session_id = s.session_id
            WHERE s.user_id = %s
            ORDER BY s.created_at DESC
            """,
            (caller.user_id,),
        ).fetchall()

    exported = []
    for row in rows:
        session_id = row["session_id"]
        # An export that silently omits a row the user owns is worse than one that
        # says it could not be read: this is the artefact someone checks *before*
        # deleting their account.
        try:
            metrics = crypto.decrypt_json(row["metrics"], aad=session_id) or {}
        except crypto.DecryptionFailed:
            logger.exception("[EXPORT] cannot decrypt metrics for %s", session_id)
            metrics = {"error": "could not be decrypted"}

        entry = {
            "session_id": session_id,
            "module": row["upload_type"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "statement_period": row["statement_period"],
            "metrics": metrics,
        }
        try:
            if row["upload_type"] == "tax_expert":
                entry["ais_data"] = crypto.decrypt_json(row["tax_data"], aad=session_id)
            else:
                df_h, df_t, df_s = storage.decode_payload({
                    "holdings": crypto.decrypt(row["holdings"], aad=session_id),
                    "transactions": crypto.decrypt(row["transactions"], aad=session_id),
                    "sips": crypto.decrypt(row["sips"], aad=session_id),
                    "meta": row["meta"],
                })
                entry["holdings"] = df_h.to_dict(orient="records")
                entry["transactions"] = df_t.to_dict(orient="records")
                entry["sips"] = df_s.to_dict(orient="records")
        except crypto.DecryptionFailed:
            logger.exception("[EXPORT] cannot decrypt payload for %s", session_id)
            entry["error"] = "this session's data could not be decrypted"
        exported.append(entry)

    return {
        "account": {
            "user_id": str(account["id"]),
            "created_at": account["created_at"].isoformat() if account["created_at"] else None,
            "pan": users.find_pan(caller.user_id),
            "display_name": account["display_name"],
        } if account else None,
        # Deliberately no `subject`: it is the provider's identifier for this person
        # and exporting it invites someone to paste it somewhere it becomes a
        # credential. Issuer and email are enough to say "you signed in with this".
        "linked_logins": [{
            "issuer": row["issuer"],
            "email": row["email"],
            "linked_at": row["created_at"].isoformat() if row["created_at"] else None,
        } for row in linked],
        "sessions": exported,
    }


@router.delete("/me")
def purge_account_data():
    """
    Permanently delete the caller's account and everything belonging to it.

    Addressed as /me rather than /{pan}. Taking the target from the path meant the
    route had to check that it matched the caller, and a route whose correctness
    depends on remembering that check is one bad merge away from letting anyone
    destroy any account by naming it. There is now no way to name someone else.

    One statement does it: `users` cascades to identities, profiles and sessions, and
    those cascade to the payload tables. Previously this fanned out across two
    modules and five tables, and had to remember to evict memory as well - dropping
    only the rows left portfolios resident, so data the user was told had been
    permanently deleted stayed readable by anyone holding a session id.
    """
    caller = identity.current_user_id()
    if not caller:
        raise HTTPException(status_code=401, detail="Sign in to purge your data.")

    from domains.mutual_funds import sessions as mf_sessions
    from domains.equity import sessions as eq_sessions
    from domains.tax_expert import tax_sessions as tax_store

    # Memory first: an eviction that happens after the delete leaves a window where
    # the rows are gone but the resident copy is not, and with no row left to name an
    # owner the ownership check has nothing to compare against.
    #
    # Every domain holding resident state has to appear here. Equity was missing, so a
    # purge deleted the rows and left the stock portfolios readable.
    mf_sessions.evict_for_user(caller)
    eq_sessions.evict_for_user(caller)
    tax_store.evict_for_user(caller)

    deleted = storage.delete_all_for_user(caller)
    users.invalidate(caller)

    logger.info("[PURGE] account %s removed (%d session(s))", caller, deleted)
    return {
        "status": "ok",
        "message": f"Permanently deleted your account and {deleted} session(s).",
        "deleted_count": deleted,
    }


@router.post("/clear_caches")
def clear_all_system_caches():
    """
    Clears all in-memory market data caches (NAVs, TERs, mappings) and session DataFrames.
    """
    try:
        from shared.services.market_data import clear_market_data_cache
        from domains.mutual_funds import sessions
        from domains.equity import sessions as eq_sessions
        from domains.tax_expert import tax_sessions
        from domains.tax_expert import computation_cache

        clear_market_data_cache()
        # Via the module's own accessor, not `sessions._SESSIONS.clear()`: that
        # reached into the private dict without _SESSIONS_LOCK, racing the GC daemon
        # and every request thread.
        sessions.clear_all()
        eq_sessions.clear_all()
        tax_sessions.clear_all()
        # Memoized tax computations reference the sessions just dropped; without
        # this they would sit in memory until LRU eviction pushed them out.
        computation_cache.clear_all()
        
        return {"status": "ok", "message": "Global market and session caches cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
