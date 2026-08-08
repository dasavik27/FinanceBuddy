"""Daily OHLCV fetch + cache for research strategies."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from domains.equity.quotes import is_valid_symbol, to_yahoo_ticker
from shared.cache import MarketCache
from shared.services.cache import MARKET_CACHE, ttl_for

logger = logging.getLogger(__name__)

_OHLC_DAYS = 500
_MIN_BARS = 50


def _cache_key(symbol: str, days: int) -> str:
    return f"equity_ohlcv_v1:{symbol}:{days}"


def _frame_to_json(df: pd.DataFrame) -> dict:
    return {
        "index": [str(ts.date()) if hasattr(ts, "date") else str(ts) for ts in df.index],
        "Open": [float(v) for v in df["Open"].values],
        "High": [float(v) for v in df["High"].values],
        "Low": [float(v) for v in df["Low"].values],
        "Close": [float(v) for v in df["Close"].values],
        "Volume": [float(v) for v in df["Volume"].values],
    }


def _frame_from_json(blob: Any) -> pd.DataFrame | None:
    if not isinstance(blob, dict):
        return None
    idx = blob.get("index")
    try:
        cols = {c: blob[c] for c in ("Open", "High", "Low", "Close", "Volume")}
        if not isinstance(idx, list) or not idx:
            return None
        df = pd.DataFrame(cols, index=pd.to_datetime(idx))
        return df.dropna()
    except Exception:
        return None


def _clean_yf(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    if raw is None or len(raw) < _MIN_BARS:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.copy()
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.loc[:, ~raw.columns.duplicated()]
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in raw.columns]
    if len(cols) < 5:
        return None
    out = raw[list(cols)].dropna()
    out.index = pd.to_datetime(out.index)
    return out if len(out) >= _MIN_BARS else None


def _download_ohlcv(symbol: str, days: int) -> pd.DataFrame | None:
    import yfinance as yf

    yf_sym = to_yahoo_ticker(symbol)
    end = datetime.today()
    start = end - timedelta(days=days + 40)
    try:
        raw = yf.download(
            yf_sym,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        df = _clean_yf(raw)
        if df is None and yf_sym.endswith(".NS"):
            df = _clean_yf(
                yf.download(
                    yf_sym.replace(".NS", ".BO"),
                    start=start,
                    end=end,
                    progress=False,
                    auto_adjust=True,
                    threads=False,
                )
            )
        return df
    except Exception as e:
        logger.debug("[research.ohlc] download failed for %s: %s", symbol, e)
        return None


def fetch_ohlcv(symbol: str, days: int = _OHLC_DAYS) -> pd.DataFrame | None:
    """
    Daily OHLCV for one NSE symbol. Cached in L1 + disk.
    Returns None when the series is too short or unavailable.
    """
    s = str(symbol).upper().strip().replace("-EQ", "")
    if not s or not is_valid_symbol(s):
        return None

    days = max(_MIN_BARS, int(days))
    key = _cache_key(s, days)
    ttl = ttl_for("benchmark_data")

    found, cached = MARKET_CACHE.get(key)
    if found and isinstance(cached, pd.DataFrame) and len(cached) >= _MIN_BARS:
        return cached

    restored = _frame_from_json(MarketCache.get(key))
    if restored is not None and len(restored) >= _MIN_BARS:
        MARKET_CACHE.set(key, restored, ttl)
        return restored

    df = _download_ohlcv(s, days)
    if df is None:
        return None

    MARKET_CACHE.set(key, df, ttl)
    try:
        MarketCache.set(key, _frame_to_json(df))
    except Exception as e:
        logger.debug("[research.ohlc] disk persist skipped for %s: %s", s, e)
    return df
