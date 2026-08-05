"""
domains/equity/bse_client.py

Lightweight BSE API client for VWAP (Volume Weighted Average Price) only.

BSE is the only source that publishes intraday VWAP (`WAP` field). Yahoo Finance
does not expose VWAP at all. Scope is deliberately limited to VWAP only — avoids
depending on undocumented BSE endpoints for fields Yahoo already covers via
.BO cascade.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from shared.services.cache import MARKET_CACHE

logger = logging.getLogger(__name__)

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}
_TIMEOUT = 10
_TTL_SCRIP_MAP = 24 * 3600  # Master list changes rarely
_TTL_VWAP = 5 * 60  # VWAP is intraday data


class BSEClient:
    """
    Lightweight BSE API client for VWAP only.
    
    Maps NSE symbols to BSE scrip codes and fetches Volume Weighted Average Price
    from BSE's official StockTrading endpoint.
    """

    def __init__(self):
        self._scrip_map: dict[str, str] | None = None

    def _load_scrip_map(self) -> dict[str, str]:
        """
        Load NSE symbol -> BSE scrip code mapping from BSE's master list.
        
        Returns empty dict on failure. Cached for 24 hours.
        """
        def _fetch() -> dict[str, str]:
            try:
                # BSE's scrip master endpoint
                url = f"{_BSE_API}/BseGetMktData/w?ddlIndustry=&ddlStatus=&strSearch=Equity&strType=AllMkt"
                resp = requests.get(url, headers=_BSE_HEADERS, timeout=_TIMEOUT)
                if resp.status_code != 200:
                    logger.warning("[bse] scrip master returned HTTP %s", resp.status_code)
                    return {}
                
                data = resp.json()
                if not isinstance(data, dict) or "Table" not in data:
                    return {}
                
                table = data.get("Table", [])
                if not isinstance(table, list):
                    return {}
                
                # Build symbol -> scripcode mapping
                mapping: dict[str, str] = {}
                for row in table:
                    if not isinstance(row, dict):
                        continue
                    # BSE lists stocks with NSE symbol equivalents
                    scrip_cd = str(row.get("scripcd", "")).strip()
                    # Try to extract NSE symbol from name or security_id
                    nse_sym = str(row.get("NSEID", "") or row.get("SYMBOL", "")).strip().upper()
                    if scrip_cd and nse_sym:
                        mapping[nse_sym] = scrip_cd
                
                logger.info("[bse] loaded %d NSE->BSE scrip mappings", len(mapping))
                return mapping
                
            except Exception as e:
                logger.warning("[bse] scrip master fetch failed: %s", e)
                return {}
        
        return MARKET_CACHE.get_or_compute("bse_scrip_map_v1", _fetch, _TTL_SCRIP_MAP)

    def resolve_scrip_code(self, symbol: str) -> str | None:
        """
        NSE symbol -> BSE scrip code via lazy-loaded master list.
        
        Returns None if the symbol cannot be mapped.
        """
        if self._scrip_map is None:
            self._scrip_map = self._load_scrip_map()
        
        clean = symbol.upper().strip().replace("-EQ", "")
        return self._scrip_map.get(clean)

    def get_vwap(self, symbol: str) -> float | None:
        """
        Returns WAP (Volume Weighted Avg Price) from BSE StockTrading endpoint.
        
        Returns None if:
        - Symbol cannot be mapped to BSE scrip code
        - API request fails
        - WAP field is missing or invalid
        """
        scrip_code = self.resolve_scrip_code(symbol)
        if not scrip_code:
            return None
        
        key = f"bse_vwap_v1:{scrip_code}"
        
        def _fetch() -> float | None:
            try:
                url = f"{_BSE_API}/StockTrading/w?flag=&scripcode={scrip_code}"
                resp = requests.get(url, headers=_BSE_HEADERS, timeout=_TIMEOUT)
                if resp.status_code != 200:
                    logger.debug("[bse] VWAP for %s (scrip %s) returned HTTP %s", 
                               symbol, scrip_code, resp.status_code)
                    return None
                
                data = resp.json()
                if not isinstance(data, dict):
                    return None
                
                # BSE returns VWAP in the "WAP" field, often with comma separators
                raw_wap = data.get("WAP", "")
                if not raw_wap:
                    return None
                
                # Clean and parse
                clean_val = str(raw_wap).replace(",", "").strip()
                if not clean_val or clean_val in ("-", "NA"):
                    return None
                
                vwap = float(clean_val)
                return round(vwap, 2) if vwap > 0 else None
                
            except Exception as e:
                logger.debug("[bse] VWAP fetch failed for %s (scrip %s): %s", 
                           symbol, scrip_code, e)
                return None
        
        return MARKET_CACHE.get_or_compute(key, _fetch, _TTL_VWAP)


# Singleton instance
bse_client = BSEClient()
