"""domains/equity/routers/overview.py"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from domains.equity import sessions as eq_sessions
from shared.services.cache import get_cache_headers

router = APIRouter()

@router.get("/{session_id}/summary")
def get_summary(session_id: str):
    """High-level KPI metrics: total value, P&L, stock count, day change."""
    portfolio = eq_sessions.get_session(session_id)
    summary = portfolio.get_summary()
    return JSONResponse(content=summary, headers=get_cache_headers("holdings_detail"))

@router.get("/{session_id}/allocation")
def get_allocation(session_id: str):
    """Sector and industry allocation breakdown."""
    portfolio = eq_sessions.get_session(session_id)
    allocation = portfolio.get_sector_allocation()
    return JSONResponse(content=allocation, headers=get_cache_headers("holdings_detail"))
