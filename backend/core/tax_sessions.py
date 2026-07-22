"""
core/tax_sessions.py

Disk-persisted session store for Tax Expert AIS data.
Sessions survive backend restarts by writing to a JSON file.
"""

import uuid
import json
import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Storage Path ──────────────────────────────────────────────────────────────
# Store sessions in backend/data/ directory (already exists)
_DATA_DIR = Path(__file__).parent.parent / "data"
_SESSIONS_FILE = _DATA_DIR / "tax_sessions.json"

# In-memory cache (loaded from disk on first access)
_tax_sessions: dict = {}
_sessions_loaded: bool = False


# ── Persistence Helpers ───────────────────────────────────────────────────────

def _ensure_data_dir():
    """Ensure the data directory exists."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_from_disk():
    """Load sessions from disk into the in-memory cache."""
    global _tax_sessions, _sessions_loaded
    _ensure_data_dir()
    if _SESSIONS_FILE.exists():
        try:
            with open(_SESSIONS_FILE, "r", encoding="utf-8") as f:
                _tax_sessions = json.load(f)
            logger.info(f"Loaded {len(_tax_sessions)} tax session(s) from disk.")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load tax sessions from disk: {e}. Starting fresh.")
            _tax_sessions = {}
    else:
        _tax_sessions = {}
    _sessions_loaded = True


def _save_to_disk():
    """Persist the in-memory session cache to disk."""
    _ensure_data_dir()
    try:
        tmp_path = str(_SESSIONS_FILE) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_tax_sessions, f, ensure_ascii=False, default=str)
        # Atomic rename to avoid partial writes
        os.replace(tmp_path, _SESSIONS_FILE)
    except IOError as e:
        logger.error(f"Failed to persist tax sessions to disk: {e}")


def _ensure_loaded():
    """Lazy-load sessions from disk on first call."""
    if not _sessions_loaded:
        _load_from_disk()


# ── Public API ────────────────────────────────────────────────────────────────

def create_tax_session(ais_data: dict, pan_id: Optional[str] = None, flags: Optional[dict] = None) -> str:
    """Create a new tax session from parsed AIS data and persist it to disk."""
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
    # Deep merge overrides
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
    """Delete a tax session from memory and disk."""
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
            ais = data["ais_data"]
            results.append({
                "session_id": sid,
                "pan": data["pan"],
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

