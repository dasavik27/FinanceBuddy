"""
domains/equity/routers/portfolio.py

Session lifecycle: CSV upload, Zerodha Kite OAuth, and sync.
"""

import os
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header
from fastapi.responses import JSONResponse

from domains.equity import sessions as eq_sessions
from domains.equity.parser import parse_holdings_csv, parse_tradebook_csv
from domains.equity.kite_client import KiteClient, holdings_to_dataframe
from shared import identity

router = APIRouter()


def _get_kite_client() -> KiteClient:
    api_key = os.getenv("ZERODHA_API_KEY", "")
    api_secret = os.getenv("ZERODHA_API_SECRET", "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Zerodha API key not configured. Set ZERODHA_API_KEY in your environment."
        )
    return KiteClient(api_key=api_key, api_secret=api_secret)


# ── CSV Upload ────────────────────────────────────────────────────────────────

@router.post("/parse")
def parse_equity_csv(
    file: UploadFile = File(...),
    tradebook: UploadFile = File(None),
):
    """
    Parse a Zerodha/Groww/Generic Holdings CSV (and optionally a Tradebook CSV).
    Creates an equity session and returns the session_id.
    """
    raw_holdings = file.file.read()
    df_holdings, err = parse_holdings_csv(raw_holdings)
    if err:
        raise HTTPException(status_code=422, detail=err)
    if df_holdings.empty:
        raise HTTPException(status_code=422, detail="No valid holdings found in the uploaded CSV.")

    df_trades = pd.DataFrame()
    if tradebook and tradebook.filename:
        raw_trades = tradebook.file.read()
        df_trades, trade_err = parse_tradebook_csv(raw_trades)
        if trade_err:
            raise HTTPException(status_code=422, detail=f"Tradebook parse error: {trade_err}")

    broker = df_holdings["broker"].iloc[0] if not df_holdings.empty else "csv"
    session_id = eq_sessions.create_session(
        df_holdings, df_trades, source=broker, upload_type="equity"
    )

    return {
        "session_id": session_id,
        "stock_count": len(df_holdings),
        "broker": broker,
        "has_tradebook": not df_trades.empty,
        "symbols": sorted(df_holdings["symbol"].tolist()),
    }


# ── Zerodha Kite OAuth ────────────────────────────────────────────────────────

@router.get("/kite/login-url")
def kite_login_url():
    """Return the Zerodha OAuth login URL for the user to open."""
    kite = _get_kite_client()
    url = kite.get_login_url()
    return {"login_url": url}


@router.post("/kite/connect")
def kite_connect(request_token: str = Form(...)):
    """
    Exchange a Zerodha request_token (from the OAuth redirect) for an access_token.
    Fetches live holdings from Kite API and creates an equity session.
    """
    kite = _get_kite_client()
    try:
        session_data = kite.exchange_token(request_token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    access_token = session_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token received from Zerodha.")

    try:
        raw_holdings = kite.fetch_holdings(access_token)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    df_holdings = holdings_to_dataframe(raw_holdings)
    if df_holdings.empty:
        raise HTTPException(status_code=422, detail="No holdings found in your Zerodha account.")

    session_id = eq_sessions.create_session(
        df_holdings=df_holdings,
        df_trades=pd.DataFrame(),
        source="zerodha_kite",
        kite_access_token=access_token,
        upload_type="equity",
    )

    profile = kite.fetch_profile(access_token)
    return {
        "session_id": session_id,
        "stock_count": len(df_holdings),
        "broker": "zerodha_kite",
        "zerodha_user": profile.get("user_name", ""),
        "symbols": sorted(df_holdings["symbol"].tolist()),
    }


# ── Sync (refresh live prices) ────────────────────────────────────────────────

@router.post("/{session_id}/sync")
def sync_equity(session_id: str):
    """Re-fetch live prices from Yahoo Finance for all holdings."""
    portfolio = eq_sessions.get_session(session_id)
    portfolio.update_live_prices()
    return {
        "status": "ok",
        "total_value": portfolio.total_value,
        "stock_count": len(portfolio.df_holdings),
    }
