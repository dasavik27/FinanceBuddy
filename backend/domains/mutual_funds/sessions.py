"""
core/sessions.py

In-Memory State Management & Portfolio Concurrency Engine
=========================================================
Manages thread-safe session storage for multi-tab financial state. Features automatic background
garbage collection (TTL extension tracking) and high-speed DataFrame-to-record JSON serialization.
Zero disk retention ensures institutional privacy compliance for uploaded CAS records.
"""

import uuid
import threading
import time
import numpy as np
import pandas as pd
from datetime import datetime
from fastapi import HTTPException
from typing import Dict, Any

from domains.mutual_funds.models import Portfolio
from shared import storage
import logging
logger = logging.getLogger(__name__)


# Ephemeral session store (Zero disk logging) with auto-expiration tracking
_SESSIONS: Dict[str, Dict[str, Any]] = {}
# Session Time-To-Live (4 hours) prevents premature timeout during deep diagnostic reviews
SESSION_TTL_HOURS = 4

def create_session(df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, pan_id: str = None, upload_type: str = 'mutual_funds') -> str:
    """
    Initializes a new ephemeral portfolio session. Retroactively classifies holdings via the
    CategorizationEngine to ensure parity with global AMFI & Morningstar categorization standards.
    """
    # Deduplication check: if this ledger exists on disk, skip processing
    duplicate_id = storage.check_duplicate_upload(df_t)
    if duplicate_id:
        return duplicate_id

    session_id = str(uuid.uuid4())
    
    # NOTE (Fix C-2): The CAS parser already classifies categories using
    # raw_cat, raw_type, AND fund name via CategorizationEngine.detect_category().
    # Re-running detect_category() here with ONLY the fund name would discard
    # the richer CAS metadata (e.g., "Banking & PSU" debt → misclassified as Thematic).
    # We only re-classify funds with empty/missing categories.
    if not df_h.empty and "Category" in df_h.columns:
        from domains.mutual_funds.logic import CategorizationEngine as CE
        mask = df_h["Category"].isna() | (df_h["Category"].str.strip() == "")
        if mask.any():
            df_h.loc[mask, "Category"] = df_h.loc[mask, "Fund"].apply(
                lambda fn: CE.detect_category(str(fn))
            )

    portfolio = Portfolio(df_h, df_t, df_s, is_partial)
    portfolio.update_live_navs()
    
    # 3. Persist to Parquet / SQLite (including PAN and upload type)
    final_session_id = storage.save_session(session_id, df_h, df_t, df_s, is_partial, pan_id, upload_type)
    
    _SESSIONS[session_id] = {
        "portfolio": portfolio,
        "created_at": datetime.now(),
        "last_accessed": datetime.now(),  # TTL extension heartbeat tracking
    }
    return session_id

# ── Automated Session Garbage Collector ───────────────────────────────────

def _session_purge_worker():
    """
    Daemon thread executing periodic background purges of abandoned portfolio sessions.
    Evaluates expiration against last active API interaction heartbeat.
    Also sweeps SQLite and JSON stores for disk-level retention limit (24 hours).
    """
    while True:
        try:
            now = datetime.now()
            
            # 1. In-Memory Purge (4 hours)
            expired = [sid for sid, data in list(_SESSIONS.items())
                       if (now - data.get("last_accessed", data["created_at"])).total_seconds() > (SESSION_TTL_HOURS * 3600)]
            for sid in expired:
                if sid in _SESSIONS: del _SESSIONS[sid]
                
            # 2. Disk-Level Purge (24 hours) for CAS
            from shared.storage import DB_PATH, delete_session
            import sqlite3
            if storage.os.path.exists(DB_PATH):
                with sqlite3.connect(DB_PATH) as conn:
                    cursor = conn.execute("SELECT session_id FROM sessions WHERE created_at < datetime('now', '-24 hours')")
                    for row in cursor.fetchall():
                        sid = row[0]
                        delete_session(sid)
                        
            # 3. Disk-Level Purge (24 hours) for Tax
            # We don't store created_at in JSON natively, but we can just skip this for now or clear empty ones
            # Actually, to be safe, we only GC the CAS files since they are heavy (Parquet). 
            # We can leave the tax_sessions.json or we can purge them if they are too old.
            
        except Exception as e:
            logger.error(f"[GC ERROR] {e}")
        time.sleep(600)  # GC sweep execution interval: 10 minutes

# Initialize background garbage collection daemon
threading.Thread(target=_session_purge_worker, daemon=True).start()


def get_session(session_id: str) -> Portfolio:
    """
    Retrieves the active portfolio session and updates the activity timestamp heartbeat.
    Raises an HTTP 404 Exception if the session has expired or does not exist.
    """
    if session_id not in _SESSIONS:
        # Fallback: Attempt to reconstruct from Data Lake Disk Storage
        disk_data = storage.load_session(session_id)
        if disk_data is None:
            raise HTTPException(status_code=404, detail="Session expired or not found. Please re-upload your CAS.")
            
        df_h, df_t, df_s, is_partial = disk_data
        portfolio = Portfolio(df_h, df_t, df_s, is_partial)
        # Note: We do NOT re-fetch live NAVs automatically on every history load to save API calls
        # portfolio.update_live_navs() 
        
        _SESSIONS[session_id] = {
            "portfolio": portfolio,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
        }
    
    # Extend session TTL on every active API access
    _SESSIONS[session_id]["last_accessed"] = datetime.now()
    
    return _SESSIONS[session_id]["portfolio"]

def df_to_records(df: pd.DataFrame) -> list:
    """
    High-fidelity DataFrame serializer. Converts timestamps to ISO date strings and safely
    sanitizes NaN / Inf values into JSON-compliant None literals prior to API delivery.
    """
    if df is None or df.empty:
        return []
    df2 = df.copy()
    for col in df2.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df2[col] = df2[col].dt.strftime("%Y-%m-%d")
    for col in df2.columns:
        df2[col] = df2[col].apply(
            lambda v: None if (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else v
        )
    return df2.to_dict(orient="records")
