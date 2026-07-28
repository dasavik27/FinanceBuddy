"""
routers/portfolio.py
Session lifecycle and CAS parsing gateway.
"""

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header
from domains.mutual_funds.parser import parse_cas_file
from domains.mutual_funds.sessions import create_session, get_session
from shared.config import BENCHMARKS, TEST_PASSWORD
from shared.cache import MarketCache
from shared.services.market_indices import clear_benchmark_cache
from shared.services.market_data import resolve_scheme_code_from_isin, clear_market_data_cache

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
