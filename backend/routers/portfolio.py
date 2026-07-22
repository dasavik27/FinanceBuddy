"""
routers/portfolio.py
Session lifecycle and CAS parsing gateway.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header
from core.parser import parse_cas_file
from core.sessions import create_session
from core.config import BENCHMARKS, TEST_PASSWORD

router = APIRouter()

@router.post("/parse")
async def parse_cas(
    file: UploadFile = File(...),
    password: str = Form(None), # Made optional for testing
    x_user_pan: str = Header(None),
    x_upload_type: str = Header("mutual_funds")
):
    raw = await file.read()
    # Use hardcoded test password if none provided (as requested by user)
    actual_pw = password if password and password.strip() else TEST_PASSWORD
    df_h, df_t, df_s, err, is_partial = parse_cas_file(raw, actual_pw)

    if err:
        raise HTTPException(status_code=422, detail=err)
    if df_h.empty:
        raise HTTPException(status_code=422, detail="No active holdings found in CAS.")

    session_id = create_session(df_h, df_t, df_s, is_partial, pan_id=x_user_pan, upload_type=x_upload_type)
    
    return {
        "session_id": session_id,
        "is_partial": is_partial,
        "fund_count": len(df_h),
        "amc_count":  len(df_h["AMC"].unique()) if "AMC" in df_h else 0,
        "categories": sorted(df_h["Category"].unique().tolist()) if "Category" in df_h else [],
        "amcs":       sorted(df_h["AMC"].unique().tolist()) if "AMC" in df_h else [],
        "benchmarks": sorted(BENCHMARKS.keys())
    }

import pandas as pd
from pydantic import BaseModel

class ConnectAARequest(BaseModel):
    phone: str = ""
    pan: str = ""

@router.post("/connect-aa")
def connect_aa(req: ConnectAARequest):
    """
    Simulates an instant MF Central Investor Data Sharing API real-time consent-based data stream.
    Delivers institutional-grade mock holding data without requiring manual CAS uploads.
    """
    df_h = pd.DataFrame([
        {
            "Fund": "Parag Parikh Flexi Cap Fund - Direct Plan",
            "AMC": "PPFAS Mutual Fund",
            "Category": "Flexi Cap",
            "Plan": "Direct",
            "Cap Type": "Flexi Cap",
            "Units": 4500.55,
            "NAV": 78.45,
            "Invested": 250000.0,
            "Market Value": 353068.15,
            "Gain": 103068.15,
            "Gain%": 41.23,
            "Weight%": 34.1,
            "ISIN": "INF879O01027",
        },
        {
            "Fund": "Nippon India Small Cap Fund - Direct Plan",
            "AMC": "Nippon India Mutual Fund",
            "Category": "Small Cap",
            "Plan": "Direct",
            "Cap Type": "Small Cap",
            "Units": 2100.25,
            "NAV": 165.20,
            "Invested": 200000.0,
            "Market Value": 346961.30,
            "Gain": 146961.30,
            "Gain%": 73.48,
            "Weight%": 33.5,
            "ISIN": "INF204KA1B64",
        },
        {
            "Fund": "ICICI Prudential Bluechip Fund - Direct Plan",
            "AMC": "ICICI Prudential Mutual Fund",
            "Category": "Large Cap",
            "Plan": "Direct",
            "Cap Type": "Large Cap",
            "Units": 3200.00,
            "NAV": 105.10,
            "Invested": 250000.0,
            "Market Value": 336320.00,
            "Gain": 86320.00,
            "Gain%": 34.53,
            "Weight%": 32.4,
            "ISIN": "INF109K012R6",
        }
    ])

    df_t = pd.DataFrame([
        {"Date": pd.to_datetime("2023-01-15"), "Fund": "Parag Parikh Flexi Cap Fund - Direct Plan", "Type": "SIP", "Amount": 10000.0, "Units": 150.2, "NAV": 66.58},
        {"Date": pd.to_datetime("2023-02-15"), "Fund": "Parag Parikh Flexi Cap Fund - Direct Plan", "Type": "SIP", "Amount": 10000.0, "Units": 148.5, "NAV": 67.34},
        {"Date": pd.to_datetime("2023-01-10"), "Fund": "Nippon India Small Cap Fund - Direct Plan", "Type": "SIP", "Amount": 10000.0, "Units": 80.5, "NAV": 124.2},
        {"Date": pd.to_datetime("2023-01-05"), "Fund": "ICICI Prudential Bluechip Fund - Direct Plan", "Type": "Lumpsum", "Amount": 100000.0, "Units": 1100.5, "NAV": 90.8},
    ])

    df_s = pd.DataFrame([
        {"Fund": "Parag Parikh Flexi Cap Fund - Direct Plan", "Amount": 10000.0, "Frequency": "Monthly", "SIP Day": 15},
        {"Fund": "Nippon India Small Cap Fund - Direct Plan", "Amount": 10000.0, "Frequency": "Monthly", "SIP Day": 10},
    ])

    session_id = create_session(df_h, df_t, df_s, False)

    return {
        "session_id": session_id,
        "is_partial": False,
        "fund_count": len(df_h),
        "amc_count": len(df_h["AMC"].unique()),
        "categories": sorted(df_h["Category"].unique().tolist()),
        "amcs": sorted(df_h["AMC"].unique().tolist()),
        "benchmarks": sorted(BENCHMARKS.keys())
    }

from core.sessions import create_session, get_session
from core.cache import MarketCache
from services.market_data import resolve_scheme_code_from_isin

@router.post("/{session_id}/sync")
def sync_portfolio(session_id: str):
    """
    Force invalidation of all cached market data for this session.
    Triggers fresh institutional audit on next data request.
    """
    portfolio = get_session(session_id)
    if portfolio.df_h.empty:
        return {"status": "ok", "cleared": 0}

    cleared_count = 0
    # 1. Global NAV Cache (Shared)
    MarketCache.invalidate("amfi_live_navs")
    from services.market_indices import clear_benchmark_cache
    from services.market_data import clear_market_data_cache
    clear_benchmark_cache()
    clear_market_data_cache()
    
    # 2. Fund-specific caches
    for _, row in portfolio.df_h.iterrows():
        isin = row.get("ISIN")
        name = row.get("Fund")
        if isin:
            # Invalidate disclosure cache
            MarketCache.invalidate(f"portfolio_{isin}")
            # Invalidate NAV history cache
            code = resolve_scheme_code_from_isin(isin)
            if code:
                MarketCache.invalidate(f"nav_series_{code}")
            cleared_count += 1
            
    # 3. Re-calculate portfolio units x live NAVs in memory
    portfolio.update_live_navs()
            
    return {"status": "ok", "cleared": cleared_count}
