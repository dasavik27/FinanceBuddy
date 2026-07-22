from fastapi import APIRouter, HTTPException, Header
from core import storage
import pandas as pd
from typing import Dict, Any

router = APIRouter()

@router.get("/")
def get_upload_history(x_user_pan: str = Header(None), x_upload_type: str = Header("mutual_funds")):
    """
    Returns the chronological timeline of all CAS uploads filtered by PAN and upload type.
    """
    history = storage.get_history(pan_id=x_user_pan, upload_type=x_upload_type)
    return {"status": "success", "history": history}

@router.delete("/{session_id}")
def delete_session(session_id: str):
    """
    Deletes a specific session from history and disk.
    """
    success = storage.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session.")
    return {"status": "success", "deleted_session_id": session_id}

def _hash_transaction(row: pd.Series) -> str:
    """Helper to generate a deterministic hash for a single transaction row."""
    import hashlib
    # The 'Type' field is excluded from the hash to ensure idempotency. Parsing engines 
    # may occasionally append semantic labels (e.g., '(Auto-Detected)') to identical 
    # transactions across different statement generations.
    raw = f"{row['Date']}_{row.get('Fund', '')}_{round(row.get('Units', 0.0), 3)}_{round(row.get('Amount', 0.0), 2)}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

@router.get("/compare/{session_id_a}/vs/{session_id_b}")
def compare_sessions(session_id_a: str, session_id_b: str):
    """
    Performs Transaction Ledger Reconciliation between two CAS uploads.
    Identifies exact semantic deltas (new transactions) instead of just value changes.
    """
    # Ensure chronological order (A is always older, B is always newer)
    history_list = storage.get_history()
    meta_a = next((h for h in history_list if h["session_id"] == session_id_a), None)
    meta_b = next((h for h in history_list if h["session_id"] == session_id_b), None)
    
    if not meta_a or not meta_b:
        raise HTTPException(status_code=404, detail="Session metadata not found.")
        
    # Load raw data first
    data_a_raw = storage.load_session(session_id_a)
    data_b_raw = storage.load_session(session_id_b)
    
    if not data_a_raw: raise HTTPException(status_code=404, detail=f"Session A ({session_id_a}) not found.")
    if not data_b_raw: raise HTTPException(status_code=404, detail=f"Session B ({session_id_b}) not found.")
    
    df_t_a_raw = data_a_raw[1]
    df_t_b_raw = data_b_raw[1]
    
    # Determine True Chronology based on Latest Transaction Date instead of Upload Time
    max_date_a = df_t_a_raw["Date"].max() if not df_t_a_raw.empty and "Date" in df_t_a_raw.columns else pd.to_datetime(meta_a["created_at"])
    max_date_b = df_t_b_raw["Date"].max() if not df_t_b_raw.empty and "Date" in df_t_b_raw.columns else pd.to_datetime(meta_b["created_at"])
    
    if max_date_a > max_date_b:
        # Realign datasets to maintain chronological integrity, ensuring Session A 
        # always serves as the older temporal baseline for delta calculation.
        session_id_a, session_id_b = session_id_b, session_id_a
        data_a_raw, data_b_raw = data_b_raw, data_a_raw
        max_date_a, max_date_b = max_date_b, max_date_a

    # Unpack mathematically validated Old vs New data
    df_h_a, df_t_a, df_s_a, _ = data_a_raw
    df_h_b, df_t_b, df_s_b, _ = data_b_raw
    
    # Generate row-level hashes for Session A
    if not df_t_a.empty:
        df_t_a['tx_hash'] = df_t_a.apply(_hash_transaction, axis=1)
        hashes_a = set(df_t_a['tx_hash'].tolist())
    else:
        hashes_a = set()
        
    # Generate row-level hashes for Session B
    if not df_t_b.empty:
        df_t_b['tx_hash'] = df_t_b.apply(_hash_transaction, axis=1)
        # Find transactions in B that are NOT in A
        new_tx_df = df_t_b[~df_t_b['tx_hash'].isin(hashes_a)].copy()
        
        # Apply a strict chronological filter to exclude backfilled transactions or 
        # historical data injected due to structural disparities between the two datasets. 
        # This guarantees the delta only reflects true forward-moving temporal events.
        new_tx_df['Date'] = pd.to_datetime(new_tx_df['Date'])
        new_tx_df = new_tx_df[new_tx_df['Date'] > max_date_a].copy()
    else:
        new_tx_df = pd.DataFrame()
        
    # Summarize the exact financial events
    events = []
    if not new_tx_df.empty:
        # Sort by date
        new_tx_df = new_tx_df.sort_values(by="Date")
        for _, row in new_tx_df.iterrows():
            tx_type = str(row.get("Type", "Transaction"))
            
            # Exclude structural boundary markers ('Opening Balance', 'Closing Balance') 
            # which are artifacts of the statement generation period rather than true financial events.
            if "opening" in tx_type.lower() or "closing" in tx_type.lower():
                continue
                
            events.append({
                "date": row["Date"].strftime("%Y-%m-%d") if pd.notnull(row["Date"]) else "Unknown",
                "fund": row.get("Fund", "Unknown Fund"),
                "type": tx_type,
                "amount": float(row.get("Amount", 0.0)),
                "units": float(row.get("Units", 0.0))
            })
            
    # Calculate high-level deltas
    val_a = float(df_h_a["Market Value"].sum()) if not df_h_a.empty and "Market Value" in df_h_a.columns else 0.0
    val_b = float(df_h_b["Market Value"].sum()) if not df_h_b.empty and "Market Value" in df_h_b.columns else 0.0
    
    inv_a = float(df_h_a["Invested"].sum()) if not df_h_a.empty and "Invested" in df_h_a.columns else 0.0
    inv_b = float(df_h_b["Invested"].sum()) if not df_h_b.empty and "Invested" in df_h_b.columns else 0.0
    
    from core.finance import compute_xirr
    xirr_a = float(compute_xirr(df_t_a, val_a)) if val_a > 0 else 0.0
    xirr_b = float(compute_xirr(df_t_b, val_b)) if val_b > 0 else 0.0

    # Aggregate total Income Distribution cum Capital Withdrawal (IDCW) payouts
    dividends = sum(abs(tx["amount"]) for tx in events if "dividend" in tx["type"].lower() or "payout" in tx["type"].lower() or "idcw" in tx["type"].lower())

    # Calculate strictly isolated organic valuation shifts per fund by stripping net capital flows
    organic_growth_by_fund = {}
    if not df_h_b.empty and not df_h_a.empty:
        for _, row_b in df_h_b.iterrows():
            fund_name = row_b.get("Fund", "")
            if not fund_name: continue
            
            val_b_fund = float(row_b.get("Market Value", 0.0))
            # Find in A
            row_a = df_h_a[df_h_a["Fund"] == fund_name]
            val_a_fund = float(row_a.iloc[0].get("Market Value", 0.0)) if not row_a.empty else 0.0
            
            # Find net flow into this fund during this period
            fund_events = [tx for tx in events if tx["fund"] == fund_name]
            fund_bought = sum(abs(tx["amount"]) for tx in fund_events if tx["units"] > 0 or "purchase" in tx["type"].lower() or "sip" in tx["type"].lower() or "reinvestment" in tx["type"].lower() or "stamp" in tx["type"].lower())
            fund_sold = sum(abs(tx["amount"]) for tx in fund_events if tx["units"] < 0 or "redemption" in tx["type"].lower() or "switch out" in tx["type"].lower())
            fund_net_flow = fund_bought - fund_sold
            
            organic_growth = (val_b_fund - val_a_fund) - fund_net_flow
            organic_growth_by_fund[fund_name] = organic_growth

    active_funds = df_h_b["Fund"].tolist() if not df_h_b.empty else []

    return {
        "status": "success",
        "baseline_session": session_id_a,
        "current_session": session_id_b,
        "deltas": {
            "portfolio_value_change": val_b - val_a,
            "capital_invested_change": inv_b - inv_a,
            "xirr_shift": xirr_b - xirr_a,
            "dividends": dividends,
            "organic_growth_by_fund": organic_growth_by_fund
        },
        "active_funds": active_funds,
        "new_transactions_count": len(events),
        "new_transactions": events
    }
