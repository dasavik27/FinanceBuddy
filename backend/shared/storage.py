"""
core/storage.py

Data Lake Persistence & Transaction Ledger Reconciliation Engine
================================================================
Manages robust disk-level storage of CAS uploaded DataFrames using a unified SQLite database,
mapped against an SQLite metadata registry. Includes a deterministic row-level hashing
engine to prevent duplicate snapshots and allow semantic ledger reconciliation.
"""

import os
import json
import sqlite3
import pandas as pd
import hashlib
from typing import Optional, Dict, Any, Tuple
import logging
logger = logging.getLogger(__name__)


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
DB_PATH = os.path.join(DATA_DIR, "metadata.sqlite3")

# Ensure directories exist
os.makedirs(SESSIONS_DIR, exist_ok=True)

def _init_db():
    """Initializes the SQLite metadata registry and runs migrations."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                pan_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data_hash TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_value REAL,
                total_invested REAL,
                num_funds INTEGER,
                is_partial BOOLEAN
            )
        """)
        # Schema Migration: Add pan_id to sessions if missing
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN pan_id TEXT")
        except sqlite3.OperationalError:
            pass # Column already exists
            
        try:
            conn.execute("ALTER TABLE sessions ADD COLUMN upload_type TEXT DEFAULT 'mutual_funds'")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()

_init_db()

def _compute_ledger_hash(df_t: pd.DataFrame) -> str:
    """
    Computes a deterministic SHA-256 fingerprint for the transaction ledger.
    Treats the portfolio like an immutable blockchain ledger.
    """
    if df_t.empty:
        return "empty_ledger"
    
    # Sort transactions chronologically to ensure deterministic ordering
    sorted_df = df_t.sort_values(by=["Date", "Fund", "Type"]).copy()
    
    # Create a string representation of the critical columns for each row
    # We round floats to prevent precision differences from failing the hash
    row_strings = sorted_df.apply(
        lambda row: f"{row['Date']}_{row.get('Fund', '')}_{row.get('Type', '')}_{round(row.get('Units', 0.0), 3)}_{round(row.get('Amount', 0.0), 2)}",
        axis=1
    )
    
    # Concatenate all rows into a single giant string and hash it
    full_ledger_string = "|".join(row_strings.values.astype(str))
    return hashlib.sha256(full_ledger_string.encode('utf-8')).hexdigest()

def check_duplicate_upload(df_t: pd.DataFrame) -> Optional[str]:
    """
    Checks if an identical transaction ledger already exists in the system.
    Returns the existing session_id if found, else None.
    """
    ledger_hash = _compute_ledger_hash(df_t)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT session_id FROM sessions WHERE data_hash = ?", (ledger_hash,))
        row = cursor.fetchone()
        return row[0] if row else None

def save_session(session_id: str, df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool, pan_id: str = None, upload_type: str = 'mutual_funds') -> str:
    """
    Persists the dataframes to SQLite and registers the session, tied to a PAN.
    """
    ledger_hash = _compute_ledger_hash(df_t)
    
    # 1. Save DataFrames to SQLite
    with sqlite3.connect(DB_PATH) as conn:
        if not df_h.empty:
            df_h_copy = df_h.copy()
            df_h_copy['session_id'] = session_id
            df_h_copy.to_sql("mf_holdings", conn, if_exists="append", index=False)
            
        if not df_t.empty:
            df_t_copy = df_t.copy()
            df_t_copy['session_id'] = session_id
            df_t_copy.to_sql("mf_transactions", conn, if_exists="append", index=False)
            
        if not df_s.empty:
            df_s_copy = df_s.copy()
            df_s_copy['session_id'] = session_id
            df_s_copy.to_sql("mf_sips", conn, if_exists="append", index=False)
    
    # 2. Extract quick metrics for the registry
    total_value = float(df_h["Market Value"].sum()) if not df_h.empty and "Market Value" in df_h.columns else 0.0
    total_invested = float(df_h["Invested"].sum()) if not df_h.empty and "Invested" in df_h.columns else 0.0
    num_funds = len(df_h)
    
    # 3. Save to SQLite Registry
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO sessions (session_id, data_hash, total_value, total_invested, num_funds, is_partial, pan_id, upload_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, ledger_hash, total_value, total_invested, num_funds, is_partial, pan_id, upload_type))
        conn.commit()
        
    return session_id

def load_session(session_id: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]]:
    """
    Reconstructs the portfolio from SQLite using the session_id.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Check if session exists
            cursor = conn.execute("SELECT is_partial FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            is_partial = bool(row[0])
            
            # Read dataframes
            try:
                df_h = pd.read_sql(f"SELECT * FROM mf_holdings WHERE session_id='{session_id}'", conn)
                df_h.drop(columns=['session_id'], inplace=True, errors='ignore')
            except Exception:
                df_h = pd.DataFrame()
                
            try:
                df_t = pd.read_sql(f"SELECT * FROM mf_transactions WHERE session_id='{session_id}'", conn)
                df_t.drop(columns=['session_id'], inplace=True, errors='ignore')
            except Exception:
                df_t = pd.DataFrame()
                
            try:
                df_s = pd.read_sql(f"SELECT * FROM mf_sips WHERE session_id='{session_id}'", conn)
                df_s.drop(columns=['session_id'], inplace=True, errors='ignore')
            except Exception:
                df_s = pd.DataFrame()
                
        return df_h, df_t, df_s, is_partial
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to load session {session_id}: {str(e)}")
        return None

def get_history(pan_id: str = None, upload_type: str = None) -> list:
    """
    Returns a chronological list of all uploaded CAS sessions for a given PAN and upload_type.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        
        if pan_id:
            query += " AND pan_id = ?"
            params.append(pan_id)
            
        if upload_type:
            query += " AND upload_type = ?"
            params.append(upload_type)
            
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def delete_session(session_id: str) -> bool:
    """
    Deletes a session from the SQLite registry and its associated dataframes.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            try:
                conn.execute("DELETE FROM mf_holdings WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM mf_transactions WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM mf_sips WHERE session_id = ?", (session_id,))
            except sqlite3.OperationalError:
                pass # Tables might not exist yet
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"[STORAGE ERROR] Failed to delete session {session_id}: {str(e)}")
        return False

def delete_all_for_pan(pan_id: str) -> int:
    """
    Deletes all sessions associated with a given PAN.
    Returns the number of sessions deleted.
    """
    count = 0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT session_id FROM sessions WHERE pan_id = ?", (pan_id,))
        sessions = [row[0] for row in cursor.fetchall()]
        
        for sid in sessions:
            if delete_session(sid):
                count += 1
                
    return count
