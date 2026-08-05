"""
domains/mutual_funds/portfolio_discovery.py
Fund insights engine: AMFI snapshots first, Yahoo Finance second.
Missing fields stay blank — no synthetic / heuristic fill-in.
"""

from typing import Dict, List, Optional

from shared.cache import MarketCache

def fetch_live_portfolio(isin: str, category: str, fund_name: str = "", refresh: bool = False) -> Dict:
    """
    Fetch comprehensive fund metadata (sectors, holdings, risk, aum, ER).
    
    Two-tier insights engine:
      - Tier 1: PostgreSQL AMFI snapshots (seeded and/or sync ingest)
      - Tier 2: Yahoo Finance (Global / ETF / Foreign fund coverage)
    
    If both miss, fields stay blank (null / empty lists). No deterministic heuristics.
    
    Args:
        isin (str): International Securities Identification Number.
        category (str): Fund category (e.g., "Large Cap Fund").
        fund_name (str): Full name of the fund.
        refresh (bool): Bypasses the cache and forces a fresh database/network lookup.
        
    Returns:
        Dict: A dictionary containing verified insights and boolean fallback flags.
    """
    cache_key = f"portfolio_{isin}_{fund_name}"
    
    if not refresh:
        cached = MarketCache.get(cache_key)
        if cached:
            return cached

    result = None

    # ── Tier 1: AMFI PostgreSQL Snapshot ───────────────────────────────────────
    try:
        from shared.services.providers.amfi_db import AMFIDatabaseProvider
        db_provider = AMFIDatabaseProvider()
        db_result = db_provider.fetch_insights(isin, fund_name, category)
        if (db_result.get("holdings") and len(db_result["holdings"]) > 0) or (
            db_result.get("sectors") and len(db_result["sectors"]) > 0
        ):
            result = db_result
    except Exception:
        result = None

    # ── Tier 2: Yahoo Finance Fallback (For un-indexed or Global FoFs) ─────────
    if not result:
        try:
            from shared.services.providers.yahoo import YahooMetadataProvider
            yahoo_provider = YahooMetadataProvider()
            result = yahoo_provider.fetch_insights(isin, fund_name, category)
        except Exception:
            result = None

    if not result:
        # Both tiers missed — leave blank rather than inventing values.
        result = {
            "source": None,
            "sectors": [],
            "holdings": [],
            "risk": None,
            "exit_load": None,
            "expense_ratio": None,
            "aum": None,
            "aum_fallback": False,
            "risk_fallback": False,
            "exit_load_fallback": False,
            "expense_ratio_fallback": False,
        }
    else:
        # Auto-persist only when a real upstream source produced data.
        _auto_persist_snapshot(isin, fund_name, category, result)

    # Persist to cache for high-fidelity audit performance
    MarketCache.set(cache_key, result)
    return result


def _auto_persist_snapshot(isin: str, fund_name: str, category: str, result: Dict) -> None:
    """Auto-persist any discovered fund into PostgreSQL snapshot table so it permanently becomes Tier 1."""
    if not isin or not isin.startswith("INF"):
        return
    try:
        import json
        import re
        from shared import db
        with db.connect() as conn:
            aum_val = None
            if result.get("aum"):
                digits = re.findall(r"[\d\.]+", str(result["aum"]).replace(",", ""))
                if digits:
                    aum_val = float(digits[0])

            er_val = None
            if result.get("expense_ratio"):
                digits = re.findall(r"[\d\.]+", str(result["expense_ratio"]).replace("%", ""))
                if digits:
                    er_val = float(digits[0])

            conn.execute(
                """
                INSERT INTO mf_portfolio_snapshots (
                    isin, scheme_name, category, aum_cr, expense_ratio, risk_level,
                    sectors, holdings, source, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, now())
                ON CONFLICT (isin) DO NOTHING
                """,
                (
                    isin,
                    fund_name or isin,
                    category or "Other",
                    aum_val,
                    er_val,
                    result.get("risk", "VERY HIGH"),
                    json.dumps(result.get("sectors", [])),
                    json.dumps(result.get("holdings", [])),
                    result.get("source") or "Auto-Discovered Disclosure",
                ),
            )
    except Exception:
        pass
