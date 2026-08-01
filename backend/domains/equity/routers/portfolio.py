"""
domains/equity/routers/portfolio.py

Session lifecycle: CSV/XLSX upload, Zerodha Kite OAuth, and sync.
"""

import hmac
import logging
import os
import secrets
import time

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from domains.equity import sessions as eq_sessions
from domains.equity.kite_client import KiteClient, holdings_to_dataframe
from domains.equity.parser import (
    UnsupportedUploadType,
    UploadTooLarge,
    parse_holdings_csv,
    parse_tradebook_csv,
    read_upload,
)
from shared import identity

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_caller() -> str:
    """
    The signed-in user, or 401.

    Ownership is enforced in the data-access layer (shared/identity.py), which is the
    right place for *reads* of an existing session. Creation is different: a session
    saved by an anonymous request lands with `user_id = NULL`, and an unowned record is
    readable by everyone by design (`identity.owns_record` returns True when there is
    no owner to protect it from). So the write side has to insist on an identity, or it
    manufactures exactly the records the read side cannot protect.
    """
    caller = identity.current_user_id()
    if not caller:
        raise HTTPException(
            status_code=401, detail="Sign in to upload or connect a portfolio."
        )
    return caller


def _get_kite_client() -> KiteClient:
    api_key = os.getenv("ZERODHA_API_KEY", "")
    api_secret = os.getenv("ZERODHA_API_SECRET", "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Zerodha API key not configured. Set ZERODHA_API_KEY in your environment."
        )
    return KiteClient(api_key=api_key, api_secret=api_secret)


# ── CSV / XLSX upload ─────────────────────────────────────────────────────────

@router.post("/parse")
def parse_equity_csv(
    file: UploadFile = File(...),
    tradebook: UploadFile = File(None),
):
    """
    Parse a Zerodha/Groww/generic holdings export, optionally with a tradebook.
    Creates an equity session and returns its id.
    """
    _require_caller()

    try:
        raw_holdings = read_upload(file.file, file.filename or "")
    except (UploadTooLarge, UnsupportedUploadType) as e:
        raise HTTPException(status_code=422, detail=str(e))

    df_holdings, err = parse_holdings_csv(raw_holdings, filename=file.filename)
    if err:
        raise HTTPException(status_code=422, detail=err)
    if df_holdings.empty:
        raise HTTPException(status_code=422, detail="No valid holdings found in the upload.")

    df_trades = pd.DataFrame()
    if tradebook and tradebook.filename:
        try:
            raw_trades = read_upload(tradebook.file, tradebook.filename)
        except (UploadTooLarge, UnsupportedUploadType) as e:
            raise HTTPException(status_code=422, detail=f"Tradebook: {e}")
        df_trades, trade_err = parse_tradebook_csv(raw_trades, filename=tradebook.filename)
        if trade_err:
            raise HTTPException(status_code=422, detail=f"Tradebook: {trade_err}")

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
#
# The flow leaves this application and comes back, so the return leg has to be tied to
# the request that started it. Without that, /kite/connect accepts any request_token
# from anybody: a victim induced to submit an attacker's token ingests the *attacker's*
# holdings into their own account, and a token leaked from the browser URL bar (it
# travels as a query parameter, so it lands in history and Referer) can be redeemed by
# whoever finds it. `state` is the standard binding, and Kite passes it through.
#
# States are held in process, keyed to the issuing user, and single-use. A restart
# invalidates outstanding logins, which is the safe direction to fail.

_KITE_STATE_TTL_SECONDS = 600
_kite_states: dict[str, tuple[str, float]] = {}


def _issue_kite_state(user_id: str) -> str:
    now = time.time()
    # Opportunistic sweep; the table only grows if logins are started and abandoned.
    for token, (_owner, expires) in list(_kite_states.items()):
        if expires < now:
            _kite_states.pop(token, None)
    state = secrets.token_urlsafe(32)
    _kite_states[state] = (user_id, now + _KITE_STATE_TTL_SECONDS)
    return state


def _redeem_kite_state(state: str, user_id: str) -> bool:
    """Consume a state token. True only if it was issued to this user and is unexpired."""
    entry = _kite_states.pop(state, None)
    if entry is None:
        return False
    owner, expires = entry
    if expires < time.time():
        return False
    # compare_digest: state is a secret, and this is a comparison an attacker can time.
    return hmac.compare_digest(str(owner), str(user_id))


@router.get("/kite/login-url")
def kite_login_url():
    """Return the Zerodha OAuth login URL, bound to the calling user via `state`."""
    caller = _require_caller()
    kite = _get_kite_client()
    state = _issue_kite_state(caller)
    try:
        url = kite.get_login_url(state=state)
    except Exception:
        logger.exception("[kite] could not build login url")
        raise HTTPException(status_code=502, detail="Could not reach Zerodha. Please retry.")
    return {"login_url": url, "state": state}


@router.post("/kite/connect")
def kite_connect(request_token: str = Form(...), state: str = Form(...)):
    """
    Exchange a Zerodha request_token for an access_token, fetch live holdings, and
    create an equity session.
    """
    caller = _require_caller()

    if not _redeem_kite_state(state, caller):
        logger.warning("[kite] rejected connect with an unknown or foreign state")
        raise HTTPException(
            status_code=400,
            detail="This Zerodha login could not be verified. Please start the connection again.",
        )

    kite = _get_kite_client()

    # Raw broker error text is logged, never returned: it previously reached the client
    # verbatim via detail=str(e).
    try:
        session_data = kite.exchange_token(request_token)
    except Exception:
        logger.exception("[kite] token exchange failed")
        raise HTTPException(
            status_code=400,
            detail="Zerodha rejected this login. Please start the connection again.",
        )

    access_token = session_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token received from Zerodha.")

    try:
        raw_holdings = kite.fetch_holdings(access_token)
    except Exception:
        logger.exception("[kite] holdings fetch failed")
        raise HTTPException(
            status_code=502, detail="Could not fetch your holdings from Zerodha. Please retry."
        )

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
    """Re-fetch live prices for all holdings. get_session enforces ownership."""
    portfolio = eq_sessions.get_session(session_id)
    portfolio.update_live_prices()
    return {
        "status": "ok",
        "total_value": portfolio.total_value,
        "stock_count": len(portfolio.df_holdings),
    }
