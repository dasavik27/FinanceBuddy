"""
routers/tabs/holdings.py

Institutional Holdings Explorer & Real-Time Enrichment Gateway
==============================================================
Dedicated REST gateway for the Holdings tab. Orchestrates multi-threaded real-time NAV enrichment,
7-day price change calculations, transaction history pagination, and live institutional fund metadata.
"""

from fastapi import APIRouter, Query
from domains.mutual_funds.sessions import get_session, df_to_records
from shared.config import CATEGORY_COLORS
from shared.services.market_data import (
    fetch_nav_series_by_isin, fetch_fund_ter, resolve_scheme_code_from_isin, fetch_fund_metadata
)
from domains.mutual_funds.portfolio_discovery import fetch_live_portfolio
from concurrent.futures import ThreadPoolExecutor

router = APIRouter()

@router.get("/{session_id}/holdings")
def get_holdings(
    session_id: str,
    sort_by: str = "Market Value",
    ascending: str = "false",
    # Bounded. Even with regex disabled below, an unbounded needle is scanned against
    # every fund name; more importantly the length was the exponent in the blow-up this
    # parameter used to permit.
    search: str = Query("", max_length=100),
    cap_filter: str = "All",
    refresh: bool = False,
):
    portfolio = get_session(session_id)
    df_h = portfolio.df_h.copy()

    if df_h.empty:
        return {"holdings": [], "total": 0, "cap_types": []}

    # 1. Search Filter
    #
    # regex=False is load-bearing, not tidiness. pandas' str.contains defaults to
    # regex=True, so this query parameter was compiled and executed as a regular
    # expression against every fund name. Two consequences, both reachable by anyone
    # who could call this endpoint:
    #
    #   - CPU exhaustion. A backtracking pattern like "(a+)+$" costs exponential time
    #     in the length of the subject: measured here at 0.15s for 18 characters, 6.7s
    #     for 24, and over two minutes for 30 - on ONE row, in ONE request, on a shared
    #     vCPU. `search` had no length limit, so the caller chose the exponent.
    #   - A 500. An invalid pattern - "(" is enough - raises re.PatternError, which no
    #     handler catches.
    #
    # A substring match is also what the UI actually wants; nobody was typing regexes
    # into a fund-name search box on purpose.
    if search:
        df_h = df_h[df_h["Fund"].str.contains(search, case=False, na=False, regex=False)]

    # 2. Market Cap Filter
    if cap_filter != "All":
        df_h = df_h[df_h["Cap Type"] == cap_filter]

    # 3. Sorting Engine
    asc = ascending.lower() == "true"
    
    def get_nav_data(r_df):
        isin = r_df["ISIN"]
        if not isin: return 0, 0, 0
        nav_series = fetch_nav_series_by_isin(isin, days=7, refresh=refresh)
        if not nav_series.empty and len(nav_series) >= 2:
            latest = float(nav_series.iloc[-1])
            prev   = float(nav_series.iloc[-2])
            return latest, (latest / prev - 1) * 100, (latest - prev) * r_df["Units"]
        return float(r_df.get("NAV", 0)), 0, 0

    if sort_by == "Signal":
        df_h = df_h.sort_values(by=["Gain%", "Weight%"], ascending=asc)
    elif sort_by == "Avg. NAV":
        df_h["_sort"] = df_h["Invested"] / df_h["Units"]
        df_h = df_h.sort_values(by="_sort", ascending=asc)
    elif sort_by == "Curr. NAV":
        df_h = df_h.sort_values(by="NAV", ascending=asc)
    elif sort_by == "P&L" or sort_by == "Gain":
        df_h = df_h.sort_values(by="Gain", ascending=asc)
    elif sort_by == "Current" or sort_by == "Market Value":
        df_h = df_h.sort_values(by="Market Value", ascending=asc)
    elif sort_by == "Day Chg.":
        df_h["_sort"] = df_h.apply(lambda r: get_nav_data(r)[2], axis=1)
        df_h = df_h.sort_values(by="_sort", ascending=asc)
    elif sort_by in df_h.columns:
        df_h = df_h.sort_values(by=sort_by, ascending=asc)
    elif sort_by == "Fund":
        df_h = df_h.sort_values(by="Fund", ascending=asc)

    records = df_to_records(df_h)
    
    # Real-time multi-threaded enrichment (Day Change & Average NAV)
    def enrich_holding(r):
        isin = r.get("ISIN")
        if not isin: return r
        
        units = float(r.get("Units", 0) or 0)
        invested = float(r.get("Invested", 0) or 0)
        r["Avg. NAV"] = round(invested / units, 4) if units > 0 else 0
        
        nav_series = fetch_nav_series_by_isin(isin, days=10, refresh=refresh)
        
        live_nav = float(r.get("NAV", 0))
        r["Curr. NAV"] = live_nav
        r["NAV Date"] = str(r.get("NAV Date", "—"))
        
        day_chg_amt = 0.0
        day_chg_pct = 0.0

        if not nav_series.empty and live_nav > 0:
            nav_date_str = str(r.get("NAV Date", ""))
            if nav_date_str and nav_date_str != "—":
                try:
                    import pandas as pd
                    nav_date_dt = pd.to_datetime(nav_date_str)
                    
                    # Lock previous close to the business day STRICTLY BEFORE the cached Live NAV Date.
                    # This guarantees Day Change is 100% deterministic and immune to mfapi's asynchronous sync delays.
                    prev_series = nav_series[nav_series.index < nav_date_dt]
                    
                    if not prev_series.empty:
                        # Only compute if the previous date is within 4 days (covers long weekends).
                        # If mfapi is stale by >4 days, Day Chg evaluates to 0 rather than a fake 20-day move.
                        from datetime import timedelta
                        if (nav_date_dt - prev_series.index[-1]) <= timedelta(days=4):
                            prev_nav = float(prev_series.iloc[-1])
                            if prev_nav > 0:
                                day_chg_pct = (live_nav / prev_nav - 1) * 100
                                day_chg_amt = units * (live_nav - prev_nav)
                                r["Prev NAV"] = prev_nav
                                r["Prev NAV Date"] = prev_series.index[-1].strftime("%d %b %Y")
                                
                                # Sanity check for impossible single day moves (>10%)
                                if abs(day_chg_pct) > 10.0:
                                    day_chg_pct = 0.0
                                    day_chg_amt = 0.0
                                    r.pop("Prev NAV", None)
                                    r.pop("Prev NAV Date", None)
                except Exception:
                    pass

        r["Day Chg."] = round(day_chg_amt, 2)
        r["Day Chg.%"] = round(day_chg_pct, 2)
            
        r["color"] = CATEGORY_COLORS.get(r.get("Category", ""), "#94A3B8")
        code = resolve_scheme_code_from_isin(isin)
        ter = fetch_fund_ter(code, r.get("Plan", "Direct")) if code else None
        
        if ter is None or ter <= 0:
            try:
                p_data = fetch_live_portfolio(isin, r.get("Category", "Equity"), r.get("Fund", ""))
                if p_data and p_data.get("expense_ratio"):
                    ter_val = float(str(p_data["expense_ratio"]).replace("%", "").strip())
                    if ter_val > 0:
                        ter = ter_val
            except Exception:
                pass

        if ter is not None and ter > 0:
            r["TER"] = round(ter, 2)
            r["TER_fallback"] = False
        else:
            # Leave blank/None when AMFI TER is unavailable — frontend renders N/A.
            r["TER"] = None
            r["TER_fallback"] = False
        return r

    with ThreadPoolExecutor(max_workers=10) as executor:
        enriched_records = list(executor.map(lambda r: enrich_holding(r), records))
    
    # Sanitize NaN/Inf values to prevent JSON serialization crashes
    import math
    def _sanitize(val):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return 0.0
        return val

    for rec in enriched_records:
        for key in rec:
            rec[key] = _sanitize(rec[key])

    return {
        "holdings": enriched_records,
        "total": len(records),
        "cap_types": sorted(portfolio.df_h["Cap Type"].unique().tolist()) if not portfolio.df_h.empty else []
    }

@router.get("/{session_id}/transactions")
def get_transactions(session_id: str, limit: int = 200):
    """
    Fetch paginated historical transaction ledger for the active portfolio.
    """
    portfolio = get_session(session_id)
    df_t = portfolio.df_t.sort_values("Date", ascending=False).head(limit)
    return {"transactions": df_to_records(df_t)}

@router.get("/{session_id}/fund-insights/{isin}")
def get_fund_insights(session_id: str, isin: str, name: str = "", refresh: bool = False):
    """
    Fetch live institutional insights, sector allocations, and factsheet metadata for a specific holding.
    """
    code = resolve_scheme_code_from_isin(isin)
    
    meta = fetch_fund_metadata(code) if code else {}
    category = meta.get("scheme_category", "Equity")
    
    search_name = name or meta.get("scheme_name", "")
    portfolio_data = fetch_live_portfolio(isin, category, search_name, refresh=refresh)
    
    # Prefer live AMFI TER; otherwise use portfolio insight ER; else blank.
    amfi_er = fetch_fund_ter(code) if code else None
    er = amfi_er if amfi_er else portfolio_data.get("expense_ratio")
    
    # If a valid TER is resolved, update in-memory session holding row so subsequent views retain it
    if er not in (None, "", "N/A"):
        try:
            er_num = float(str(er).replace("%", "").strip())
            portfolio = get_session(session_id)
            if portfolio and hasattr(portfolio, "df_h") and not portfolio.df_h.empty:
                if "ISIN" in portfolio.df_h.columns and isin:
                    mask = portfolio.df_h["ISIN"] == isin
                    if mask.any():
                        portfolio.df_h.loc[mask, "TER"] = er_num
        except Exception:
            pass

    aum_str = meta.get("aum") or portfolio_data.get("aum")
    
    return {
        "isin": isin,
        "scheme_code": code,
        "scheme_name": meta.get("scheme_name"),
        "fund_house": meta.get("fund_house"),
        "expense_ratio": f"{er}%" if er not in (None, "", "N/A") else None,
        "expense_ratio_fallback": False,
        "aum": aum_str,
        "aum_fallback": False,
        "exit_load": portfolio_data.get("exit_load"),
        "exit_load_fallback": False,
        "risk": portfolio_data.get("risk"),
        "risk_fallback": False,
        "category": category,
        "type": meta.get("scheme_type"),
        "sectors": portfolio_data.get("sectors", []),
        "holdings": portfolio_data.get("holdings", []),
        "source": portfolio_data.get("source"),
    }
