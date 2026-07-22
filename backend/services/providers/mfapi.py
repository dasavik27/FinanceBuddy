"""
services/providers/mfapi.py
Implementation of the MarketDataProvider for mfapi.in.
"""

import requests
import pandas as pd
from datetime import timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Dict, Any
from .base import MarketDataProvider

class MFApiProvider(MarketDataProvider):
    """
    Data provider utilizing the public API at mfapi.in.
    Implements automatic retries and robust error handling.
    """
    
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(
            total=3, 
            backoff_factor=0.3, 
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def fetch_nav_series(self, scheme_code: str, days: int) -> pd.Series:
        """Fetch NAV history and return it as a pandas Series."""
        try:
            url = f"https://api.mfapi.in/mf/{str(scheme_code).strip()}"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", [])

            if not data:
                return pd.Series(dtype=float)

            # Parse to a map of Datetime objects -> floats
            raw_map = {pd.to_datetime(rec["date"], dayfirst=True): float(rec["nav"]) for rec in data}
            
            series = pd.Series(raw_map).sort_index()

            # Truncate by days if required
            if days < 9999:
                cutoff = series.index[-1] - timedelta(days=days)
                return series[series.index >= cutoff]
            return series

        except Exception as e:
            print(f"[MFAPI PROVIDER] Error fetching NAV for {scheme_code}: {e}")
            return pd.Series(dtype=float)

    def fetch_fund_meta(self, scheme_code: str) -> Dict[str, Any]:
        """Fetch fund metadata (name, house, type)."""
        try:
            url = f"https://api.mfapi.in/mf/{str(scheme_code).strip()}"
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            meta = resp.json().get("meta", {})
            return {
                "scheme_name":      meta.get("scheme_name", ""),
                "fund_house":       meta.get("fund_house", ""),
                "scheme_type":      meta.get("scheme_type", ""),
                "scheme_category":  meta.get("scheme_category", ""),
            }
        except Exception as e:
            print(f"[MFAPI PROVIDER] Metadata error for {scheme_code}: {e}")
            return {}

    def search_funds(self, query: str) -> List[Dict[str, Any]]:
        """Search the mfapi.in registry."""
        try:
            url = f"https://api.mfapi.in/mf/search?q={query}"
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[MFAPI PROVIDER] Search error for query '{query}': {e}")
            return []
