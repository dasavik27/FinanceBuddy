"""Equity Research Scan API — strategy list, universe scan, per-symbol evaluate."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from domains.equity.research_engine import evaluate_symbol, list_strategies, run_scan
from domains.equity.research_engine.vcp import STRATEGY_ID
from shared import identity

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_caller() -> str:
    caller = identity.current_user_id()
    if not caller:
        raise HTTPException(status_code=401, detail="Sign in to use equity research scans.")
    return caller


class ScanRequest(BaseModel):
    strategy: str = Field(default=STRATEGY_ID)
    universe: str = Field(default="nifty50")
    symbols: list[str] | None = None
    limit: int = Field(default=50, ge=1, le=80)
    only_setups: bool = False


@router.get("/strategies")
def strategies():
    """List registered research strategies (no auth — metadata only)."""
    return {"strategies": list_strategies()}


@router.get("/symbol/{symbol}")
def symbol_research(
    symbol: str,
    strategy: str = Query(default=STRATEGY_ID),
):
    """Evaluate one symbol against a research strategy."""
    _require_caller()
    try:
        result = evaluate_symbol(symbol, strategy_id=strategy)
    except Exception:
        logger.exception("[research] symbol evaluate failed for %r", symbol)
        raise HTTPException(status_code=502, detail="Could not evaluate that symbol.")
    if not result.get("ok") and result.get("reason", "").startswith("unknown strategy"):
        raise HTTPException(status_code=404, detail=result["reason"])
    return result


@router.post("/scan")
def scan(body: ScanRequest):
    """
    Scan a universe with a research strategy.

    Default universe is Nifty 50, capped for deploy safety. Pass `symbols` for a
    custom list. Results are ranked by MarketSmith-free composite score.
    """
    _require_caller()
    try:
        out = run_scan(
            strategy_id=body.strategy,
            universe=body.universe,
            symbols=body.symbols,
            limit=body.limit,
            only_setups=body.only_setups,
        )
    except Exception:
        logger.exception("[research] scan failed")
        raise HTTPException(status_code=502, detail="Research scan failed. Please retry.")
    if not out.get("ok") and str(out.get("reason", "")).startswith("unknown strategy"):
        raise HTTPException(status_code=404, detail=out["reason"])
    return out
