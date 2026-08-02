import json
import zlib
import pandas as pd
import io
import uuid
from typing import Tuple, Dict

from shared import crypto, db

def _compress_frame(df: pd.DataFrame) -> bytes:
    if df.empty:
        return b""
    df_copy = df.copy()
    if 'date' in df_copy.columns:
        df_copy['date'] = df_copy['date'].astype(str)
    return zlib.compress(df_copy.to_json(orient="records").encode("utf-8"))

def _decompress_frame(b: bytes) -> pd.DataFrame:
    if not b:
        return pd.DataFrame()
    json_str = zlib.decompress(b).decode("utf-8")
    df = pd.read_json(io.StringIO(json_str), orient="records")
    if not df.empty and 'date' in df.columns:
        try:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d').fillna(df['date'].astype(str))
        except Exception:
            df['date'] = df['date'].astype(str)
    return df
def save_budget_session(session_id: str, user_id: str, df: pd.DataFrame, accounts: dict):
    compressed = _compress_frame(df)
    encrypted_txns = crypto.encrypt(compressed, aad=session_id)
    
    metrics = {
        "total_income": float(df[df["type"] == "credit"]["amount"].sum()) if not df.empty else 0.0,
        "total_expense": float(df[df["type"] == "debit"]["amount"].sum()) if not df.empty else 0.0,
    }
    encrypted_metrics = crypto.encrypt_json(metrics, aad=session_id)
    accounts_json = json.dumps(accounts)
    
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO sessions (
                session_id, user_id, upload_type, data_hash,
                metrics, is_partial, statement_period
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (session_id) DO NOTHING
        """, (
            session_id, user_id, "budget", session_id,
            encrypted_metrics, False, ""
        ))
        
        conn.execute("""
            INSERT INTO budget_payloads (
                session_id, codec, transactions, accounts, byte_size
            ) VALUES (
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (session_id) DO UPDATE SET
                transactions = EXCLUDED.transactions,
                accounts = EXCLUDED.accounts,
                byte_size = EXCLUDED.byte_size,
                updated_at = now()
        """, (
            session_id, "zlib_json", encrypted_txns, accounts_json, len(compressed)
        ))

def get_budget_session(session_id: str) -> Tuple[pd.DataFrame, dict]:
    with db.connect() as conn:
        row = conn.execute("""
            SELECT transactions, accounts FROM budget_payloads WHERE session_id = %s
        """, (session_id,)).fetchone()
        
    if not row:
        return pd.DataFrame(), {}
        
    encrypted_txns, accounts = row
    
    if encrypted_txns:
        decrypted_txns = crypto.decrypt(encrypted_txns, aad=session_id)
        df = _decompress_frame(decrypted_txns)
    else:
        df = pd.DataFrame()
        
    return df, accounts if isinstance(accounts, dict) else json.loads(accounts)

def get_all_budget_sessions(user_id: str) -> Tuple[pd.DataFrame, Dict]:
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT b.transactions, s.session_id, b.accounts
            FROM budget_payloads b
            JOIN sessions s ON b.session_id = s.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
        """, (user_id,)).fetchall()
        
    all_dfs = []
    all_accounts = {}
    
    for txns_bytes, sid, accounts_json in rows:
        decrypted = crypto.decrypt(txns_bytes, aad=sid)
        df = _decompress_frame(decrypted)
        if not df.empty:
            df["session_id"] = sid
            
            # Ensure newer columns exist for old sessions
            if "txn_id" not in df.columns:
                df["txn_id"] = [uuid.uuid4().hex for _ in range(len(df))]
            if "source_bank" not in df.columns or df["source_bank"].isna().all():
                fn = (accounts_json.get("filename") if isinstance(accounts_json, dict) else "") or ""
                if "acct" in fn.lower() or "hdfc" in fn.lower():
                    df["source_bank"] = "HDFC"
                elif "optransaction" in fn.lower() or "icici" in fn.lower():
                    df["source_bank"] = "ICICI"
                elif "sbi" in fn.lower():
                    df["source_bank"] = "SBI"
                else:
                    df["source_bank"] = "GENERIC"
            if "account_type" not in df.columns or df["account_type"].isna().all():
                fn = (accounts_json.get("filename") if isinstance(accounts_json, dict) else "") or ""
                acc_type_meta = accounts_json.get("account_type") if isinstance(accounts_json, dict) else None
                if acc_type_meta:
                    df["account_type"] = acc_type_meta
                elif any(w in fn.lower() for w in ["credit card", "creditcard", "card", "cc_"]):
                    df["account_type"] = "Credit Card"
                elif "current" in fn.lower():
                    df["account_type"] = "Current Account"
                elif "salary" in fn.lower():
                    df["account_type"] = "Salary Account"
                else:
                    df["account_type"] = "Savings Account"
            else:
                df["account_type"] = df["account_type"].fillna("Savings Account").astype(str)
                
            all_dfs.append(df)
        if accounts_json:
            all_accounts.update(accounts_json)
            
    if not all_dfs:
        return pd.DataFrame(), {}
        
    master_df = pd.concat(all_dfs, ignore_index=True)
    
    # Deduplicate overlapping statements per bank and account type
    if not master_df.empty:
        if 'date' in master_df.columns:
            try:
                master_df['date'] = pd.to_datetime(master_df['date'], errors='coerce').dt.strftime('%Y-%m-%d').fillna(master_df['date'].astype(str))
            except Exception:
                master_df['date'] = master_df['date'].astype(str)
        if 'source_bank' not in master_df.columns:
            master_df['source_bank'] = 'GENERIC'
        else:
            master_df['source_bank'] = master_df['source_bank'].fillna('GENERIC').astype(str).str.upper()
        if 'account_type' not in master_df.columns:
            master_df['account_type'] = 'Savings Account'
        else:
            master_df['account_type'] = master_df['account_type'].fillna('Savings Account').astype(str)
            
        # Sort by date so we keep the most recent if we drop duplicates (just to be consistent)
        master_df = master_df.sort_values(by=["date"]).drop_duplicates(
            subset=["date", "description", "amount", "type", "source_bank", "account_type"], 
            keep="last"
        )
        
    return master_df, all_accounts

def update_budget_transactions(user_id: str, session_id: str, updates: list) -> bool:
    """
    Updates specific transactions within a session payload.
    updates is a list of dicts: [{"txn_id": "...", "category": "...", "notes": "..."}, ...]
    """
    with db.connect() as conn:
        row = conn.execute("""
            SELECT b.transactions, b.accounts
            FROM budget_payloads b
            JOIN sessions s ON b.session_id = s.session_id
            WHERE s.session_id = %s AND s.user_id = %s
        """, (session_id, user_id)).fetchone()
        
        if not row:
            return False
            
        txns_bytes, accounts_json = row
        decrypted = crypto.decrypt(txns_bytes, aad=session_id)
        df = _decompress_frame(decrypted)
        
        if df.empty or "txn_id" not in df.columns:
            return False
            
        # Apply updates
        for u in updates:
            txn_id = u.get("txn_id")
            if not txn_id:
                continue
            idx = df.index[df["txn_id"] == txn_id]
            if not idx.empty:
                if "category" in u:
                    df.loc[idx, "category"] = u["category"]
                if "notes" in u:
                    df.loc[idx, "notes"] = u["notes"]
                    
        # Save back
        new_payload = crypto.encrypt(_compress_frame(df), aad=session_id)
        conn.execute("""
            UPDATE budget_payloads 
            SET transactions = %s, updated_at = now()
            WHERE session_id = %s
        """, (new_payload, session_id))
        
    return True

def reapply_rules_to_all_sessions(user_id: str) -> int:
    """
    Re-runs all user & default categorization rules across all past uploaded sessions.
    """
    from domains.budget.categorizer import categorize_transactions
    total_updated = 0
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT s.session_id, b.transactions, b.accounts
            FROM sessions s
            JOIN budget_payloads b ON s.session_id = b.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
        """, (user_id,)).fetchall()
        
        for sid, txns_bytes, accounts_json in rows:
            decrypted = crypto.decrypt(txns_bytes, aad=sid)
            df = _decompress_frame(decrypted)
            if not df.empty:
                df = categorize_transactions(df, user_id)
                compressed = _compress_frame(df)
                encrypted = crypto.encrypt(compressed, aad=sid)
                
                conn.execute("""
                    UPDATE budget_payloads
                    SET transactions = %s, byte_size = %s, updated_at = now()
                    WHERE session_id = %s
                """, (encrypted, len(compressed), sid))
                total_updated += len(df)
                
    return total_updated

def list_budget_sessions(user_id: str) -> list:
    """
    Lists all past budget uploads for the given user, with metadata and summary metrics.
    """
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT s.session_id, s.created_at, b.accounts, s.metrics, b.transactions
            FROM sessions s
            JOIN budget_payloads b ON s.session_id = b.session_id
            WHERE s.user_id = %s AND s.upload_type = 'budget'
            ORDER BY s.created_at DESC
        """, (user_id,)).fetchall()
        
    results = []
    for sid, created_at, accounts_json, enc_metrics, txns_bytes in rows:
        acc = accounts_json if isinstance(accounts_json, dict) else (json.loads(accounts_json) if accounts_json else {})
        filename = acc.get("filename", "Bank Statement")
        row_count = acc.get("rows", 0)
        
        income = 0.0
        expense = 0.0
        bank_name = "GENERIC"
        
        try:
            if enc_metrics:
                dec_metrics = crypto.decrypt_json(enc_metrics, aad=sid)
                income = float(dec_metrics.get("total_income", 0.0))
                expense = float(dec_metrics.get("total_expense", 0.0))
        except Exception:
            pass
            
        try:
            if txns_bytes:
                df = _decompress_frame(crypto.decrypt(txns_bytes, aad=sid))
                if not df.empty:
                    row_count = len(df)
                    if income == 0 and expense == 0:
                        income = float(df[df["type"] == "credit"]["amount"].sum())
                        expense = float(df[df["type"] == "debit"]["amount"].sum())
                    if "source_bank" in df.columns:
                        bank_val = df["source_bank"].dropna().unique()
                        if len(bank_val) > 0:
                            bank_name = str(bank_val[0]).upper()
        except Exception:
            pass

        if bank_name == "GENERIC":
            if "acct" in filename.lower() or "hdfc" in filename.lower():
                bank_name = "HDFC"
            elif "optransaction" in filename.lower() or "icici" in filename.lower():
                bank_name = "ICICI"
            elif "sbi" in filename.lower():
                bank_name = "SBI"
                
        acc_type = acc.get("account_type", "Savings Account")
        if "card" in filename.lower() or "cc" in filename.lower():
            acc_type = "Credit Card"

        results.append({
            "session_id": sid,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            "filename": filename,
            "bank": bank_name,
            "account_type": acc_type,
            "rows": row_count,
            "total_income": income,
            "total_expense": expense,
            "net_savings": income - expense
        })
    return results

def delete_budget_session(user_id: str, session_id: str) -> bool:
    """
    Deletes a specific budget session and its payload.
    """
    with db.connect() as conn:
        conn.execute("""
            DELETE FROM budget_payloads WHERE session_id = %s
        """, (session_id,))
        conn.execute("""
            DELETE FROM sessions WHERE session_id = %s AND user_id = %s
        """, (session_id, user_id))
    return True
