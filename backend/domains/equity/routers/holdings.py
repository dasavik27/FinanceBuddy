"""domains/equity/routers/holdings.py"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from domains.equity import sessions as eq_sessions
from shared.services.cache import get_cache_headers

router = APIRouter()

@router.get("/{session_id}/holdings")
def get_holdings(
    session_id: str,
    sort_by: str = Query("current_value"),
    ascending: bool = Query(False),
):
    """
    Per-stock holdings table with symbol, quantity, avg price, LTP, P&L.
    """
    portfolio = eq_sessions.get_session(session_id)
    holdings = portfolio.get_holdings(sort_by=sort_by, ascending=ascending)
    return JSONResponse(
        content={"holdings": holdings, "total": portfolio.total_value},
        headers=get_cache_headers("holdings_detail"),
    )

@router.get("/{session_id}/pnl")
def get_pnl(session_id: str):
    """P&L analysis with STCG/LTCG estimates and top gainers/losers."""
    portfolio = eq_sessions.get_session(session_id)
    pnl = portfolio.get_pnl_analysis()
    return JSONResponse(content=pnl, headers=get_cache_headers("holdings_detail"))
