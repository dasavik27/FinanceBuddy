"""
core/storage.py

Data Lake Persistence & Transaction Ledger Reconciliation Engine
================================================================
Manages robust disk-level storage of CAS uploaded DataFrames using highly compressed Parquet
files, mapped against an SQLite metadata registry. Includes a deterministic row-level hashing
engine to prevent duplicate snapshots and allow semantic ledger reconciliation.
"""

import os
import json
import sqlite3
import pandas as pd
import hashlib
from typing import Optional, Dict, Any, Tuple

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
    Persists the dataframes as Parquet files and registers the session in SQLite, tied to a PAN.
    """
    ledger_hash = _compute_ledger_hash(df_t)
    
    # 1. Save DataFrames to Parquet (Fast, Compressed)
    session_dir = os.path.join(SESSIONS_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    df_h.to_parquet(os.path.join(session_dir, "df_h.parquet"), index=False)
    df_t.to_parquet(os.path.join(session_dir, "df_t.parquet"), index=False)
    df_s.to_parquet(os.path.join(session_dir, "df_s.parquet"), index=False)
    
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
    Reconstructs the portfolio from disk using the session_id.
    """
    session_dir = os.path.join(SESSIONS_DIR, session_id)
    if not os.path.exists(session_dir):
        return None
        
    try:
        df_h = pd.read_parquet(os.path.join(session_dir, "df_h.parquet"))
        df_t = pd.read_parquet(os.path.join(session_dir, "df_t.parquet"))
        df_s = pd.read_parquet(os.path.join(session_dir, "df_s.parquet"))
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT is_partial FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            is_partial = bool(row[0]) if row else False
            
        return df_h, df_t, df_s, is_partial
    except Exception as e:
        print(f"[STORAGE ERROR] Failed to load session {session_id}: {str(e)}")
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
    Deletes a session from the SQLite registry and removes its Parquet files from disk.
    """
    import shutil
    
    # 1. Remove from SQLite
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        
    # 2. Remove from Disk
    session_dir = os.path.join(SESSIONS_DIR, session_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
            return True
        except Exception as e:
            print(f"[STORAGE ERROR] Failed to delete session directory {session_id}: {str(e)}")
            return False
    return True
