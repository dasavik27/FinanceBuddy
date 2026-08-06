"""
services/market_indices.py
Fetches and aligns index/benchmark data (Nifty 50, Sensex, Gold, etc.)
from Yahoo Finance with mfapi.in historical mutual fund datasets.

Benchmark splicing: a 3-tier fallback cascade for index proxy benchmarking
(e.g. Nifty Smallcap 250), so a single upstream outage does not blank a chart:
1. MFAPI.in (Primary): Fetches accurate NAVs from actual index funds.
2. Yahoo Finance NSE (Fallback 1): If MFAPI is down, fetches NSE tickers (e.g. ^CNXSC).
3. Yahoo Finance BSE (Fallback 2): If Yahoo drops NSE data (frequent issue), fetches
   BSE equivalents (e.g. BSE-SMLCAP.BO).

This used to claim a fourth tier reading directly from the NSE API via nselib. That
function existed but nothing ever called it - `_fetch_benchmark_series_uncached` went
no further than the BSE fallback - so the documented resilience was not real. It has
been deleted rather than wired up: it was also the only outbound HTTP call in the
backend with no timeout at all (nselib issues bare `requests.get`), plus a
`time.sleep(0.5)` loop, which is precisely what must not run on a single worker.
Restoring a fourth tier means giving it an explicit timeout first.
"""

# yfinance is imported lazily inside the two functions that need it. It is a heavy
# import (it pulls its own pandas/lxml/requests machinery) and this module is loaded
# at startup by every mutual-fund router, so paying for it eagerly costs resident
# memory on a 512 MB box even when no Yahoo-backed benchmark is ever requested.
# Same rationale as the camelot/opencv deferral noted in requirements.txt.
import pandas as pd
import numpy as np
import requests
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from shared.services.providers.factory import get_provider
from shared.services.cache import MARKET_CACHE, ttl_for
import logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
# Benchmark series live in the shared L1 tier (bounded by bytes, single-flighted,
# and reported by /health/cache) rather than in a module-level dict here. The prefix
# lets a refresh clear just this family of entries.
_BENCH_L1_PREFIX = "bench_full|"

# Benchmarks are always fetched at full history and sliced on return, so the
# requested window never fragments the cache.
_FULL_HORIZON_DAYS = 9999

# TTL for the bounded-window fallback, including when it comes back empty. Shorter
# than the main entry because this path only runs for tickers the primary fetch could
# not satisfy: long enough to stop per-request retries, short enough to recover
# quickly once the upstream does.
_BENCH_FALLBACK_TTL = 900


def clear_benchmark_cache():
    """Invalidate all cached benchmark series."""
    MARKET_CACHE.delete_prefix(_BENCH_L1_PREFIX)


# ---------------------------------------------------------------------------
# Live Market Summary
# ---------------------------------------------------------------------------

_MARKET_SUMMARY_KEY = "nifty_live_summary_v1"

# Short, because this is a live quote. Long enough that N browser tabs polling on a
# 60s interval collapse onto roughly one upstream call per minute in total.
_MARKET_SUMMARY_TTL = 60


def fetch_live_market_summary() -> Dict:
    """
    Live Nifty 50 price and 1D change, cached and single-flighted.

    This was the only completely uncached network path left on a polled endpoint.
    /market/summary is hit once a minute by every open tab, and the call below is
    expensive in the worst case: yfinance's `fast_info` performs a cookie/crumb
    handshake (30s default timeout) plus a quote fetch (30s) plus a timezone lookup
    (10s). Yahoo rate-limiting is routine, and without a cache every poll from every
    tab paid the full timeout while holding a worker thread.

    The fallback dict is cached too - deliberately. Caching only successes means a
    rate-limited upstream is retried on every single request, which is exactly when
    you least want to be hammering it.
    """
    from shared import config

    if config.CACHE_TTL_MINUTES <= 0:
        return _fetch_live_market_summary_uncached()

    return MARKET_CACHE.get_or_compute(
        _MARKET_SUMMARY_KEY, _fetch_live_market_summary_uncached, _MARKET_SUMMARY_TTL
    )


def _fetch_live_market_summary_uncached() -> Dict:
    """
    Fetch live Nifty 50 price and 1D change from Yahoo Finance.
    Returns a safe fallback dict on any failure — never raises.
    """
    try:
        import yfinance as yf  # lazy: see note at top of module

        ticker = yf.Ticker("^NSEI")
        info   = ticker.fast_info
        price  = getattr(info, "last_price", None)
        prev   = getattr(info, "previous_close", None)

        if price and prev and prev > 0:
            change = price - prev
            pct    = (change / prev) * 100
            return {
                "nifty": {
                    "price":      round(float(price), 2),
                    "change":     round(float(change), 2),
                    "change_pct": round(float(pct), 2),
                    "is_live":    True,
                }
            }
    except Exception as e:  # pragma: no cover — defensive / hard to exercise in unit tests
        logger.error(f"[MARKET ERROR] Nifty live fetch failed: {e}")  # pragma: no cover — defensive / hard to exercise in unit tests

    # Return stale/fallback data — explicitly flagged as not live
    return {  # pragma: no cover — defensive / hard to exercise in unit tests
        "nifty": {
            "price":      0.0,
            "change":     0.0,
            "change_pct": 0.0,
            "is_live":    False,
        }
    }


# ---------------------------------------------------------------------------
# Benchmark Series Fetching
# ---------------------------------------------------------------------------

def fetch_benchmark_series(ticker: str, period_days: int = 365, refresh: bool = False) -> pd.Series:
    """
    Fetch benchmark history as a pd.Series (DatetimeIndex → float).

    Supports:
    - Yahoo Finance tickers (^NSEI, ^CRSLDX, GOLDBEES.NS, ^GSPC, etc.)
    - MF scheme codes (5+ digit integers as strings)
    - Synthetic benchmarks (HYBRID_50_50)

    Parameters
    ----------
    ticker      : Yahoo Finance symbol, scheme code, or synthetic key
    period_days : Days of history to fetch (9999 = all available)
    refresh     : Force fresh download bypassing cache

    Returns
    -------
    pd.Series sorted ascending by date.
    EMPTY SERIES on failure — caller must handle gracefully.
    Never returns fabricated data.
    """
    from shared import config
    if config.CACHE_TTL_MINUTES <= 0 or refresh:
        return _fetch_benchmark_series_uncached(ticker, period_days)

    # Per-datatype TTL rather than the single global CACHE_TTL_MINUTES (default 60).
    # Index history only changes at market close, so a 60-minute TTL meant
    # re-downloading settled historical series ~24 times a day. The policy table
    # already declared the right value; nothing was reading it.
    ttl_sec = ttl_for("market_indices")

    # Cache ONE full-history series per ticker and slice locally.
    #
    # The cache used to key on f"{ticker}_{period_days}", which fragmented badly:
    # a single dashboard load asks for the same index at 1855, 9999 and
    # max(perf_days+30, 365) days, so the same series was downloaded three times and
    # stored three times. Keying on the ticker alone collapses that to one fetch.
    # Slicing a full series is equivalent because the trim is measured from the last
    # observation, exactly as _fetch_yahoo_series does it.
    full = MARKET_CACHE.get_or_compute(
        f"{_BENCH_L1_PREFIX}{ticker}",
        lambda: _fetch_benchmark_series_uncached(ticker, _FULL_HORIZON_DAYS),
        ttl_sec,
    )

    if full is None or full.empty:
        # A few tickers only respond to a bounded window (Yahoo is inconsistent about
        # very long ranges), so fall back to honouring exactly what the caller asked.
        #
        # This fallback is itself cached, keyed by (ticker, period). Previously it was
        # not, and because an empty result was stored in the full-history entry above,
        # the code could never tell "not cached" from "cached as empty" - so a ticker
        # Yahoo refuses re-ran the fallback on *every* request, forever. For a Yahoo
        # symbol that path makes two downloads (~20s), and /benchmark-overlay asks for
        # four benchmarks, so it was roughly 80s of dead upstream work per request.
        return MARKET_CACHE.get_or_compute(
            f"{_BENCH_L1_PREFIX}{ticker}|{period_days}",
            lambda: _fetch_benchmark_series_uncached(ticker, period_days),
            _BENCH_FALLBACK_TTL,
        )

    return _slice_trailing_days(full, period_days)


def _slice_trailing_days(series: pd.Series, period_days: int) -> pd.Series:
    """
    Trim to the trailing window, measured from the final observation.

    Mirrors the trimming in _fetch_yahoo_series so a sliced full-history series is
    interchangeable with one fetched at that period directly.
    """
    if series.empty or period_days >= _FULL_HORIZON_DAYS:
        return series.copy()

    cutoff = series.index[-1] - timedelta(days=period_days)
    return series[series.index >= cutoff].copy()


# Reverse map for human names from NSE search
_INDEX_ALIAS_MAP = {
    "NIFTY 50": "^NSEI",
    "NIFTY 500": "^CRSLDX",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY MIDCAP 150": "NIFTYMIDCAP150.NS",
    "NIFTY SMALLCAP 250": "^CNXSC",
    "S&P 500": "^GSPC",
    "GOLD": "GC=F"
}

_MFAPI_TO_YAHOO_MAP = {
    "120716": "^NSEI",          # Nifty 50
    "120711": "^NSEI",          # Nifty Next 50 (Proxy)
    "147726": "NIFTYMIDCAP150.NS", # Nifty Midcap 150
    "147724": "^CNXSC",         # Nifty Smallcap 250
    "147702": "^CRSLDX",        # Nifty 500
    "153432": "^NSEBANK",       # Nifty Bank
    "119598": "LICNETFGSC.NS",  # CRISIL Bond Proxy
    "119596": "LICNETFGSC.NS"   # Liquid Proxy
}

def benchmark_uses_price_index_blend(ticker: str, period_days: int) -> bool:
    """
    True when this benchmark request will (or may) splice pre-launch history
    from a Yahoo PRICE index onto the modern index-fund NAV series — see
    _splice_benchmark_series. The primary path (mfapi scheme code) is a real
    TRI proxy (actual index-fund NAV, dividends already reinvested), but no
    free TRI history exists for Indian indices before most index funds
    launched, so long lookbacks (5Y/All-Time) blend in a price-only tail that
    slightly understates returns for that older stretch (~1-1.5%/yr of
    foregone dividends). Used purely to disclose the caveat, not to fix it —
    there's no free TRI data source to fetch instead.
    """
    return str(ticker).strip().isdigit() and str(ticker).strip() in _MFAPI_TO_YAHOO_MAP and period_days > 1000


def _splice_benchmark_series(mf_series: pd.Series, yf_series: pd.Series) -> pd.Series:
    """
    Mathematically splices a historical Yahoo Index curve onto a modern MFAPI NAV curve.
    
    Why this is needed:
    Many Indian index funds (MFAPI) only launched recently (e.g., 2019+). To compute long-term 
    XIRR (e.g. from a 2015 investment), we need historical data. This engine scales the 
    older Yahoo Index data perfectly so it bridges seamlessly onto the exact modern MFAPI NAV.
    """
    if mf_series.empty: return yf_series
    if yf_series.empty: return mf_series
    
    mf_start = mf_series.index.min()
    yf_past = yf_series[yf_series.index < mf_start]
    
    if yf_past.empty: return mf_series
        
    overlap_yf = yf_series[yf_series.index <= mf_start]
    if overlap_yf.empty: return mf_series
        
    yf_overlap_price = overlap_yf.iloc[-1]
    mf_start_price = mf_series.iloc[0]
    
    if float(yf_overlap_price) == 0: return mf_series
    multiplier = float(mf_start_price) / float(yf_overlap_price)
    
    yf_scaled = yf_past * multiplier
    return pd.concat([yf_scaled, mf_series]).sort_index()

def _fetch_benchmark_series_uncached(ticker: str, period_days: int) -> pd.Series:
    """Internal — no cache logic."""

    # ── 1. Synthetic: HYBRID 50/50 ────────────────────────────────────────
    if ticker == "HYBRID_50_50":
        return _build_hybrid_benchmark(period_days)

    # ── 1.5 Index Aliases (e.g. "NIFTY 50" -> "^NSEI") ────────────────────
    t_upper = ticker.strip().upper()
    if t_upper in _INDEX_ALIAS_MAP:
        ticker = _INDEX_ALIAS_MAP[t_upper]

    # ── 2. ISIN (e.g. "INF879O01019") ─────────────────────────────────────
    if len(str(ticker)) == 12 and str(ticker)[:2].isalpha():
        from shared.services.market_data import fetch_nav_series_by_isin
        return fetch_nav_series_by_isin(ticker, period_days)

    # ── 3. MF Scheme Code (numeric string, e.g. "122639") ─────────────────
    if str(ticker).strip().isdigit() and len(str(ticker).strip()) >= 5:
        from shared.services.market_data import fetch_nav_series_by_code
        series = fetch_nav_series_by_code(ticker, period_days)
        
        # ── HYBRID FALLBACK: If MFAPI series is too short for history, splice with Yahoo
        if str(ticker) in _MFAPI_TO_YAHOO_MAP:
            required_start = datetime.now() - timedelta(days=period_days if period_days < 9999 else 3650)
            if series.empty or (period_days > 1000 and series.index.min() > required_start):
                yahoo_ticker = _MFAPI_TO_YAHOO_MAP[str(ticker)]
                logger.info(f"[HYBRID FETCH] MFAPI series {ticker} is too short. Splicing with {yahoo_ticker} via yfinance...")
                yf_series = _fetch_yahoo_series(yahoo_ticker, period_days)
                
                # BSE Fallback if Yahoo NSE fails
                _BSE_FALLBACK_MAP = {
                    "^CNXSC": "BSE-SMLCAP.BO",
                    "NIFTYMIDCAP150.NS": "BSE-MIDCAP.BO",
                    "^CRSLDX": "BSE-500.BO",
                    "^NSEI": "BSESN"
                }
                if (yf_series.empty or len(yf_series) < 10) and yahoo_ticker in _BSE_FALLBACK_MAP:
                    bse_ticker = _BSE_FALLBACK_MAP[yahoo_ticker]  # pragma: no cover — defensive / hard to exercise in unit tests
                    yf_series = _fetch_yahoo_series(bse_ticker, period_days)  # pragma: no cover — defensive / hard to exercise in unit tests
                
                # Fallback to empty series if both Yahoo NSE and BSE fail
                if yf_series.empty or len(yf_series) < 10:
                    return pd.Series(dtype=float)  # pragma: no cover — defensive / hard to exercise in unit tests
                
                series = _splice_benchmark_series(series, yf_series)
        return series

    # ── 3. Yahoo Finance ──────────────────────────────────────────────────
    series = _fetch_yahoo_series(ticker, period_days)
    
    _BSE_FALLBACK_MAP = {
        "^CNXSC": "BSE-SMLCAP.BO",
        "NIFTYMIDCAP150.NS": "BSE-MIDCAP.BO",
        "^CRSLDX": "BSE-500.BO",
        "^NSEI": "BSESN" # Sensex as fallback for Nifty 50
    }
    
    # ── 3.5 Fallback to BSE Index on Yahoo if NSE fails ──────────────────
    if (series.empty or len(series) < 10) and ticker in _BSE_FALLBACK_MAP:
        bse_ticker = _BSE_FALLBACK_MAP[ticker]
        logger.info(f"[BENCH FETCH] Yahoo failed for {ticker}, falling back to BSE equivalent {bse_ticker} via Yahoo...")
        series = _fetch_yahoo_series(bse_ticker, period_days)
    
    # ── 4. User Warning if Yahoo completely fails ──────────────────────────
    if series.empty or len(series) < 10:
        return pd.Series(dtype=float)
        
    return series


def _fetch_yahoo_series(ticker: str, period_days: int) -> pd.Series:
    """Fetch index/ETF history from Yahoo Finance."""
    try:
        import yfinance as yf  # lazy: see note at top of module

        end   = datetime.now()
        # Request extra buffer for weekends/holidays
        start = end - timedelta(days=period_days + 60) if period_days < 9999 else datetime(2000, 1, 1)

        df = yf.download(
            ticker,
            start    = start,
            end      = end,
            progress = False,
            auto_adjust = True,
            threads  = False,
        )

        if df.empty or len(df) < 5:
            return pd.Series(dtype=float)

        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        series = close.dropna().sort_index()

        # Trim to requested period
        if period_days < 9999:
            cutoff = series.index[-1] - timedelta(days=period_days)
            series = series[series.index >= cutoff]

        return pd.Series(series, dtype=float)

    except Exception as e:
        # FIX #11: Return empty, NOT a synthetic growth curve
        logger.error(f"[BENCH FETCH ERROR] ticker={ticker}: {e}")
        return pd.Series(dtype=float)


def _fetch_mf_nav_series(scheme_code: str, period_days: int) -> pd.Series:
    """Fetch NAV series from mfapi.in for use as a benchmark (e.g. liquid fund proxy)."""
    try:
        provider = get_provider()
        return provider.fetch_nav_series(scheme_code, period_days)
    except Exception as e:
        logger.error(f"[MF NAV BENCH ERROR] code={scheme_code}: {e}")
        return pd.Series(dtype=float)


def _build_hybrid_benchmark(period_days: int) -> pd.Series:
    """
    Build a synthetic 50/50 Equity+Debt benchmark.

    FIX #13: Uses Nifty 50 (^NSEI) for equity component and
    ICICI Prudential Liquid ETF (LIQUIDCASE.NS) as the debt proxy
    instead of LIC G-Sec ETF (which is a long-duration product
    inappropriate for a moderate hybrid benchmark).

    Both components are normalised to 100 at start, then blended 50/50.
    """
    # Fetch equity: Nifty 50
    equity = _fetch_yahoo_series("^NSEI", period_days)

    # FIX #13: Short-duration debt proxy (liquid ETF) — more appropriate for hybrid
    # Primary: LIQUIDCASE.NS (ICICI Pru Liquid ETF on NSE)
    # Fallback: LICNETFGSC.NS (LIC Gilt ETF — only if liquid fails)
    debt = _fetch_yahoo_series("LIQUIDCASE.NS", period_days)
    if debt.empty:
        debt = _fetch_yahoo_series("LICNETFGSC.NS", period_days)

    if equity.empty and debt.empty:
        return pd.Series(dtype=float)

    if equity.empty:
        return debt
    if debt.empty:
        return equity

    # Align on common dates
    combined = pd.DataFrame({"equity": equity, "debt": debt}).dropna()
    if combined.empty:
        return pd.Series(dtype=float)

    # Normalise both to 100 at start date, then blend
    e_norm = combined["equity"] / combined["equity"].iloc[0] * 100
    d_norm = combined["debt"]   / combined["debt"].iloc[0]   * 100
    synth  = (e_norm * 0.50) + (d_norm * 0.50)

    return synth.rename("HYBRID_50_50")


# ---------------------------------------------------------------------------
# Utility: Compute benchmark trailing returns (reuse finance.py logic inline)
# ---------------------------------------------------------------------------

def get_benchmark_trailing_returns(ticker: str) -> Dict[str, Optional[float]]:
    """
    Fetch benchmark and compute trailing returns for all standard periods.
    Standardized: Reuses the same compute_trailing_returns logic used for funds.
    """
    # Was `from domains.mutual_funds.finance import compute_trailing_returns` - a
    # shared -> domain import that made Equity's performance tab run Mutual Funds code.
    # The function now lives in shared/services/returns.py; MF re-exports it, so funds
    # and benchmarks are still measured by one implementation.
    from shared.services.returns import compute_trailing_returns

    # Fetch 5Y history (1825 days + buffer)
    series = fetch_benchmark_series(ticker, period_days=1825 + 90)
    if series.empty:
        return {p: None for p in ["1M", "3M", "6M", "1Y", "3Y", "5Y"]}

    return compute_trailing_returns(series)
