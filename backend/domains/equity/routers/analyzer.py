"""domains/equity/routers/analyzer.py"""
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from domains.equity import sessions as eq_sessions
from domains.equity.stock_analyzer import (
    UnknownSymbol,
    analyze_stock,
    compute_portfolio_impact,
    get_market_indices,
    search_stocks,
)
from shared import identity
from shared.services.cache import get_cache_headers

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_caller() -> str:
    """
    These two endpoints reach an external provider on every miss, so they are an
    amplifier: left open, an anonymous caller can drive our upstream quota from a loop.
    Nothing here is user data, so this is rate-limiting by identity, not authorization.
    """
    caller = identity.current_user_id()
    if not caller:
        raise HTTPException(status_code=401, detail="Sign in to use the stock analyzer.")
    return caller


@router.get("/indices")
def market_indices():
    """
    Live levels for NIFTY 50, SENSEX, BANK NIFTY, NIFTY IT for the top ticker ribbon.
    """
    return {"indices": get_market_indices()}


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=64)):
    """
    Search the curated NSE index by symbol or company name.

    max_length matters even though the index is local and small: without it, a
    multi-megabyte `q` was substring-matched against every entry.
    """
    results = search_stocks(q, limit=10)
    return {"results": results}


@router.get("/analyze/{symbol}")
def analyze(symbol: str):
    """
    Fundamental + technical analysis for a single NSE stock.
    Returns PE, market cap, 52-week range, beta, 1Y return, and a price chart.
    """
    _require_caller()
    try:
        result = analyze_stock(symbol)
    except UnknownSymbol:
        raise HTTPException(status_code=404, detail="That symbol was not recognised.")
    except Exception:
        # The provider's error text stays in the log. It used to be interpolated into
        # the response detail, exposing upstream internals to the client.
        logger.exception("[analyzer] analysis failed for %r", symbol)
        raise HTTPException(
            status_code=502, detail="Could not fetch data for that stock. Please retry."
        )
    return JSONResponse(content=result, headers=get_cache_headers("comparison_data"))


class ImpactRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    # Bounded on both ends: the simulation is meaningless at zero, and an unbounded
    # amount produced allocation percentages that overflowed the chart axis.
    amount: float = Field(..., gt=0, le=1_000_000_000)
    session_id: str | None = Field(default=None, max_length=64)


@router.post("/impact")
def portfolio_impact(req: ImpactRequest):
    """
    Simulate adding `amount` of `symbol` to the caller's portfolio.
    Returns before/after sector allocation, weight, and a concentration warning.
    """
    _require_caller()

    current_holdings: list[dict] = []
    current_total = 0.0

    if req.session_id:
        # get_session raises HTTPException for "not yours" and "not found", and those
        # must propagate. Swallowing every exception here (as this did) turned an
        # ownership denial into a silent success computed against an empty portfolio,
        # which reads to the user as though the simulation ran on their real holdings.
        portfolio = eq_sessions.get_session(req.session_id)
        current_holdings = portfolio.get_holdings()
        current_total = portfolio.total_value

    try:
        result = compute_portfolio_impact(
            symbol=req.symbol,
            amount=req.amount,
            current_holdings=current_holdings,
            current_total=current_total,
        )
    except UnknownSymbol:
        raise HTTPException(status_code=404, detail="That symbol was not recognised.")
    except Exception:
        logger.exception("[analyzer/impact] failed for %r", req.symbol)
        raise HTTPException(
            status_code=502, detail="Could not run that simulation. Please retry."
        )

    return JSONResponse(content=result, headers=get_cache_headers("holdings_detail"))
