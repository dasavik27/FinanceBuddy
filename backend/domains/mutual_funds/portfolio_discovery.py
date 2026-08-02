"""
domains/mutual_funds/portfolio_discovery.py
The Deterministic Insights Engine.
Fetches deep institutional metadata (AUM, Risk, ER, Sectors) via Yahoo Finance.
Implements robust categorical heuristic fallbacks if upstream APIs fail, ensuring 100% UI uptime.
"""

from typing import Dict, List, Optional

from shared.cache import MarketCache

def fetch_live_portfolio(isin: str, category: str, fund_name: str = "", refresh: bool = False) -> Dict:
    """
    Fetch comprehensive fund metadata (sectors, holdings, risk, aum, ER).
    
    This acts as the core Deterministic Insights Engine. It first attempts to fetch
    verified institutional data from Yahoo Finance by resolving the ISIN.
    If the fetch fails, it falls back to a deterministic heuristic generation engine
    that accurately estimates the missing metrics based on the fund's asset category
    (e.g., Equity vs Debt) and cap type (e.g., Large vs Small).
    
    Args:
        isin (str): International Securities Identification Number.
        category (str): Fund category (e.g., "Large Cap Fund").
        fund_name (str): Full name of the fund, used to seed the random heuristics.
        refresh (bool): Bypasses the cache and forces a fresh network fetch.
        
    Returns:
        Dict: A dictionary containing the insights and boolean fallback flags.
    """
    cache_key = f"portfolio_{isin}_{fund_name}"
    
    if not refresh:
        cached = MarketCache.get(cache_key)
        if cached: return cached

    from shared.services.providers.yahoo import YahooMetadataProvider
    provider = YahooMetadataProvider()
    result = provider.fetch_insights(isin, fund_name, category)

    from shared.services.fallbacks.factory import get_fallback_engine
    fallback_engine = get_fallback_engine()
    
    # If missing, pass through the Extensible Fallback Strategy Engine
    result = fallback_engine.generate_fallbacks(isin, category, fund_name, result)
        
    # Persist to cache for high-fidelity audit performance
    MarketCache.set(cache_key, result)
    return result
