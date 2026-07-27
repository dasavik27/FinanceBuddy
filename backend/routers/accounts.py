"""
routers/accounts.py

Vault Manager API Gateway.
Allows querying of all sessions grouped by PAN, and purging data.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
import sqlite3
import os

import core.tax_sessions
from core.storage import DB_PATH, delete_all_for_pan

router = APIRouter()

@router.get("/summary")
def get_accounts_summary():
    """
    Returns an aggregated list of all active sessions (Mutual Funds, Stocks, Tax) grouped by PAN.
    """
    # 1. Fetch CAS sessions from SQLite
    cas_sessions = []
    if os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT session_id, pan_id, upload_type, created_at FROM sessions WHERE pan_id IS NOT NULL AND pan_id != ''")
            cas_sessions = [dict(row) for row in cursor.fetchall()]
            
    # 2. Fetch Tax sessions from JSON cache
    core.tax_sessions._ensure_loaded()
    tax_sessions_list = []
    for sid, data in core.tax_sessions._tax_sessions.items():
        pan = data.get("pan")
        if pan:
            tax_sessions_list.append({
                "session_id": sid,
                "pan_id": pan,
                "upload_type": "tax_expert",
                "created_at": None # We don't track creation time in JSON currently, but that's fine
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
    Permanently deletes all session data (disk + sqlite + memory cache) associated with a PAN.
    """
    pan_id = pan_id.upper()
    
    # 1. Delete all CAS sessions
    cas_deleted = delete_all_for_pan(pan_id)
    
    # 2. Delete all Tax sessions
    tax_deleted = core.tax_sessions.delete_all_for_pan(pan_id)
    
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
        from services.market_data import clear_market_data_cache
        from core import sessions, tax_sessions
        
        clear_market_data_cache()
        sessions._SESSIONS.clear()
        tax_sessions._tax_sessions.clear()
        
        return {"status": "ok", "message": "Global market and session caches cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
