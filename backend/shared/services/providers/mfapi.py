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
import logging
logger = logging.getLogger(__name__)


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

            # Vectorized parse: ONE pd.to_datetime call over the whole date column,
            # not one per record.
            #
            # The previous dict comprehension called pd.to_datetime() per row, paying
            # parser setup and dayfirst inference ~2,500 times for a 10-year scheme -
            # roughly 50,000 invocations to warm a 20-fund portfolio on 0.1 vCPU.
            # mfapi returns dates as DD-MM-YYYY, so the format is known and passing it
            # explicitly skips per-element inference as well.
            dates = pd.to_datetime(
                [rec["date"] for rec in data], format="%d-%m-%Y", errors="coerce"
            )
            navs = pd.to_numeric([rec["nav"] for rec in data], errors="coerce")

            series = pd.Series(navs, index=dates, dtype=float)
            # A malformed date or NAV becomes NaT/NaN rather than raising, matching the
            # old behaviour of skipping unparseable rows.
            series = series[series.index.notna()].dropna()
            # Duplicate dates would previously collapse via dict keying; keep that.
            series = series[~series.index.duplicated(keep="last")].sort_index()

            if series.empty:
                return pd.Series(dtype=float)

            # Truncate by days if required
            if days < 9999:
                cutoff = series.index[-1] - timedelta(days=days)
                return series[series.index >= cutoff]
            return series

        except Exception as e:
            logger.info(f"[MFAPI PROVIDER] Error fetching NAV for {scheme_code}: {e}")
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
            logger.info(f"[MFAPI PROVIDER] Metadata error for {scheme_code}: {e}")
            return {}

    def search_funds(self, query: str) -> List[Dict[str, Any]]:
        """Search the mfapi.in registry."""
        try:
            url = f"https://api.mfapi.in/mf/search?q={query}"
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.info(f"[MFAPI PROVIDER] Search error for query '{query}': {e}")
            return []
