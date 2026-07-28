"""
domains/equity/router.py

Indian Stocks (Equity) Domain Router
=====================================
Placeholder for the direct-equity tracking feature. The frontend "Indian Stocks"
dashboard renders a standalone "Coming Soon" state and calls no endpoint at all.

This file exists so the domain has a real home from day one. Build NSDL/CDSL
statement parsing and equity-specific analytics here when the feature ships.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
def equity_status():
    """Reports that the Equity domain has no live endpoints yet."""
    return {"status": "not_implemented", "message": "Indian Stocks tracking is coming soon."}
