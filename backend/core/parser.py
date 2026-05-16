"""
core/parser.py
Mutual Fund CAS parsing and metadata detection.
"""

import casparser
import pandas as pd
import os
import tempfile
from typing import Tuple, Optional
from services.market_data import fetch_live_navs

def _get(obj, key, default=None):
    """Robust helper to get attributes from dicts or objects."""
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return val if val is not None else default
    val = getattr(obj, key, default)
    return val if val is not None else default

def parse_cas_file(file_bytes: bytes, password: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Optional[str], bool]:
    """Parse CAMS/KFintech CAS PDF. Zero disk retention after parsing."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_bytes)
        temp_path = tmp.name

    print(f"[DEBUG] Starting CAS parse. Bytes: {len(file_bytes)}")
    try:
        try:
            data = casparser.read_cas_pdf(temp_path, password)
            print("[DEBUG] CASParser success.")
        except Exception as e:
            print(f"[DEBUG] CASParser ERROR: {e}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), f"CASParser Error: {str(e)}", False
        finally:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

        folios = _get(data, 'folios', [])
        print(f"[DEBUG] Found {len(folios)} folios.")
        if not folios:
            # Check if it's a 'data' object but empty
            if hasattr(data, 'folios') and not data.folios:
                return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "No folios found in CAS. Check your PDF.", False
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "Failed to extract folios from PDF.", False
            
        holdings, txns, sips = [], [], []
        
        # Performance optimization: Fetch live NAVs once
        try:
            live_nav_map = fetch_live_navs()
        except:
            live_nav_map = {}
            
        is_partial = False

        for folio in folios:
            for scheme in _get(folio, 'schemes', []):
                name = _get(scheme, 'scheme', "Unknown Fund")
                isin = _get(scheme, 'isin', "N/A")
                
                # Robust numeric extraction
                def to_f(v):
                    try: return float(v) if v is not None else 0.0
                    except: return 0.0

                bal = to_f(_get(scheme, 'close', 0))
                
                if to_f(_get(scheme, 'open', 0)) > 0:
                    is_partial = True

                if bal <= 0:
                    txs = _get(scheme, 'transactions', [])
                    if txs:
                        bal = to_f(_get(txs[-1], 'balance', 0))
                
                nav_obj = _get(scheme, 'valuation', {})
                nav = to_f(_get(nav_obj, 'nav', 0))
                if isin in live_nav_map:
                    nav = live_nav_map[isin]
                
                # --- EXACT-FIRST METADATA DETECTION ---
                raw_cat = _get(scheme, 'category', "")
                raw_type = _get(scheme, 'type', "")
                raw_amc = _get(folio, 'amc', "") # Some CAS have AMC at folio level
                
                # Use engine to resolve/normalize raw values
                category = CategorizationEngine.detect_category(name, raw_cat, raw_type)
                amc = CategorizationEngine.detect_amc(name, raw_amc)
                plan = CategorizationEngine.detect_plan(name)
                cap_type = CategorizationEngine.detect_cap_type(name, category, raw_cat)
                
                cur_val = bal * nav
                
                if bal > 0 or cur_val > 0:
                    holdings.append({
                        "Fund": name, "ISIN": isin, "Category": category,
                        "Units": bal, "NAV": nav, "Market Value": cur_val,
                        "AMC": amc, "Plan": plan,
                        "Cap Type": cap_type,
                        "Invested": _estimate_invested(scheme),
                    })
                
                for tx in _get(scheme, 'transactions', []):
                    tx_amt = to_f(_get(tx, 'amount', 0))
                    tx_units = to_f(_get(tx, 'units', 0))
                    tx_nav = to_f(_get(tx, 'nav', 0))
                    tx_date = _get(tx, 'date')
                    tx_type = str(_get(tx, 'type', 'N/A'))
                    
                    if tx_date:
                        dt = pd.to_datetime(tx_date, dayfirst=True)
                        txns.append({
                            "Fund": name, "Date": dt,
                            "Amount": tx_amt, "Type": tx_type,
                            "Units": tx_units, "NAV": tx_nav
                        })
                        if "SIP" in tx_type.upper():
                            sips.append({"Fund": name, "Date": dt, "Amount": abs(tx_amt)})

        df_h = pd.DataFrame(holdings)
        if not df_h.empty:
            # Ensure types are correct
            df_h["Market Value"] = df_h["Market Value"].astype(float)
            df_h["Invested"] = df_h["Invested"].astype(float)
            df_h["Gain"] = df_h["Market Value"] - df_h["Invested"]
            df_h["Gain%"] = (df_h["Gain"] / df_h["Invested"] * 100).fillna(0)
            df_h["Weight%"] = (df_h["Market Value"] / df_h["Market Value"].sum() * 100)

        return df_h, pd.DataFrame(txns), pd.DataFrame(sips), None, is_partial
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), str(e), False

from core.logic import CategorizationEngine

def _estimate_invested(scheme) -> float:
    """
    Institutional FIFO Cost Basis Engine.
    Tracks precise acquisition cost for currently held units only.
    Handles partial redemptions using First-In-First-Out (FIFO) methodology
    to ensure gain calculations match regulatory standards.
    """
    txs = _get(scheme, 'transactions', [])
    if not txs: return 0.0
    
    # Sort by date
    sorted_txs = sorted(txs, key=lambda x: pd.to_datetime(_get(x, 'date', '2000-01-01'), dayfirst=True))
    
    active_buys = [] # List of [units, cost_per_unit]
    
    for tx in sorted_txs:
        u   = float(_get(tx, 'units', 0) or 0)
        a   = abs(float(_get(tx, 'amount', 0) or 0))
        nav = float(_get(tx, 'nav', 0) or 0)

        # Impute amount for SWITCH or transfer transactions using NAV basis
        # ensures cost integrity for records missing explicit monetary values.
        if a == 0 and u != 0 and nav > 0:
            a = abs(u * nav)

        if u > 0:
            # Buy: Add to FIFO queue
            active_buys.append([u, a / u])
        elif u < 0:
            # Sell: Remove from FIFO queue (oldest first)
            sell_u = abs(u)
            while sell_u > 0 and active_buys:
                if active_buys[0][0] <= sell_u:
                    sell_u -= active_buys[0][0]
                    active_buys.pop(0)
                else:
                    active_buys[0][0] -= sell_u
                    sell_u = 0
                    
    # Current cost basis = remaining units * their original buy price
    cost_basis = sum(b[0] * b[1] for b in active_buys)
    return round(cost_basis, 2)
