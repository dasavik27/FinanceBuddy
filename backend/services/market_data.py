"""
services/market_data.py
All external data fetching — AMFI, mfapi.in, NSE, Yahoo Finance.

Key fixes vs v1.0:
- FIX #4 : fetch_fund_ter()  — live expense ratio from AMFI TER file
- FIX #7 : fetch_nav_series_by_isin() / fetch_nav_series_by_code() — NAV history
- FIX #7 : resolve_scheme_code_from_isin() — ISIN → scheme code lookup
- FIX #8 : PEER_UNIVERSE scheme codes corrected in config.py
- FIX #12: ER field always float, no string-handling needed
- FIX #1 : get_fund_benchmark() — correct cap_type normalisation
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.request
import yfinance as yf
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from core import config
from core.config import BENCHMARKS, FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT

# ── Thread-safe Cache Locks ──────────────────────────────────────────────
_CACHE_LOCK = threading.Lock()

# ── Resilient HTTP Session ───────────────────────────────────────────────
def _create_retry_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=1.0,  # 1s, 2s, 4s, 8s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

_HTTP_SESSION = _create_retry_session()


# ---------------------------------------------------------------------------
# Module-level caches  (simple in-memory; replace with Redis for multi-worker)
# ---------------------------------------------------------------------------
_ISIN_TO_CODE_CACHE:  Dict[str, str] = {}       # ISIN → scheme_code
_NAV_SERIES_CACHE:    Dict[str, Tuple[float, pd.Series]] = {}  # code → (ts, series)
_TER_CACHE:           Dict[str, float] = {}      # scheme_code → TER %
_TER_CACHE_TS:        float = 0.0                # timestamp of last TER fetch

_NAV_CACHE_TTL = 3600       # 1 hour
_TER_CACHE_TTL = 86400      # 24 hours (AMFI updates once daily)

def clear_market_data_cache():
    """Invalidate all in-memory market data caches."""
    global _ISIN_TO_CODE_CACHE, _NAV_SERIES_CACHE, _TER_CACHE, _TER_CACHE_TS, _LIVE_NAV_CACHE, _LIVE_NAV_CACHE_TS
    with _CACHE_LOCK:
        _ISIN_TO_CODE_CACHE.clear()
        _NAV_SERIES_CACHE.clear()
        _TER_CACHE.clear()
        _TER_CACHE_TS = 0.0
        _LIVE_NAV_CACHE.clear()
        _LIVE_NAV_CACHE_TS = 0.0


# ---------------------------------------------------------------------------
# Live NAVs from AMFI daily file
# ---------------------------------------------------------------------------

_LIVE_NAV_CACHE: Dict[str, float] = {}
_LIVE_NAV_CACHE_TS: float = 0.0

def _fetch_amfi_data() -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Unified AMFI fetch — downloads NAVAll.txt once and populates both
    live NAV cache and ISIN-to-Code mapping.
    """
    global _LIVE_NAV_CACHE, _LIVE_NAV_CACHE_TS, _ISIN_TO_CODE_CACHE
    
    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    live_map: Dict[str, float] = {}
    isin_map: Dict[str, str]   = {}
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read().decode("utf-8", errors="ignore")

        for line in data.splitlines():
            if ";" not in line: continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) < 5: continue
            
            code  = parts[0]
            isin1 = parts[1].upper()
            isin2 = parts[2].upper() if len(parts) > 2 else ""
            nav_s = parts[4]
            
            try:
                nav_v = float(nav_s)
                if isin1: live_map[isin1] = nav_v
                if isin2: live_map[isin2] = nav_v
            except ValueError: pass
            
            if isin1: isin_map[isin1] = code
            if isin2: isin_map[isin2] = code
            
        with _CACHE_LOCK:
            _LIVE_NAV_CACHE = live_map
            _LIVE_NAV_CACHE_TS = time.time()
            _ISIN_TO_CODE_CACHE.update(isin_map)
            
    except Exception as e:
        print(f"[AMFI UNIFIED ERROR] {e}")
        
    return live_map, isin_map

from core.cache import MarketCache

def fetch_live_navs(refresh: bool = False) -> Dict[str, float]:
    """
    Fetch live NAVs from AMFI with persistent caching.
    """
    cache_key = "amfi_live_navs"
    if not refresh and config.CACHE_TTL_MINUTES > 0:
        cached = MarketCache.get(cache_key)
        if cached: return cached

    live_map, _ = _fetch_amfi_data()
    if live_map and config.CACHE_TTL_MINUTES > 0:
        MarketCache.set(cache_key, live_map)
    return live_map

def _fetch_amfi_ter_all() -> Dict[str, float]:
    """
    Robust TER parser using header discovery (Fixes fragile parts[-1]).
    """
    global _TER_CACHE, _TER_CACHE_TS

    with _CACHE_LOCK:
        now = time.time()
        if config.CACHE_TTL_MINUTES > 0 and _TER_CACHE and (now - _TER_CACHE_TS) < _TER_CACHE_TTL:
            return _TER_CACHE

    url = "https://www.amfiindia.com/modules/TotalExpenseRatioDownload"
    ter_map: Dict[str, float] = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8", errors="ignore")

        lines = [l for l in data.splitlines() if l.strip()]
        if not lines: return {}
        
        # Header discovery
        header = lines[0].upper()
        delim = "," if "," in header else "\t"
        cols = [c.strip() for c in header.split(delim)]
        
        try:
            idx_code = cols.index("SCHEMECODE") if "SCHEMECODE" in cols else 0
            idx_ter  = -1
            for i, c in enumerate(cols):
                if "TER_DIRECT" in c or "DIRECT_PLAN" in c or "TER DIRECT" in c:
                    idx_ter = i
                    break
            if idx_ter == -1: idx_ter = len(cols) - 1 # Fallback to last
            
            for line in lines[1:]:
                parts = [p.strip() for p in line.split(delim)]
                if len(parts) <= max(idx_code, idx_ter): continue
                
                code = parts[idx_code]
                try:
                    val = float(parts[idx_ter].replace("%", ""))
                    ter_map[code] = val
                except ValueError: pass
        except Exception: pass

    except Exception: pass

    if ter_map:
        with _CACHE_LOCK:
            _TER_CACHE = ter_map
            _TER_CACHE_TS = now

    return ter_map


def fetch_fund_ter(scheme_code: str, plan: str = "Direct") -> Optional[float]:
    """
    Fetch live expense ratio for a fund from AMFI TER file.

    Parameters
    ----------
    scheme_code : AMFI scheme code (string or int)
    plan        : "Direct" or "Regular"

    Returns
    -------
    TER as float (e.g. 0.62 for 0.62%), or None if unavailable.
    """
    code_str = str(scheme_code).strip()
    ter_map  = _fetch_amfi_ter_all()
    return ter_map.get(code_str)


# ---------------------------------------------------------------------------
# ISIN → Scheme Code Resolution
# FIX #7: Required for NAV history fetch from mfapi
# ---------------------------------------------------------------------------

def resolve_scheme_code_from_isin(isin: str) -> str:
    """
    Resolve AMFI scheme code from ISIN using the AMFI NAV file.
    Cached in-process for the session lifetime.

    Parameters
    ----------
    isin : Either ISIN-growth (INF...) or ISIN-dividend

    Returns
    -------
    Scheme code string (e.g. "122639"), or "" if not found.
    """
    isin = isin.strip().upper()
    with _CACHE_LOCK:
        if isin in _ISIN_TO_CODE_CACHE:
            return _ISIN_TO_CODE_CACHE[isin]

    _, _ = _fetch_amfi_data()
    
    with _CACHE_LOCK:
        return _ISIN_TO_CODE_CACHE.get(isin, "")


# ---------------------------------------------------------------------------
# NAV History Fetch
# FIX #7: New functions required for all risk metric computation
# ---------------------------------------------------------------------------

def fetch_nav_series_by_code(scheme_code: str, days: int = 3650, refresh: bool = False) -> pd.Series:
    """
    Fetch NAV history from mfapi.in for a given scheme code.
    Returns pd.Series indexed by date (DatetimeIndex), sorted ascending.
    Supports persistent caching and manual refresh.
    """
    code_str = str(scheme_code).strip()
    cache_key = f"nav_series_{code_str}"
    
    if not refresh:
        cached_data = MarketCache.get(cache_key)
        if cached_data:
            series = pd.Series(cached_data).sort_index()
            # FIX: Add dayfirst=True for DD-MM-YYYY dates
            series.index = pd.to_datetime(series.index, dayfirst=True)
            if days < 9999:
                cutoff = series.index[-1] - timedelta(days=days + 30)
                return series[series.index >= cutoff].copy()
            return series.copy()

    try:
        url  = f"https://api.mfapi.in/mf/{code_str}"
        resp = _HTTP_SESSION.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            return pd.Series(dtype=float)

        # Build series: date string -> float nav
        raw_map = {rec["date"]: float(rec["nav"]) for rec in data}
        
        # Persist the raw map for next time
        MarketCache.set(cache_key, raw_map)
        
        series = pd.Series(
            {pd.to_datetime(d, dayfirst=True): v for d, v in raw_map.items()}
        ).sort_index()

        if days < 9999:
            cutoff = series.index[-1] - timedelta(days=days)
            return series[series.index >= cutoff]
        return series

    except Exception as e:
        print(f"[NAV FETCH ERROR] scheme={code_str}: {e}")
        return pd.Series(dtype=float)


def fetch_nav_series_by_isin(isin: str, days: int = 1825, refresh: bool = False) -> pd.Series:
    """
    Fetch NAV history for a fund identified by its ISIN.
    Resolves ISIN → scheme code → NAV series.

    Parameters
    ----------
    isin : Fund ISIN (e.g. "INF879O01019" for PPFAS Flexi Cap Direct Growth)
    days : Days of history to return

    Returns
    -------
    pd.Series (DatetimeIndex → float NAV), empty on failure.
    """
    code = resolve_scheme_code_from_isin(isin)
    if not code:
        print(f"[NAV FETCH] Could not resolve scheme code for ISIN={isin}")
        return pd.Series(dtype=float)
    return fetch_nav_series_by_code(code, days, refresh=refresh)


def fetch_nav_series_by_name(fund_name: str, days: int = 1825, refresh: bool = False) -> pd.Series:
    """Search mfapi.in by fund name and fetch its NAV series."""
    clean_q = fund_name.split("-")[0].replace("Direct", "").replace("Regular", "").replace("Plan", "").replace("Growth", "").strip()
    results = search_mutual_funds(clean_q)
    if not results:
        short_q = " ".join(clean_q.split()[:3])
        results = search_mutual_funds(short_q)
        
    if results and "symbol" in results[0]:
        code = results[0]["symbol"]
        return fetch_nav_series_by_code(code, days=days, refresh=refresh)
    return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Fund Metadata
# ---------------------------------------------------------------------------

def fetch_fund_metadata(scheme_code: str) -> Dict:
    """
    Fetch fund metadata from mfapi.in.
    Returns dict with scheme_name, fund_house, scheme_type, scheme_category.
    """
    try:
        url  = f"https://api.mfapi.in/mf/{scheme_code}"
        resp = _HTTP_SESSION.get(url, timeout=10)
        resp.raise_for_status()
        meta = resp.json().get("meta", {})
        return {
            "scheme_name":      meta.get("scheme_name", ""),
            "fund_house":       meta.get("fund_house", ""),
            "scheme_type":      meta.get("scheme_type", ""),
            "scheme_category":  meta.get("scheme_category", ""),
        }
    except Exception as e:
        print(f"[METADATA ERROR] scheme={scheme_code}: {e}")
        return {}


# ---------------------------------------------------------------------------
# Peer Returns
# ---------------------------------------------------------------------------

def fetch_peer_returns(scheme_code: str) -> Tuple[float, float]:
    """
    Fetch 1Y and 3Y trailing returns for a peer fund.

    Returns
    -------
    (return_1y_pct, return_3y_pct) as floats.
    Returns (0.0, 0.0) on failure — NOT fabricated values.
    """
    try:
        series = fetch_nav_series_by_code(str(scheme_code), days=1825)
        if series.empty or len(series) < 30:
            return 0.0, 0.0

        end_nav  = float(series.iloc[-1])
        end_date = series.index[-1]

        ret_1y, ret_3y = 0.0, 0.0

        # 1Y
        target_1y  = end_date - timedelta(days=365)
        past_1y    = series[series.index <= target_1y]
        if not past_1y.empty:
            nav_1y = float(past_1y.iloc[-1])
            if nav_1y > 0:
                ret_1y = round((end_nav / nav_1y - 1) * 100, 2)

        # 3Y CAGR
        target_3y = end_date - timedelta(days=1095)
        past_3y   = series[series.index <= target_3y]
        if not past_3y.empty:
            nav_3y = float(past_3y.iloc[-1])
            if nav_3y > 0:
                ret_3y = round(((end_nav / nav_3y) ** (1 / 3) - 1) * 100, 2)

        return ret_1y, ret_3y

    except Exception as e:
        print(f"[PEER RETURNS ERROR] scheme={scheme_code}: {e}")
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Fund Search
# ---------------------------------------------------------------------------

def search_mutual_funds(query: str) -> List[Dict]:
    """Search for funds using MFapi.in search endpoint."""
    try:
        url  = f"https://api.mfapi.in/mf/search?q={query}"
        resp = _HTTP_SESSION.get(url, timeout=8)
        resp.raise_for_status()
        return [
            {
                "symbol":   str(item["schemeCode"]),
                "name":     item.get("schemeName", "Unknown"),
                "type":     "Mutual Fund",
                "exchange": "AMFI",
            }
            for item in resp.json()[:15]
        ]
    except Exception as e:
        print(f"[SEARCH ERROR] query={query}: {e}")
        return []


def get_nse_indices(query: str) -> List[Dict]:
    """Search for NSE indices."""
    try:
        from nsepython import nse_get_index_list
        indices = nse_get_index_list() or []
        return [
            {"symbol": name, "name": name, "type": "Index", "exchange": "NSE"}
            for name in indices
            if query.lower() in name.lower()
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Benchmark Selection
# FIX #1: Correct cap_type normalisation — prevents PPFAS → Nifty 50 fallthrough
# ---------------------------------------------------------------------------

def get_fund_benchmark(category: str, cap_type: str, fund_name: str) -> Tuple[str, str]:
    """
    Determine the appropriate benchmark index for a given fund.

    Priority order:
    1. Fund name keywords (sectoral / thematic)
    2. cap_type lookup (normalised)
    3. category lookup
    4. Default: Nifty 50

    Parameters
    ----------
    category  : Broad category ("Equity", "Debt", "Hybrid", etc.)
    cap_type  : SEBI cap type from CAS ("Flexi Cap", "Mid Cap", etc.)
    fund_name : Full fund name for keyword matching

    Returns
    -------
    (yahoo_ticker, display_name)
    """
    fn = fund_name.upper().replace(" ", "").replace("-", "")

    # ── 1. Sectoral / Thematic (name-based, highest priority) ────────────
    if any(x in fn for x in ("BANK", "BANKING", "FINANCIAL", "FINSERV")):
        return ("^NSEBANK", "Nifty Bank TRI")
    if any(x in fn for x in ("INFOTECH", "TECH", "DIGIT", "SOFTWARE")) and "IT" in fn:
        return ("^CNXIT", "Nifty IT TRI")
    if any(x in fn for x in ("PHARMA", "HEALTH", "MEDIC", "LIFESCIENCE")):
        return ("^CNXPHARMA", "Nifty Pharma TRI")
    if "INFRA" in fn and "FINANCIAL" not in fn:
        return ("^CNXINFRA", "Nifty Infra TRI")
    if any(x in fn for x in ("INTERNATIONAL", "OVERSEAS", "NASDAQ", "GLOBAL", "USTECH")):
        return ("^GSPC", "S&P 500 TRI")
    if "GOLD" in fn:
        return ("GC=F", "Gold Spot TRI")

    # ── 2. Debt / Liquid by name ──────────────────────────────────────────
    if any(x in fn for x in ("LIQUID", "OVERNIGHT", "MONEYMARKET")):
        return ("LICNETFGSC.NS", "CRISIL Liquid Index")
    if any(x in fn for x in ("GILT", "GSEC", "GOVERNMENTSEC")):
        return ("LICNETFGSC.NS", "Nifty 10yr G-Sec Index")
    if any(x in fn for x in ("BOND", "DEBT", "INCOME", "CREDITRISK", "CORPORATEBOND")):
        return ("LICNETFGSC.NS", "CRISIL Composite Bond")

    # ── 3. Cap-type lookup (normalised to strip whitespace/case) ──────────
    cap_norm = str(cap_type or "").strip()
    if cap_norm in FUND_BENCH_BY_CAP:
        return FUND_BENCH_BY_CAP[cap_norm]

    # Try case-insensitive match
    cap_upper = cap_norm.upper()
    for key, val in FUND_BENCH_BY_CAP.items():
        if key.upper() == cap_upper:
            return val

    # ── 4. Category-level fallback ────────────────────────────────────────
    if category in FUND_BENCH_BY_CAT:
        return FUND_BENCH_BY_CAT[category]

    # ── 5. Hard default ───────────────────────────────────────────────────
    return ("^NSEI", "Nifty 50 TRI")
