"""
CAS Parser and Fund Detection
Handles CAMS/KFintech PDF parsing and fund metadata detection
"""

import pandas as pd
import streamlit as st
import casparser
import os
from datetime import datetime


def _get(obj, key, default=None):
    """Safe getter for dict/object attributes."""
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return val if val is not None else default
    val = getattr(obj, key, default)
    return val if val is not None else default


@st.cache_data(show_spinner=False)
def parse_cas(file_bytes: bytes, password: str):
    """Parse CAMS/KFintech CAS PDF. Zero disk retention after parsing."""
    try:
        with open("_vault_tmp.pdf", "wb") as f:
            f.write(file_bytes)

        data = casparser.read_cas_pdf("_vault_tmp.pdf", password)

        try:
            os.remove("_vault_tmp.pdf")
        except Exception:
            pass

        if "accounts" in data:
            return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 
                   "NSDL CAS detected. FolioIQ requires a CAMS/KFintech Detailed CAS for transaction analytics.",
                   False)
            
        folios = _get(data, 'folios', [])
        if not folios:
            return (pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                   "No folios found in CAS. Make sure this is a 'Detailed' CAS.", False)
            
        holdings = []
        txns = []
        sips = []
        is_partial_cas = False

        for folio in folios:
            schemes = _get(folio, 'schemes', [])
            for scheme in schemes:
                name = _get(scheme, 'scheme', "Unknown Scheme")
                isin = _get(scheme, 'isin', "N/A") or "N/A"
                bal = float(_get(scheme, 'close_calculated', _get(scheme, 'close', 0)) or 0)
                
                open_bal = float(_get(scheme, 'open', 0) or 0)
                if open_bal > 0:
                    is_partial_cas = True
                    
                if not bal:
                    txs = _get(scheme, 'transactions', []) or []
                    if txs:
                        bal = float(_get(txs[-1], 'balance', 0) or 0)
                        
                val_obj = _get(scheme, 'valuation', {})
                cur_val = float(_get(val_obj, 'value', 0) or 0)
                nav = float(_get(val_obj, 'nav', 0) or 0) if val_obj else 0
                cost = float(_get(val_obj, 'cost', 0) or 0)

                category = detect_category(name)
                plan = "Regular" if any(x in name.upper() for x in ["REGULAR", "REG "]) else "Direct"
                amc = detect_amc(name)
                cap_type = detect_cap_type(name)

                if bal > 0 or cur_val > 0:
                    invested = cost if cost > 0 else estimate_invested(scheme)
                    holdings.append({
                        "Fund": name,
                        "ISIN": isin,
                        "AMC": amc,
                        "Category": category,
                        "Plan": plan,
                        "Cap Type": cap_type,
                        "Units": bal,
                        "NAV": nav,
                        "Market Value": cur_val,
                        "Invested": invested,
                        "Gain": cur_val - invested,
                        "Gain%": ((cur_val - invested) / invested * 100) if invested > 0 else 0,
                        "Weight%": 0.0,
                    })

                txs_raw = _get(scheme, 'transactions', [])
                for tx in txs_raw:
                    t_date = _get(tx, 'date', None)
                    t_amt = _get(tx, 'amount', 0)
                    t_type = _get(tx, 'type', 'N/A') or 'N/A'
                    t_nav = _get(tx, 'nav', 0) or 0
                    t_units = _get(tx, 'units', 0) or 0
                    if t_date:
                        txns.append({
                            "Fund": name,
                            "AMC": amc,
                            "Category": category,
                            "Date": pd.to_datetime(t_date),
                            "Amount": float(t_amt or 0),
                            "Type": str(t_type),
                            "NAV": float(t_nav),
                            "Units": float(t_units),
                        })
                        if "SIP" in str(t_type).upper() or "SYSTEMATIC" in str(t_type).upper():
                            sips.append({
                                "Fund": name,
                                "AMC": amc,
                                "Date": pd.to_datetime(t_date),
                                "Amount": abs(float(t_amt or 0)),
                                "NAV": float(t_nav),
                            })

        df_h = pd.DataFrame(holdings)
        if not df_h.empty:
            total_val = df_h["Market Value"].sum()
            if total_val > 0:
                df_h["Weight%"] = df_h["Market Value"] / total_val * 100

        df_t = pd.DataFrame(txns)
        df_s = pd.DataFrame(sips)
        return df_h, df_t, df_s, None, is_partial_cas

    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), str(e), False


def detect_category(name: str) -> str:
    """Detect fund category from scheme name."""
    n = name.upper()
    if "ELSS" in n or "TAX SAVER" in n or "TAX SAVING" in n:
        return "ELSS"
    if any(x in n for x in ["LIQUID", "OVERNIGHT", "MONEY MARKET", "ULTRA SHORT"]):
        return "Liquid"
    if any(x in n for x in ["DEBT", "BOND", "GILT", "INCOME", "CREDIT RISK", "CORPORATE BOND", "BANKING AND PSU"]):
        return "Debt"
    if any(x in n for x in ["HYBRID", "BALANCED", "CONSERVATIVE", "AGGRESSIVE HYBRID", "EQUITY SAVINGS", "ARBITRAGE"]):
        return "Hybrid"
    if any(x in n for x in ["INDEX", "NIFTY", "SENSEX", "ETF", "FTF"]):
        return "Index"
    if "FOF" in n or "FUND OF FUND" in n or "OVERSEAS" in n or "INTERNATIONAL" in n:
        return "FOF"
    if any(x in n for x in ["EQUITY", "FLEXI", "MULTI CAP", "LARGE CAP", "MID CAP", "SMALL CAP",
                              "SECTORAL", "THEMATIC", "FOCUSED", "VALUE", "CONTRA", "DIVIDEND YIELD"]):
        return "Equity"
    return "Other"


def detect_cap_type(name: str) -> str:
    """Detect capitalization type from scheme name."""
    n = name.upper()
    if "SMALL CAP" in n:
        return "Small Cap"
    if "MID CAP" in n or "MIDCAP" in n:
        return "Mid Cap"
    if "LARGE CAP" in n or "LARGECAP" in n:
        return "Large Cap"
    if "FLEXI CAP" in n or "MULTI CAP" in n:
        return "Flexi/Multi Cap"
    if "INDEX" in n or "NIFTY 50" in n or "SENSEX" in n:
        return "Index"
    return "Mixed"


def detect_amc(name: str) -> str:
    """Detect AMC from scheme name."""
    amcs = {
        "Mirae": "Mirae Asset", "HDFC": "HDFC", "SBI": "SBI",
        "Axis": "Axis", "ICICI": "ICICI Prudential", "Kotak": "Kotak",
        "Nippon": "Nippon India", "DSP": "DSP", "Parag Parikh": "PPFAS",
        "Motilal": "Motilal Oswal", "Franklin": "Franklin Templeton",
        "Aditya Birla": "Aditya Birla SL", "UTI": "UTI", "Tata": "Tata",
        "Canara": "Canara Robeco", "Edelweiss": "Edelweiss",
        "Invesco": "Invesco", "L&T": "L&T", "BOI": "BOI AXA",
        "Sundaram": "Sundaram", "PGIM": "PGIM India", "Quant": "Quant",
    }
    for k, v in amcs.items():
        if k.upper() in name.upper():
            return v
    return "Other AMC"


def estimate_invested(scheme) -> float:
    """Estimate invested amount using average cost calculation."""
    try:
        txs = _get(scheme, 'transactions', [])
        current_units = 0.0
        avg_cost = 0.0
        for tx in txs:
            amt = abs(float(_get(tx, 'amount', 0) or 0))
            units = float(_get(tx, 'units', 0) or 0)
            
            if units > 0:
                new_units = current_units + units
                if new_units > 0:
                    avg_cost = (current_units * avg_cost + amt) / new_units
                current_units = new_units
            elif units < 0:
                current_units += units
                if current_units <= 1e-6:
                    current_units = 0.0
                    avg_cost = 0.0
        
        return current_units * avg_cost
    except Exception:
        return 0.0
