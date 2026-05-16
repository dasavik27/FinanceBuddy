"""
services/market_indices.py
Live index tracking and benchmark series fetching.

Key fixes vs v1.0:
- FIX #11: Removed fake synthetic benchmark on fetch failure (was growing at ~17.4%/yr)
- FIX #13: Hybrid 50/50 uses a more appropriate short-duration debt proxy
- Added: per-ticker in-memory cache to avoid redundant Yahoo Finance calls
- Added: proper error propagation (empty Series on failure, not fake data)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

# ── Thread-safe Cache Lock ──────────────────────────────────────────────
_BENCH_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
_BENCH_CACHE: Dict[str, Tuple[float, pd.Series]] = {}   # ticker → (timestamp, series)
_BENCH_CACHE_TTL = 3600   # 1 hour for index data

def clear_benchmark_cache():
    """Invalidate all in-memory benchmark series."""
    with _BENCH_LOCK:
        _BENCH_CACHE.clear()


# ---------------------------------------------------------------------------
# Live Market Summary
# ---------------------------------------------------------------------------

def fetch_live_market_summary() -> Dict:
    """
    Fetch live Nifty 50 price and 1D change from Yahoo Finance.
    Returns a safe fallback dict on any failure — never raises.
    """
    try:
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
    except Exception as e:
        print(f"[MARKET ERROR] Nifty live fetch failed: {e}")

    # Return stale/fallback data — explicitly flagged as not live
    return {
        "nifty": {
            "price":      0.0,
            "change":     0.0,
            "change_pct": 0.0,
            "is_live":    False,
        }
    }


# ---------------------------------------------------------------------------
# Benchmark Series Fetching
# FIX #11: Returns empty Series on failure — no fake growth data
# FIX #13: Hybrid 50/50 uses improved debt proxy
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
    # ── Cache check ───────────────────────────────────────────────────────
    from core import config
    if config.CACHE_TTL_MINUTES <= 0 or refresh:
        return _fetch_benchmark_series_uncached(ticker, period_days)

    cache_key = f"{ticker}_{period_days}"
    now       = time.time()
    ttl_sec   = config.CACHE_TTL_MINUTES * 60
    with _BENCH_LOCK:
        if cache_key in _BENCH_CACHE:
            ts, series = _BENCH_CACHE[cache_key]
            if now - ts < ttl_sec:
                return series.copy() # Fix #9: Prevent cache reference leaks

    series = _fetch_benchmark_series_uncached(ticker, period_days)

    if not series.empty:
        with _BENCH_LOCK:
            _BENCH_CACHE[cache_key] = (now, series.copy()) # Fix #9: Store deep copy

    return series


_NSELIB_MAP = {
    "^CNXSC": "NIFTY SMALLCAP 250",
    "NIFTYMIDCAP150.NS": "NIFTY MIDCAP 150",
    "^CRSLDX": "NIFTY 500",
    "^NSEI": "NIFTY 50"
}

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

def _fetch_nselib_series(index_name: str, period_days: int) -> pd.Series:
    """Fetch index history from nselib in chunks (NSE API limits queries to 1 year)."""
    try:
        from nselib import capital_market
    except ImportError:
        print("[NSELIB] nselib package not installed.")
        return pd.Series(dtype=float)

    import time
    end = datetime.now()
    dfs = []
    
    # Calculate how many 365-day chunks we need (Cap at 6 years to ensure 5Y math clears weekends)
    chunks = min((period_days // 365) + 1, 6)
        
    for _ in range(chunks):
        start = end - timedelta(days=365)
        from_str = start.strftime("%d-%m-%Y")
        to_str = end.strftime("%d-%m-%Y")
        
        try:
            df = capital_market.index_data(index=index_name, from_date=from_str, to_date=to_str)
            if isinstance(df, pd.DataFrame) and not df.empty and 'CLOSE_INDEX_VAL' in df.columns:
                dfs.append(df[['TIMESTAMP', 'CLOSE_INDEX_VAL']])
        except Exception as e:
            # Fix #10: Log chunk failures instead of swallowing silently
            print(f"[NSELIB CHUNK ERROR] {index_name} ({from_str} to {to_str}): {e}")
            
        end = start - timedelta(days=1)
        time.sleep(0.5) # respect NSE rate limits
        
    if dfs:
        try:
            full = pd.concat(dfs, ignore_index=True)
            full['TIMESTAMP'] = pd.to_datetime(full['TIMESTAMP'], format='%d-%b-%Y')
            full = full.sort_values('TIMESTAMP').set_index('TIMESTAMP')
            series = pd.to_numeric(full['CLOSE_INDEX_VAL'], errors='coerce').dropna()
            return series
        except Exception as e:
            print(f"[NSELIB ERROR] Parsing failed: {e}")
            
    return pd.Series(dtype=float)


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
        from services.market_data import fetch_nav_series_by_isin
        return fetch_nav_series_by_isin(ticker, period_days)

    # ── 3. MF Scheme Code (numeric string, e.g. "122639") ─────────────────
    if str(ticker).strip().isdigit() and len(str(ticker).strip()) >= 5:
        from services.market_data import fetch_nav_series_by_code
        return fetch_nav_series_by_code(ticker, period_days)

    # ── 3. Yahoo Finance ──────────────────────────────────────────────────
    series = _fetch_yahoo_series(ticker, period_days)
    
    # ── 4. Fallback to NSELib if Yahoo fails and we have a mapping ─────────
    if (series.empty or len(series) < 10) and ticker in _NSELIB_MAP:
        print(f"[BENCH FETCH] Yahoo failed for {ticker}, using nselib for {_NSELIB_MAP[ticker]}...")
        series = _fetch_nselib_series(_NSELIB_MAP[ticker], period_days)
        
    return series


def _fetch_yahoo_series(ticker: str, period_days: int) -> pd.Series:
    """Fetch index/ETF history from Yahoo Finance."""
    try:
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
        print(f"[BENCH FETCH ERROR] ticker={ticker}: {e}")
        return pd.Series(dtype=float)


def _fetch_mf_nav_series(scheme_code: str, period_days: int) -> pd.Series:
    """Fetch NAV series from mfapi.in for use as a benchmark (e.g. liquid fund proxy)."""
    try:
        url  = f"https://api.mfapi.in/mf/{scheme_code}"
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        if not data:
            return pd.Series(dtype=float)

        series = pd.Series(
            {pd.to_datetime(rec["date"], dayfirst=True): float(rec["nav"])
             for rec in data}
        ).sort_index()

        if period_days < 9999:
            cutoff = series.index[-1] - timedelta(days=period_days)
            series = series[series.index >= cutoff]

        return series

    except Exception as e:
        print(f"[MF NAV BENCH ERROR] code={scheme_code}: {e}")
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
    from core.finance import compute_trailing_returns
    
    # Fetch 5Y history (1825 days + buffer)
    series = fetch_benchmark_series(ticker, period_days=1825 + 90)
    if series.empty:
        return {p: None for p in ["1M", "3M", "6M", "1Y", "3Y", "5Y"]}

    return compute_trailing_returns(series)
