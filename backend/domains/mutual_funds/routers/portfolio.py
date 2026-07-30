"""
routers/portfolio.py
Session lifecycle and CAS parsing gateway.
"""

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header
from domains.mutual_funds.parser import parse_cas_file
from domains.mutual_funds.sessions import create_session, get_session
from shared.config import BENCHMARKS
from shared.cache import MarketCache
from shared.services.market_indices import clear_benchmark_cache
from shared.services.market_data import (
    resolve_scheme_code_from_isin,
    clear_market_data_cache,
    _AMFI_BUNDLE_KEY as AMFI_BUNDLE_KEY,
)

router = APIRouter()

@router.post("/parse")
def parse_cas(
    file: UploadFile = File(...),
    password: str = Form(None), # Made optional for testing
    x_user_pan: str = Header(None),
    x_upload_type: str = Header("mutual_funds")
):
    """
    Parse a CAS PDF and create a portfolio session.

    Deliberately a sync `def`, not `async def`: parse_cas_file (casparser + PDF
    extraction) and create_session (ledger hash + three SQLite writes) are blocking
    work measured in seconds. Under `async def` they ran directly on the event loop
    of a single-worker deployment, which froze the whole API for the duration -
    including /health, which can fail the platform health check mid-upload. As a
    sync def, FastAPI runs this in the threadpool and the loop stays responsive.

    The tax-expert equivalent (domains/tax_expert/routers/session.py) was already
    fixed for exactly this reason; this endpoint is the same bug.
    """
    raw = file.file.read()
    # CAS statements are conventionally password-protected with the investor's own PAN.
    # If no password is supplied, fall back to the logged-in profile's PAN (X-User-PAN header)
    # rather than a hardcoded credential.
    actual_pw = password if password and password.strip() else x_user_pan
    if not actual_pw:
        raise HTTPException(status_code=400, detail="Password is required (or log in with your PAN so it can be used automatically).")
    df_h, df_t, df_s, err, is_partial, statement_period = parse_cas_file(raw, actual_pw)

    if err:
        raise HTTPException(status_code=422, detail=err)
    if df_h.empty:
        raise HTTPException(status_code=422, detail="No active holdings found in CAS.")

    session_id = create_session(df_h, df_t, df_s, is_partial, statement_period, pan_id=x_user_pan, upload_type=x_upload_type)
    
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

    # 1. Shared market data. clear_market_data_cache() also drops the in-process L1
    #    tier, which is where the parsed AMFI bundle and NAV series now live.
    MarketCache.delete(AMFI_BUNDLE_KEY)
    clear_benchmark_cache()
    clear_market_data_cache()

    # 2. Fund-specific caches.
    #    Exact-key deletes rather than pattern invalidation: each invalidate() call
    #    scans the whole cache directory, so the previous loop did 1 + 2N directory
    #    scans for an N-fund portfolio. delete() touches exactly one path.
    for _, row in portfolio.df_h.iterrows():
        isin = row.get("ISIN")
        name = row.get("Fund")
        if not isin:
            continue

        MarketCache.delete(f"portfolio_{isin}_{name}")
        code = resolve_scheme_code_from_isin(isin)
        if code:
            MarketCache.delete(f"nav_series_{code}")
        cleared_count += 1

    # 3. Re-calculate portfolio units x live NAVs in memory
    portfolio.update_live_navs()

    return {"status": "ok", "cleared": cleared_count}
