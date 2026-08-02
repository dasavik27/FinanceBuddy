"""domains/equity/routers/holdings.py"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from domains.equity import sessions as eq_sessions
from domains.equity.models import EquityPortfolio
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
    # Allowlisted rather than passed through. An unknown column used to be silently
    # ignored deep in get_holdings(), so the response came back in arbitrary order while
    # the UI showed a sorted header - a wrong answer presented as a correct one.
    if sort_by not in EquityPortfolio.SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot sort by {sort_by!r}. Allowed: {', '.join(EquityPortfolio.SORTABLE_COLUMNS)}.",
        )

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
