"""
routers/accounts.py

Vault Manager API Gateway.
Allows querying of all sessions grouped by PAN, and purging data.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
import logging
import sqlite3
import os

import domains.tax_expert.tax_sessions
from shared import identity
from shared.storage import DB_PATH, delete_all_for_pan

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/summary")
def get_accounts_summary():
    """
    Sessions belonging to the calling PAN, grouped by module.

    Scoped to the caller. This previously took no parameters and returned every PAN
    paired with every session_id on the deployment - and since a session_id is all
    that is needed to read a portfolio, that made full disclosure a two-request
    operation: enumerate here, then read.
    """
    caller = identity.current_pan()
    if not caller:
        raise HTTPException(
            status_code=401,
            detail="Sign in with your PAN to view your accounts.",
        )

    # 1. Fetch this caller's CAS sessions from SQLite
    cas_sessions = []
    if os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT session_id, pan_id, upload_type, created_at FROM sessions "
                "WHERE pan_id = ?",
                (caller,),
            )
            cas_sessions = [dict(row) for row in cursor.fetchall()]

    # 2. Fetch Tax sessions via the store's public accessor rather than reaching
    # into its private _tax_sessions global (which also skipped LRU bookkeeping).
    tax_sessions_list = []
    for sid, data in domains.tax_expert.tax_sessions.list_sessions():
        pan = data.get("pan")
        if pan and pan.upper() == caller:
            tax_sessions_list.append({
                "session_id": sid,
                "pan_id": pan,
                "upload_type": "tax_expert",
                "created_at": None  # not surfaced here; the store tracks it in SQLite
            })
            
    # 3. Aggregate by PAN
    accounts = {}
    
    for row in cas_sessions + tax_sessions_list:
        pan = row["pan_id"].upper()
        if pan not in accounts:
            accounts[pan] = {
                "pan": pan,
                "sessions": []
            }
        accounts[pan]["sessions"].append({
            "session_id": row["session_id"],
            "module": row["upload_type"],
            "created_at": row["created_at"]
        })
        
    return {"status": "ok", "accounts": list(accounts.values())}


@router.delete("/{pan_id}")
def purge_account_data(pan_id: str):
    """
    Permanently deletes all session data (disk + sqlite + memory cache) for a PAN.

    A caller may only purge their own PAN. Unauthenticated, this endpoint let anyone
    destroy any account's entire dataset by naming its PAN.
    """
    pan_id = pan_id.upper()

    caller = identity.current_pan()
    if not caller:
        raise HTTPException(status_code=401, detail="Sign in with your PAN to purge your data.")
    if caller != pan_id:
        logger.warning(
            "[AUTHZ] %s attempted to purge %s",
            identity.mask_pan(caller), identity.mask_pan(pan_id),
        )
        raise HTTPException(status_code=403, detail="You can only purge your own account data.")


    # 1. Delete all CAS sessions — disk AND memory.
    #
    # Dropping only the SQLite rows left the portfolios resident, so data the user was
    # told had been permanently deleted stayed readable by anyone holding the session
    # id for up to the session TTL. Worse, with the registry row gone the ownership
    # check had nothing to compare against. The tax store already evicted on purge;
    # the mutual-fund store did not.
    from domains.mutual_funds import sessions as mf_sessions
    evicted = mf_sessions.evict_for_pan(pan_id)
    cas_deleted = delete_all_for_pan(pan_id)
    if evicted:
        logger.info("[PURGE] evicted %d resident session(s) for %s", evicted, identity.mask_pan(pan_id))
    
    # 2. Delete all Tax sessions
    tax_deleted = domains.tax_expert.tax_sessions.delete_all_for_pan(pan_id)
    
    total_deleted = cas_deleted + tax_deleted
    
    if total_deleted == 0:
        raise HTTPException(status_code=404, detail="No data found for this PAN.")
        
    return {
        "status": "ok", 
        "message": f"Successfully purged {total_deleted} session(s) across all modules for PAN {pan_id}.",
        "deleted_count": total_deleted
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
