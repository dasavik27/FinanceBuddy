"""
routers/accounts.py

Vault Manager API Gateway.
Lists the caller's own sessions across modules, and permanently deletes an account.
"""

from fastapi import APIRouter, HTTPException
import logging

from psycopg.rows import dict_row

from shared import db, identity, storage, users

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
    from domains.tax_expert import tax_sessions as tax_store

    # Memory first: an eviction that happens after the delete leaves a window where
    # the rows are gone but the resident copy is not, and with no row left to name an
    # owner the ownership check has nothing to compare against.
    mf_sessions.evict_for_user(caller)
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
        from domains.tax_expert import tax_sessions
        from domains.tax_expert import computation_cache

        clear_market_data_cache()
        # Via the module's own accessor, not `sessions._SESSIONS.clear()`: that
        # reached into the private dict without _SESSIONS_LOCK, racing the GC daemon
        # and every request thread.
        sessions.clear_all()
        tax_sessions.clear_all()
        # Memoized tax computations reference the sessions just dropped; without
        # this they would sit in memory until LRU eviction pushed them out.
        computation_cache.clear_all()
        
        return {"status": "ok", "message": "Global market and session caches cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
