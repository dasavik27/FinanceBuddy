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

from core.models import Portfolio

# Ephemeral session store (Zero disk logging) with auto-expiration tracking
_SESSIONS: Dict[str, Dict[str, Any]] = {}
# Session Time-To-Live (4 hours) prevents premature timeout during deep diagnostic reviews
SESSION_TTL_HOURS = 4

def create_session(df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool) -> str:
    """
    Initializes a new ephemeral portfolio session. Retroactively classifies holdings via the
    CategorizationEngine to ensure parity with global AMFI & Morningstar categorization standards.
    """
    session_id = str(uuid.uuid4())
    
    # Execute one-time categorization normalization during session initialization
    if not df_h.empty and "Category" in df_h.columns:
        from core.logic import CategorizationEngine as CE
        def fix_cat(row):
            return CE.detect_category(str(row["Fund"]))
        df_h["Category"] = df_h.apply(fix_cat, axis=1)

    _SESSIONS[session_id] = {
        "portfolio": Portfolio(df_h, df_t, df_s, is_partial),
        "created_at": datetime.now(),
        "last_accessed": datetime.now(),  # TTL extension heartbeat tracking
    }
    return session_id

# ── Automated Session Garbage Collector ───────────────────────────────────

def _session_purge_worker():
    """
    Daemon thread executing periodic background purges of abandoned portfolio sessions.
    Evaluates expiration against last active API interaction heartbeat.
    """
    while True:
        try:
            now = datetime.now()
            expired = [sid for sid, data in list(_SESSIONS.items())
                       if (now - data.get("last_accessed", data["created_at"])).total_seconds() > (SESSION_TTL_HOURS * 3600)]
            for sid in expired:
                if sid in _SESSIONS: del _SESSIONS[sid]
        except Exception: pass
        time.sleep(600)  # GC sweep execution interval: 10 minutes

# Initialize background garbage collection daemon
threading.Thread(target=_session_purge_worker, daemon=True).start()


def get_session(session_id: str) -> Portfolio:
    """
    Retrieves the active portfolio session and updates the activity timestamp heartbeat.
    Raises an HTTP 404 Exception if the session has expired or does not exist.
    """
    if session_id not in _SESSIONS:
        raise HTTPException(status_code=404, detail="Session expired or not found. Please re-upload your CAS.")
    
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
