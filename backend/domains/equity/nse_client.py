"""
domains/equity/nse_client.py

Direct client for the National Stock Exchange of India (NSE) official endpoints.
Fetches real-time equity quotes, fundamental metadata, 52-week ranges, P/E,
sector P/E, delivery data, and complete NSE master symbol search.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import Any

import pandas as pd
import requests

from domains.equity.sector_map import get_sector

logger = logging.getLogger(__name__)

NSE_BASE_URL = "https://www.nseindia.com"
NSE_EQUITY_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

API_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/get-quotes/equity",
    "X-Requested-With": "XMLHttpRequest",
}


class NSEClient:
    """
    Session-managed client for NSE India.
    Handles cookie lifecycle, master symbol caching, and quote parsing.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._cookie_timestamp: float = 0
        self._master_symbols: list[dict[str, str]] = []
        self._master_loaded: bool = False
        self._name_index: dict[str, str] = {}
        self._isin_index: dict[str, str] = {}

    def _ensure_indexes(self) -> None:
        """Build the symbol->name and ISIN->symbol maps once, on first use."""
        if self._name_index and self._isin_index:
            return
        master = self.load_master_symbols()
        self._name_index = {i["symbol"]: i["name"] for i in master}
        # NSE publishes an ISIN for every listed symbol (verified: 2,371 of 2,371), and
        # an ISIN survives a rename while the trading symbol does not. This is what
        # lets a holding recorded under a retired ticker still resolve, without anyone
        # maintaining a list of which names changed.
        self._isin_index = {i["isin"]: i["symbol"] for i in master if i.get("isin")}

    def is_listed(self, symbol: str) -> bool:
        """Whether `symbol` is currently in NSE's master list of live equities."""
        self._ensure_indexes()
        # An empty index means the download failed; assume listed rather than
        # declaring every symbol delisted on a network blip.
        if not self._name_index:
            return True
        return symbol.upper().strip() in self._name_index

    def symbol_for_isin(self, isin: str) -> str | None:
        """Current trading symbol for an ISIN, or None if it is not listed."""
        if not isin:
            return None
        self._ensure_indexes()
        return self._isin_index.get(isin.upper().strip())

    def name_for(self, symbol: str) -> str | None:
        """
        Company name for a symbol, from the master list.

        Indexed on first use rather than scanned: resolving a handful of peer names
        per analysis was otherwise a linear pass over ~2,400 rows each time.
        """
        self._ensure_indexes()
        return self._name_index.get(symbol.upper().strip())

    def _refresh_session_cookies(self) -> None:
        """Establish a clean session on NSE to acquire necessary cookies."""
        now = time.time()
        # Refresh cookies if older than 5 minutes or uninitialised
        if now - self._cookie_timestamp < 300:
            return

        try:
            resp = self._session.get(NSE_BASE_URL, headers=DEFAULT_HEADERS, timeout=8)
            if resp.status_code == 200:
                self._cookie_timestamp = now
        except Exception as e:
            logger.warning("[nse_client] Cookie refresh failed: %s", e)

    def load_master_symbols(self) -> list[dict[str, str]]:
        """
        Load the full list of ~2,200 active NSE equity stocks.
        Returns a list of dicts: [{'symbol': '...', 'name': '...', 'isin': '...'}]
        """
        if self._master_loaded and self._master_symbols:
            return self._master_symbols

        try:
            resp = requests.get(NSE_EQUITY_MASTER_URL, headers=DEFAULT_HEADERS, timeout=10)
            if resp.status_code == 200 and resp.text:
                reader = csv.DictReader(io.StringIO(resp.text))
                items: list[dict[str, str]] = []
                for row in reader:
                    sym = (row.get("SYMBOL") or "").strip().upper()
                    name = (row.get("NAME OF COMPANY") or "").strip()
                    isin = (row.get(" ISIN NUMBER") or row.get("ISIN NUMBER") or "").strip()
                    series = (row.get(" SERIES") or row.get("SERIES") or "").strip().upper()
                    if sym and series in ("EQ", "BE", "SM", "ST"):
                        items.append({
                            "symbol": sym,
                            "name": name or sym,
                            "isin": isin,
                        })
                if items:
                    self._master_symbols = items
                    self._master_loaded = True
                    return items
        except Exception as e:
            logger.warning("[nse_client] Master symbol download failed: %s", e)

        # Fallback to local high-volume seed if network download is blocked
        return self._get_fallback_symbols()

    def search(self, query: str, limit: int = 15) -> list[dict[str, Any]]:
        """
        Search NSE equities by ticker or company name.
        """
        q = query.upper().strip()
        if not q:
            return []

        master = self.load_master_symbols()
        exact_matches = []
        prefix_matches = []
        name_matches = []

        for item in master:
            sym = item["symbol"].upper()
            name = item["name"].upper()

            if sym == q:
                exact_matches.append(item)
            elif sym.startswith(q):
                prefix_matches.append(item)
            elif q in sym or q in name:
                name_matches.append(item)

        combined = exact_matches + prefix_matches + name_matches
        seen = set()
        unique = []
        for c in combined:
            if c["symbol"] not in seen:
                seen.add(c["symbol"])
                sector, industry = get_sector(c["symbol"])
                unique.append({
                    "symbol": c["symbol"],
                    "name": c["name"],
                    "sector": sector,
                    "industry": industry,
                    "ticker": f"{c['symbol']}.NS",
                })
                if len(unique) >= limit:
                    break

        return unique

    #: `/api/quote-equity` returns 403 by exchange policy, not by bot detection.
    #: Verified from a residential Indian IP with full Chrome TLS impersonation: the
    #: cookie bootstrap and the endpoint both return Akamai "Access Denied", while
    #: `/api/corporates-corporateActions`, `/api/corporate-announcements` and
    #: `/api/event-calendar` return 200 from the same session. So this is not something
    #: better headers or a different host can fix, and each attempt cost ~4-8s inside a
    #: request - five of them per analysis, via the peer loop, for five null prices.
    #:
    #: Left callable and off by default rather than deleted: if NSE ever reopens the
    #: endpoint, flipping this is the whole change.
    QUOTE_API_ENABLED = False

    def get_equity_quote(self, symbol: str) -> dict[str, Any] | None:
        """
        Fetch direct equity quote and metadata from NSE's official API.

        Returns None without touching the network while `QUOTE_API_ENABLED` is False.
        """
        if not self.QUOTE_API_ENABLED:
            return None

        clean = symbol.upper().strip().replace("-EQ", "").replace(".NS", "").replace(".BO", "")
        self._refresh_session_cookies()

        url = f"{NSE_BASE_URL}/api/quote-equity?symbol={clean}&section=trade_info"
        try:
            resp = self._session.get(url, headers=API_HEADERS, timeout=8)
            if resp.status_code == 401 or resp.status_code == 403:
                # Cookie expired, refresh and retry once
                self._cookie_timestamp = 0
                self._refresh_session_cookies()
                resp = self._session.get(url, headers=API_HEADERS, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                return self._parse_nse_quote(clean, data)
        except Exception as e:
            logger.warning("[nse_client] NSE quote fetch failed for %s: %s", clean, e)

        return None

    def _parse_nse_quote(self, symbol: str, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw NSE payload into standardized structure."""
        info = data.get("info") or {}
        price_info = data.get("priceInfo") or {}
        metadata = data.get("metadata") or {}
        security_info = data.get("securityInfo") or {}
        trade_info = data.get("tradeInfo") or {}
        week_hl = price_info.get("weekHighLow") or {}

        company_name = info.get("companyName") or symbol
        industry = info.get("industry") or metadata.get("pdSectorInd") or ""
        sector, mapped_industry = get_sector(symbol)
        if not industry:
            industry = mapped_industry

        last_price = float(price_info.get("lastPrice") or price_info.get("close") or 0.0)
        previous_close = float(price_info.get("previousClose") or last_price)
        change = float(price_info.get("change") or (last_price - previous_close))
        p_change = float(price_info.get("pChange") or (0.0 if not previous_close else (change / previous_close) * 100))

        week52_high = float(week_hl.get("max") or 0.0) or None
        week52_low = float(week_hl.get("min") or 0.0) or None

        # P/E Ratio directly from NSE metadata
        pe_ratio = metadata.get("pdSymbolPe")
        if pe_ratio is not None:
            try:
                pe_ratio = float(pe_ratio)
            except (ValueError, TypeError):
                pe_ratio = None

        sector_pe = metadata.get("pdSectorPe")
        if sector_pe is not None:
            try:
                sector_pe = float(sector_pe)
            except (ValueError, TypeError):
                sector_pe = None

        issued_size = security_info.get("issuedSize")
        market_cap_cr = None
        if issued_size and last_price:
            try:
                market_cap_cr = round((float(issued_size) * last_price) / 1e7, 0)
            except (ValueError, TypeError):
                pass

        vwap = price_info.get("vwap")
        if vwap is not None:
            try:
                vwap = float(vwap)
            except (ValueError, TypeError):
                vwap = None

        delivery_pct = None
        del_pos = trade_info.get("deliveryPosition") or {}
        if del_pos.get("deliveryToTradedQuantity") is not None:
            try:
                delivery_pct = float(del_pos.get("deliveryToTradedQuantity"))
            except (ValueError, TypeError):
                pass

        return {
            "source": "NSE",
            "symbol": symbol,
            "name": company_name,
            "sector": sector,
            "industry": industry,
            "current_price": last_price,
            "previous_close": previous_close,
            "change": round(change, 2),
            "p_change": round(p_change, 2),
            "vwap": vwap,
            "pe_ratio": pe_ratio,
            "sector_pe": sector_pe,
            "market_cap_cr": market_cap_cr,
            "week52_high": week52_high,
            "week52_low": week52_low,
            "delivery_pct": delivery_pct,
            "isin": info.get("isin"),
            "series": metadata.get("series") or "EQ",
        }

    def _get_fallback_symbols(self) -> list[dict[str, str]]:
        """Fallback seed for NSE search if network master download is unavailable."""
        return [
            {"symbol": "RELIANCE", "name": "Reliance Industries Ltd", "isin": "INE002A01018"},
            {"symbol": "TCS", "name": "Tata Consultancy Services Ltd", "isin": "INE467B01029"},
            {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd", "isin": "INE040A01034"},
            {"symbol": "INFY", "name": "Infosys Ltd", "isin": "INE009A01021"},
            {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd", "isin": "INE090A01021"},
            {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Ltd", "isin": "INE030A01027"},
            {"symbol": "ITC", "name": "ITC Ltd", "isin": "INE154A01025"},
            {"symbol": "SBIN", "name": "State Bank of India", "isin": "INE062A01020"},
            {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd", "isin": "INE397D01024"},
            {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd", "isin": "INE296A01024"},
            {"symbol": "LT", "name": "Larsen & Toubro Ltd", "isin": "INE018A01030"},
            {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Ltd", "isin": "INE237A01028"},
            {"symbol": "AXISBANK", "name": "Axis Bank Ltd", "isin": "INE238A01034"},
            {"symbol": "WIPRO", "name": "Wipro Ltd", "isin": "INE075A01022"},
            {"symbol": "HCLTECH", "name": "HCL Technologies Ltd", "isin": "INE860A01027"},
            {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Ltd", "isin": "INE044A01036"},
            {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd", "isin": "INE585B01010"},
            {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd", "isin": "INE155A01022"},
            {"symbol": "TATASTEEL", "name": "Tata Steel Ltd", "isin": "INE081A01020"},
            {"symbol": "NTPC", "name": "NTPC Ltd", "isin": "INE733E01010"},
            {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Ltd", "isin": "INE752E01010"},
            {"symbol": "ONGC", "name": "Oil and Natural Gas Corporation Ltd", "isin": "INE213A01029"},
            {"symbol": "TITAN", "name": "Titan Company Ltd", "isin": "INE280A01028"},
            {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Ltd", "isin": "INE481G01011"},
            {"symbol": "M&M", "name": "Mahindra & Mahindra Ltd", "isin": "INE101A01026"},
            {"symbol": "ADANIPORTS", "name": "Adani Ports and Special Economic Zone Ltd", "isin": "INE742F01042"},
            {"symbol": "COALINDIA", "name": "Coal India Ltd", "isin": "INE522F01014"},
            {"symbol": "JSWSTEEL", "name": "JSW Steel Ltd", "isin": "INE019A01038"},
            {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd", "isin": "INE917I01010"},
            {"symbol": "ASIANPAINT", "name": "Asian Paints Ltd", "isin": "INE021A01026"},
            {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Ltd", "isin": "INE089A01023"},
            {"symbol": "CIPLA", "name": "Cipla Ltd", "isin": "INE059A01026"},
            {"symbol": "ZOMATO", "name": "Zomato Ltd", "isin": "INE758T01015"},
            {"symbol": "TRENT", "name": "Trent Ltd", "isin": "INE849A01020"},
            {"symbol": "DMART", "name": "Avenue Supermarts Ltd", "isin": "INE192R01011"},
            {"symbol": "HAL", "name": "Hindustan Aeronautics Ltd", "isin": "INE066F01012"},
            {"symbol": "BEL", "name": "Bharat Electronics Ltd", "isin": "INE263A01024"},
            {"symbol": "JIOFIN", "name": "Jio Financial Services Ltd", "isin": "INE758E01017"},
            {"symbol": "VEDL", "name": "Vedanta Ltd", "isin": "INE205A01025"},
            {"symbol": "SWIGGY", "name": "Swiggy Ltd", "isin": "INE00H001014"},
        ]


# Singleton instance across backend
nse_client = NSEClient()
