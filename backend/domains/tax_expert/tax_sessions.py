"""
core/tax_sessions.py

Disk-persisted session store for Tax Expert AIS data.
Sessions survive backend restarts by writing to a unified SQLite database.
"""

import uuid
import json
import os
import sqlite3
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Storage Path ──────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "metadata.sqlite3"

# Initialize tax_sessions table
with sqlite3.connect(DB_PATH) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tax_sessions (
            session_id TEXT PRIMARY KEY,
            pan TEXT,
            data TEXT
        )
    """)
    conn.commit()

# In-memory cache for fast reads
_tax_sessions: dict = {}
_sessions_loaded: bool = False

def _load_from_disk():
    """Load sessions from SQLite into the in-memory cache."""
    global _tax_sessions, _sessions_loaded
    _tax_sessions = {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT session_id, data FROM tax_sessions")
            for row in cursor.fetchall():
                _tax_sessions[row[0]] = json.loads(row[1])
        logger.info(f"Loaded {len(_tax_sessions)} tax session(s) from SQLite.")
    except Exception as e:
        logger.error(f"Failed to load tax sessions from SQLite: {e}")
    _sessions_loaded = True

def _save_to_disk():
    """Persist the in-memory session cache to SQLite."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Upsert all sessions
            for sid, data in _tax_sessions.items():
                pan = data.get("pan", "")
                data_str = json.dumps(data, ensure_ascii=False, default=str)
                conn.execute("""
                    INSERT INTO tax_sessions (session_id, pan, data) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, pan=excluded.pan
                """, (sid, pan, data_str))
            
            # Delete removed sessions
            placeholders = ','.join(['?'] * len(_tax_sessions))
            if placeholders:
                conn.execute(f"DELETE FROM tax_sessions WHERE session_id NOT IN ({placeholders})", list(_tax_sessions.keys()))
            else:
                conn.execute("DELETE FROM tax_sessions")
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist tax sessions to SQLite: {e}")

def _ensure_loaded():
    """Lazy-load sessions from disk on first call."""
    if not _sessions_loaded:
        _load_from_disk()

# ── Public API ────────────────────────────────────────────────────────────────

def create_tax_session(ais_data: dict, pan_id: Optional[str] = None, flags: Optional[dict] = None) -> str:
    """Create a new tax session from parsed AIS data and persist it."""
    _ensure_loaded()
    session_id = str(uuid.uuid4())
    pan = pan_id or ais_data.get("personal", {}).get("pan", "")
    _tax_sessions[session_id] = {
        "ais_data": ais_data,
        "deductions": {},
        "overrides": {},
        "pan": pan,
        "reconciliation_flags": flags or {}
    }
    _save_to_disk()
    logger.info(f"Created tax session {session_id} for PAN {pan}")
    return session_id

def get_tax_session(session_id: str) -> Optional[dict]:
    """Retrieve a tax session by ID."""
    _ensure_loaded()
    return _tax_sessions.get(session_id)

def update_deductions(session_id: str, deductions: dict) -> bool:
    """Update user-provided deductions for a tax session."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["deductions"] = deductions
    _save_to_disk()
    return True

def update_ais_data(session_id: str, ais_data: dict) -> bool:
    """Update AIS data (e.g., manual cost patching) and persist."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["ais_data"] = ais_data
    _save_to_disk()
    return True

def update_overrides(session_id: str, overrides: dict) -> bool:
    """Update manual inputs (losses, deductions, schedule AL) and persist."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    if "overrides" not in session:
        session["overrides"] = {}

    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(session["overrides"].get(k), dict):
            session["overrides"][k].update(v)
        else:
            session["overrides"][k] = v

    _save_to_disk()
    return True

def delete_tax_session(session_id: str) -> bool:
    """Delete a tax session from memory and SQLite."""
    _ensure_loaded()
    if session_id in _tax_sessions:
        del _tax_sessions[session_id]
        _save_to_disk()
        return True
    return False

def get_sessions_by_pan(pan: str) -> list:
    """Get all tax sessions for a given PAN."""
    _ensure_loaded()
    results = []
    for sid, data in _tax_sessions.items():
        if data.get("pan", "").upper() == pan.upper():
            ais = data.get("ais_data", {})
            results.append({
                "session_id": sid,
                "pan": data.get("pan", ""),
                "name": ais.get("personal", {}).get("name", ""),
                "fy": ais.get("fy", ""),
                "gross_salary": ais.get("salary", {}).get("gross", 0),
            })
    return results

def update_itr_data(session_id: str, itr_data: dict) -> bool:
    """Persist parsed ITR data into a tax session for comparison."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return False
    session["itr_data"] = itr_data
    _save_to_disk()
    logger.info(f"ITR data saved for session {session_id}")
    return True

def get_itr_data(session_id: str) -> Optional[dict]:
    """Retrieve previously parsed ITR data for a session."""
    _ensure_loaded()
    session = _tax_sessions.get(session_id)
    if not session:
        return None
    return session.get("itr_data")

def delete_all_for_pan(pan: str) -> int:
    """Delete all tax sessions for a given PAN from memory and disk."""
    _ensure_loaded()
    global _tax_sessions
    count = 0
    keys_to_delete = []
    
    for sid, data in _tax_sessions.items():
        if data.get("pan", "").upper() == pan.upper():
            keys_to_delete.append(sid)
            
    for sid in keys_to_delete:
        del _tax_sessions[sid]
        count += 1
        
    if count > 0:
        _save_to_disk()
        
    return count

