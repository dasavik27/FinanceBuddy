"""
routers/tabs/planning.py

Forward-Looking Wealth Planning Engine
=======================================
Surfaces the LTCG/STCG harvest calculator and the SIP step-up goal projector —
turning the portfolio from a rear-view mirror into a planning tool for future
investment decisions.
"""

from fastapi import APIRouter, Query
import pandas as pd
from domains.mutual_funds.sessions import get_session
from domains.mutual_funds.finance import (
    stepup_sip_projection, compute_xirr_by_fy, compute_sip_lumpsum_attribution, compute_mandate_overlap,
    simulate_historical_sip,
)
from shared.services.market_data import fetch_nav_series_by_code
from domains.mutual_funds.derived import cached_xirr_by_fy
from domains.mutual_funds.tax_lots import portfolio_tax_summary

router = APIRouter()


@router.get("/{session_id}/tax-harvest")
def get_tax_harvest(session_id: str):
    """
    LTCG/STCG harvest opportunities and debt-fund slab-tax exposure across
    the current portfolio. Indicative planning estimate — not tax advice.
    """
    portfolio = get_session(session_id)
    return portfolio_tax_summary(portfolio.df_h, portfolio.df_t)


@router.get("/{session_id}/sip-projection")
def get_sip_projection(
    session_id: str,
    # Bounded because it is a loop count, not a preference: finance.py runs
    # `for year in range(1, years + 1): for _ in range(12)` and appends a dict per month,
    # so an unbounded value is arbitrary CPU and memory from one GET. 50 years is longer
    # than any real projection horizon.
    years: int = Query(10, ge=1, le=50),
    annual_return: float = Query(12.0, ge=-50.0, le=100.0),
    stepup_pct: float = Query(10.0, ge=0.0, le=100.0),
    monthly_sip: float = Query(0.0, ge=0.0),
    lumpsum: float = Query(0.0, ge=0.0),
    include_existing_corpus: bool = True,
):
    """
    Project future wealth for a SIP plan with annual step-up. Defaults the
    starting monthly SIP to the portfolio's trailing-12-month run-rate, so
    users can plan "if I continue as-is" or override every field to model
    a brand-new fund/goal.
    """
    portfolio = get_session(session_id)
    df_s = portfolio.df_s

    if monthly_sip <= 0:
        if df_s is not None and not df_s.empty:
            recent = df_s.copy()
            recent["Date"] = pd.to_datetime(recent["Date"], dayfirst=True)
            cutoff = recent["Date"].max() - pd.DateOffset(months=12)
            recent_12m = recent[recent["Date"] >= cutoff]
            if not recent_12m.empty:
                monthly_sip = float(recent_12m["Amount"].sum() / 12)
            else:
                monthly_sip = float(recent["Amount"].mean() or 0)
        else:
            monthly_sip = 10000.0

    existing_corpus = portfolio.total_value if include_existing_corpus else 0.0

    result = stepup_sip_projection(
        monthly_sip=monthly_sip,
        years=years,
        annual_return=annual_return,
        stepup_pct=stepup_pct,
        lumpsum=lumpsum,
        existing_corpus=existing_corpus,
    )
    result["assumed_monthly_sip"] = round(monthly_sip, 0)
    result["assumed_existing_corpus"] = round(existing_corpus, 0)
    return result


@router.get("/{session_id}/xirr-by-fy")
def get_xirr_by_fy(session_id: str):
    """
    Cumulative-to-date XIRR sampled at each financial-year end — "am I
    improving year over year?" Reuses the same FIFO lots + XIRR engine used
    elsewhere, so it can't drift from the headline number.
    """
    portfolio = get_session(session_id)
    return {"fy_series": cached_xirr_by_fy(portfolio.df_t, portfolio.df_h)}


@router.get("/{session_id}/sip-attribution")
def get_sip_attribution(session_id: str):
    """SIP-vs-lumpsum split of invested capital and (approximate) current value."""
    portfolio = get_session(session_id)
    return compute_sip_lumpsum_attribution(portfolio.df_t, portfolio.total_value)


@router.get("/{session_id}/mandate-overlap")
def get_mandate_overlap(session_id: str):
    """
    Category + Cap-Type mandate-overlap groups — a proxy for stock-level
    portfolio overlap (no reliable real holdings data source exists for
    Indian mutual funds in this app; see compute_mandate_overlap docstring).
    """
    portfolio = get_session(session_id)
    return compute_mandate_overlap(portfolio.df_h)


@router.get("/{session_id}/what-if")
def get_what_if(
    session_id: str,
    scheme_code: str = Query(..., max_length=32),
    monthly_amount: float = Query(10000.0, gt=0, le=10_000_000),
    # Also a loop bound, and it additionally sizes the NAV history request below
    # (`days=years * 365 + 60`), so an unbounded value is an unbounded upstream fetch.
    years: int = Query(5, ge=1, le=50),
):
    """
    "If I'd invested Rs.X/month in THIS candidate fund for the last N years" —
    replays real historical NAVs (mfapi scheme code), not a projection. Use
    /mutual-funds/compare/search?q=... to resolve a fund name to a scheme_code.
    session_id is accepted for URL consistency with the rest of this router
    but unused — the simulation only needs the candidate fund's own NAV history.
    """
    nav_series = fetch_nav_series_by_code(scheme_code, days=max(years * 365 + 60, 365))
    if nav_series.empty:
        return {"error": "Could not fetch NAV history for this scheme code."}
    return simulate_historical_sip(nav_series, monthly_amount, years)
