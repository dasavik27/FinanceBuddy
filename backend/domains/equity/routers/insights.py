"""domains/equity/routers/insights.py"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from domains.equity import sessions as eq_sessions
from shared.services.cache import get_cache_headers

router = APIRouter()

@router.get("/{session_id}/insights")
def get_insights(session_id: str):
    """Smart nudges: top movers, concentrated positions, tax-loss harvest alerts, diversification score."""
    portfolio = eq_sessions.get_session(session_id)
    insights = portfolio.get_insights()
    return JSONResponse(content=insights, headers=get_cache_headers("holdings_detail"))
