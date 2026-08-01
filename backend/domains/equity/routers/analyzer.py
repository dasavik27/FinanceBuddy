"""domains/equity/routers/analyzer.py"""
import logging
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from domains.equity.stock_analyzer import search_stocks, analyze_stock, compute_portfolio_impact
from domains.equity import sessions as eq_sessions
from shared.services.cache import get_cache_headers

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/search")
def search(q: str = Query(..., min_length=1)):
    """Search for NSE stocks by symbol or company name."""
    results = search_stocks(q, limit=10)
    return {"results": results}


@router.get("/analyze/{symbol}")
def analyze(symbol: str):
    """
    Full fundamental + technical analysis for a single NSE stock.
    Returns PE ratio, market cap, 52-week range, beta, 1Y return, price chart.
    """
    try:
        result = analyze_stock(symbol)
        return JSONResponse(content=result, headers=get_cache_headers("comparison_data"))
    except Exception as e:
        logger.error("[analyzer] failed for %s: %s", symbol, e)
        raise HTTPException(status_code=502, detail=f"Could not fetch data for {symbol}: {e}")


class ImpactRequest(BaseModel):
    symbol: str
    amount: float       # Rupee amount to invest
    session_id: str | None = None  # If provided, uses the user's actual portfolio


@router.post("/impact")
def portfolio_impact(req: ImpactRequest):
    """
    Simulate adding `amount` of `symbol` to the user's portfolio.
    Returns before/after sector allocation, weight, and concentration warning.
    """
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")

    current_holdings = []
    current_total = 0.0

    if req.session_id:
        try:
            portfolio = eq_sessions.get_session(req.session_id)
            current_holdings = portfolio.get_holdings()
            current_total = portfolio.total_value
        except Exception as e:
            logger.warning("[analyzer/impact] session load failed: %s", e)

    result = compute_portfolio_impact(
        symbol=req.symbol,
        amount=req.amount,
        current_holdings=current_holdings,
        current_total=current_total,
    )
    return JSONResponse(content=result, headers=get_cache_headers("holdings_detail"))
