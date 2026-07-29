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
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, Any, List
from shared import config
from shared.cache import MarketCache
from shared.services.cache import MARKET_CACHE
from shared.services.providers.factory import get_provider
from shared.config import BENCHMARKS, FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT

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
_ISIN_MISS_CACHE:     Dict[str, float] = {}     # ISIN → ts of last failed resolution
_NAV_SERIES_CACHE:    Dict[str, Tuple[float, pd.Series]] = {}  # code → (ts, series)
_TER_CACHE:           Dict[str, float] = {}      # scheme_code → TER %
_TER_CACHE_TS:        float = 0.0                # timestamp of last TER fetch

_NAV_CACHE_TTL = 3600       # 1 hour
_TER_CACHE_TTL = 86400      # 24 hours (AMFI updates once daily)
_ISIN_MISS_TTL = 3600       # 1 hour — retry unresolvable ISINs occasionally, not constantly

def clear_market_data_cache():
    """Invalidate all in-memory market data caches."""
    global _ISIN_TO_CODE_CACHE, _NAV_SERIES_CACHE, _TER_CACHE, _TER_CACHE_TS, _LIVE_NAV_CACHE, _LIVE_NAV_CACHE_TS
    with _CACHE_LOCK:
        _ISIN_TO_CODE_CACHE.clear()
        _ISIN_MISS_CACHE.clear()
        _NAV_SERIES_CACHE.clear()
        _TER_CACHE.clear()
        _TER_CACHE_TS = 0.0
        _LIVE_NAV_CACHE.clear()
        _LIVE_NAV_CACHE_TS = 0.0
    # The parsed AMFI bundle and NAV series live in the L1 tier now.
    MARKET_CACHE.clear()


# ---------------------------------------------------------------------------
# Live NAVs from AMFI daily file
# ---------------------------------------------------------------------------

_LIVE_NAV_CACHE: Dict[str, float] = {}
_LIVE_NAV_CACHE_TS: float = 0.0

def _fetch_amfi_data_uncached() -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str]]:
    """
    Unified AMFI fetch — downloads NAVAll.txt once and populates both
    live NAV cache and ISIN-to-Code mapping.

    Always hits the network. Call `_fetch_amfi_data()` instead unless you
    specifically need to force a refresh.
    """
    global _LIVE_NAV_CACHE, _LIVE_NAV_CACHE_TS, _ISIN_TO_CODE_CACHE
    
    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    live_map: Dict[str, float] = {}
    isin_map: Dict[str, str]   = {}
    date_map: Dict[str, str]   = {}
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read().decode("utf-8", errors="ignore")

        for line in data.splitlines():
            if ";" not in line: continue
            parts = [p.strip() for p in line.split(";")]
            if len(parts) < 6: continue
            
            code  = parts[0]
            isin1 = parts[1].upper()
            isin2 = parts[2].upper() if len(parts) > 2 else ""
            nav_s = parts[4]
            date_s = parts[5]
            
            try:
                nav_v = float(nav_s)
                if isin1: 
                    live_map[isin1] = nav_v
                    date_map[isin1] = date_s
                if isin2: 
                    live_map[isin2] = nav_v
                    date_map[isin2] = date_s
            except ValueError: pass
            
            if isin1: isin_map[isin1] = code
            if isin2: isin_map[isin2] = code
            
        with _CACHE_LOCK:
            _LIVE_NAV_CACHE = live_map
            _LIVE_NAV_CACHE_TS = time.time()
            _ISIN_TO_CODE_CACHE.update(isin_map)
            
    except Exception as e:
        logger.error(f"[AMFI UNIFIED ERROR] {e}")

    return live_map, isin_map, date_map

from shared.cache import MarketCache
import logging
logger = logging.getLogger(__name__)


# The AMFI bundle is the single most reused network payload in the app: it values
# every holding, resolves every ISIN, and dates every NAV. It used to be refetched
# and reparsed on every call - including once per unresolvable ISIN - so caching the
# *parsed* triple here removes the largest source of redundant network I/O.
#
# Treated as immutable by convention: callers must not mutate the returned maps.
# They are handed out by reference deliberately, because deep-copying ~50k-entry
# dicts on every access would cost more than the fetch it replaces.
_AMFI_BUNDLE_KEY = "amfi_bundle_v1"


def _load_amfi_bundle() -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str]]:
    """
    L2 (disk) then network. Used as the producer behind the L1 cache.

    Reading disk before the network matters for cold starts: a free-tier instance
    that just woke has an empty L1 but may still have a usable bundle on disk, and
    re-downloading several MB to rebuild what we already have is pure latency.
    """
    if config.CACHE_TTL_MINUTES > 0:
        cached = MarketCache.get(_AMFI_BUNDLE_KEY)
        if isinstance(cached, dict) and cached.get("live"):
            live_map = {k: float(v) for k, v in cached["live"].items()}
            isin_map = dict(cached.get("isin") or {})
            date_map = dict(cached.get("date") or {})
            # Keep the legacy module globals coherent with what we just served.
            with _CACHE_LOCK:
                global _LIVE_NAV_CACHE, _LIVE_NAV_CACHE_TS
                _LIVE_NAV_CACHE = live_map
                _LIVE_NAV_CACHE_TS = time.time()
                _ISIN_TO_CODE_CACHE.update(isin_map)
            return live_map, isin_map, date_map

    live_map, isin_map, date_map = _fetch_amfi_data_uncached()

    if live_map and config.CACHE_TTL_MINUTES > 0:
        MarketCache.set(
            _AMFI_BUNDLE_KEY,
            {"live": live_map, "isin": isin_map, "date": date_map},
        )

    return live_map, isin_map, date_map


def _fetch_amfi_data(refresh: bool = False) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str]]:
    """
    Cached AMFI bundle: (live_navs_by_isin, isin_to_code, nav_date_by_isin).

    Single-flight, so a burst of concurrent holdings enrichment triggers one
    download rather than one per holding.
    """
    ttl = config.CACHE_TTL_MINUTES * 60
    if refresh or ttl <= 0:
        return _fetch_amfi_data_uncached()

    # copy_on_read=False: the bundle is three maps with tens of thousands of entries
    # and is treated as immutable by every consumer. Deep-copying it per access would
    # cost more than the download it replaces.
    return MARKET_CACHE.get_or_compute(
        _AMFI_BUNDLE_KEY, _load_amfi_bundle, ttl, copy_on_read=False
    )


def fetch_live_navs(refresh: bool = False) -> Dict[str, float]:
    """
    Fetch live NAVs from AMFI with persistent caching.
    
    This pulls the unified AMFI NAVAll.txt file which contains the latest end-of-day
    pricing for all mutual funds in India. It is highly efficient for valuing an entire
    portfolio (e.g., 20+ funds) simultaneously without incurring multiple API calls.
    
    Args:
        refresh (bool): If True, bypasses the cache and forces a fresh network pull.
        
    Returns:
        Dict[str, float]: A mapping of ISIN codes to their latest NAV as floats.
    """
    live_map, _, _ = _fetch_amfi_data(refresh=refresh)
    return live_map


def fetch_live_navs_with_date(refresh: bool = False) -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Returns both the NAV mapping and the NAV-date mapping.

    Shares the cached AMFI bundle with fetch_live_navs. This previously bypassed the
    cache entirely ("date mapping is not cached yet") and so forced a full multi-MB
    download on every upload and every /sync - the bundle now carries all three maps,
    so there is nothing left to bypass for.
    """
    live_map, _, date_map = _fetch_amfi_data(refresh=refresh)
    return live_map, date_map

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
    if not isin:
        return ""

    with _CACHE_LOCK:
        if isin in _ISIN_TO_CODE_CACHE:
            return _ISIN_TO_CODE_CACHE[isin]

        # Negative cache. Some ISINs in a CAS are simply not in AMFI's file (closed
        # schemes, segregated portfolios). Without this, every lookup for such an
        # ISIN falls through to a bundle refresh, and a single unresolvable holding
        # re-triggers that work on every request that touches it.
        missed_at = _ISIN_MISS_CACHE.get(isin)
        if missed_at is not None and (time.time() - missed_at) < _ISIN_MISS_TTL:
            return ""

    # Not known yet: consult the (cached) bundle in case it has appeared since.
    _, isin_map, _ = _fetch_amfi_data()

    code = (isin_map or {}).get(isin, "")
    if not code:
        with _CACHE_LOCK:
            code = _ISIN_TO_CODE_CACHE.get(isin, "")

    if not code:
        # Bounded TTL rather than permanent: AMFI can add a scheme later.
        with _CACHE_LOCK:
            _ISIN_MISS_CACHE[isin] = time.time()

    return code


# ---------------------------------------------------------------------------
# NAV History Fetch
# FIX #7: New functions required for all risk metric computation
# ---------------------------------------------------------------------------

def fetch_nav_series_by_code(scheme_code: str, days: int = 3650, refresh: bool = False) -> pd.Series:
    """
    Fetch NAV history from mfapi.in for a given scheme code.
    Returns pd.Series indexed by date (DatetimeIndex), sorted ascending.
    
    Fail-Safe Architecture:
    If mfapi.in is down, rate-limited, or returns an error, this explicitly catches 
    the exception and returns an empty pd.Series. This prevents the upstream engine 
    from crashing, allowing downstream systems to either trigger Yahoo Finance/NSELib 
    fallbacks (for benchmarks) or fail gracefully (for portfolio funds).
    """
    code_str = str(scheme_code).strip()
    full = _full_nav_series(code_str, refresh=refresh)
    return _slice_trailing(full, days)


# NAV history is always fetched in full and sliced locally, so the `days` argument
# never affects what is fetched or cached - only what is returned. Keeping one entry
# per scheme (rather than one per scheme+window) is what stops the same fund being
# downloaded three times because three call sites asked for 10, 3650 and 9999 days.
_NAV_LEAD_IN_DAYS = 30


def _slice_trailing(series: pd.Series, days: int) -> pd.Series:
    """
    Trim to the trailing `days` window, measured from the last observation.

    The extra lead-in gives downstream return/risk windows a little history to
    anchor on. Note this unifies a pre-existing inconsistency: the cache-hit path
    used `days + 30` while the fresh-fetch path used `days`, so the same call
    returned different lengths depending on cache state. `days + 30` wins because
    it is what production served in the common (warm) case.
    """
    if series.empty or days >= 9999:
        return series.copy()

    cutoff = series.index[-1] - timedelta(days=days + _NAV_LEAD_IN_DAYS)
    return series[series.index >= cutoff].copy()


def _full_nav_series(code_str: str, refresh: bool = False) -> pd.Series:
    """
    Full parsed NAV history for a scheme, cached as a *parsed* pd.Series.

    Caching the parsed object rather than the raw JSON map is the point. The disk
    tier stores `{"DD-MM-YYYY": nav}`, and rebuilding a Series from that means a
    `to_datetime` over the entire history plus a sort — which previously ran once per
    holding per request, making a cache hit nearly as expensive as a miss.
    """
    ttl = config.CACHE_TTL_MINUTES * 60
    if refresh or ttl <= 0:
        return _load_full_nav_series(code_str, refresh=refresh)

    return MARKET_CACHE.get_or_compute(
        f"nav_full|{code_str}",
        lambda: _load_full_nav_series(code_str, refresh=False),
        ttl,
    )


def _load_full_nav_series(code_str: str, refresh: bool) -> pd.Series:
    """L2 (disk) then network. Producer behind the L1 entry above."""
    cache_key = f"nav_series_{code_str}"

    if not refresh:
        cached_data = MarketCache.get(cache_key)
        if cached_data:
            try:
                series = pd.Series(cached_data)
                # dayfirst=True for DD-MM-YYYY dates, then sort chronologically.
                series.index = pd.to_datetime(series.index, dayfirst=True)
                return series.sort_index().astype(float)
            except Exception:
                pass  # corrupt/partial cache entry — fall through to the network

    try:
        provider = get_provider()
        series = provider.fetch_nav_series(code_str, 9999)  # always full history

        if series.empty:
            return pd.Series(dtype=float)

        series = series.sort_index()

        # Persist the raw map for next time (format expected by the disk cache)
        raw_map = {d.strftime("%d-%m-%Y"): float(v) for d, v in series.items()}
        MarketCache.set(cache_key, raw_map)

        return series

    except Exception:
        # Fail gracefully. Downstream systems handle the empty series.
        return pd.Series(dtype=float)


def fetch_nav_series_by_isin(isin: str, days: int = 1825, refresh: bool = False) -> pd.Series:
    """
    Fetch NAV history for a fund identified by its ISIN.
    
    This acts as a bridge function. It first resolves the ISIN (e.g., "INF879O01019")
    into an AMFI scheme code (e.g., "122639") using the AMFI NAV dictionary, and then
    delegates the actual historical fetching to `fetch_nav_series_by_code()`.
    
    Args:
        isin (str): The unique International Securities Identification Number.
        days (int): The number of trailing days of history to request.
        refresh (bool): Bypasses the cache if True.
        
    Returns:
        pd.Series: The historical NAV curve, or an empty Series if resolution fails.
    """
    code = resolve_scheme_code_from_isin(isin)
    if not code:
        return pd.Series(dtype=float)
        
    return fetch_nav_series_by_code(code, days=days, refresh=refresh)


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
        provider = get_provider()
        return provider.fetch_fund_meta(scheme_code)
    except Exception as e:
        logger.error(f"[METADATA ERROR] scheme={scheme_code}: {e}")
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
        logger.error(f"[PEER RETURNS ERROR] scheme={scheme_code}: {e}")
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Fund Search
# ---------------------------------------------------------------------------

def search_mutual_funds(query: str) -> List[Dict]:
    """
    Search for funds using MFapi.in search endpoint.

    Cached: the peer-comparison path issues up to eight of these per request with a
    small, repeating set of queries ("Large Cap Direct", "Flexi Cap Direct", ...), and
    /compare/search re-runs the same user queries constantly. Results are
    user-independent fund metadata, so a shared entry is correct.
    """
    ttl = config.CACHE_TTL_MINUTES * 60
    if ttl <= 0:
        return _search_mutual_funds_uncached(query)

    normalized = " ".join(str(query).strip().lower().split())
    if not normalized:
        return []

    return MARKET_CACHE.get_or_compute(
        f"fund_search|{normalized}",
        lambda: _search_mutual_funds_uncached(query),
        ttl,
    )


def _search_mutual_funds_uncached(query: str) -> List[Dict]:
    """Always hits the provider. Use search_mutual_funds() unless bypassing the cache."""
    try:
        provider = get_provider()
        raw_results = provider.search_funds(query)
        return [
            {
                "symbol":   str(item.get("schemeCode")),
                "name":     item.get("schemeName", "Unknown"),
                "type":     "Mutual Fund",
                "exchange": "PROVIDER",
            }
            for item in raw_results[:15]
        ]
    except Exception as e:
        logger.error(f"[SEARCH ERROR] query={query}: {e}")
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

    # ── 1. Debt / Liquid by name (HIGHEST priority to prevent misclassification) ──
    # FIX M-4: Moved debt checks FIRST. Without this, "HDFC Banking and PSU Debt Fund"
    # matches the "BANKING" keyword below and returns Nifty Bank instead of CRISIL Bond.
    if any(x in fn for x in ("LIQUID", "OVERNIGHT", "MONEYMARKET")):
        return ("LICNETFGSC.NS", "CRISIL Liquid Index")
    if any(x in fn for x in ("GILT", "GSEC", "GOVERNMENTSEC")):
        return ("LICNETFGSC.NS", "CRISIL Dynamic Gilt Index")
    if any(x in fn for x in ("BOND", "DEBT", "INCOME", "CREDITRISK", "CORPORATEBOND",
                               "SHORTDURATION", "MEDIUMDURATION", "DYNAMICBOND",
                               "FLOATINGRATE", "LOWDURATION", "ULTRASHORT")):
        return ("LICNETFGSC.NS", "CRISIL Composite Bond Index")
    # "Banking & PSU" as a debt category (not to be confused with Banking sectoral equity)
    if "BANKING" in fn and "PSU" in fn:
        return ("LICNETFGSC.NS", "CRISIL Banking & PSU Debt Index")

    # ── 2. Sectoral / Thematic (name-based) ──────────────────────────────
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
