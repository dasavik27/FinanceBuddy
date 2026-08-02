"""
domains/equity/quotes.py

Live quotes for listed Indian equities, cached and batched.

Why this module exists
---------------------
domains/equity/models.py used to call `yfinance.download()` directly, once per
`update_live_prices()`, with no caching at any tier. That is one HTTP request per
holding, repeated on every session create, every LRU rehydration and every /sync -
and because `get_session()` has no single-flight, a cold dashboard load with six tabs
fetching concurrently multiplied it by six. The mutual-fund side resolves N holdings'
NAVs from a single shared cached bundle in 0-2 requests regardless of N; this brings
equity to the same shape.

It also isolates the vendor. `yfinance` is imported here and nowhere in
domains/equity, so the provider can be swapped without touching the domain, and tests
can substitute a fake by monkeypatching `_download_closes`.

Cache design
------------
Entries are per-symbol, not per-portfolio: a price is user-independent, so two users
holding RELIANCE share one entry, and a portfolio that overlaps a warm one only pays
for its unique symbols. Misses are then fetched in *batches*, so the per-symbol cache
granularity does not cost per-symbol requests.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from shared.cache import MarketCache
from shared.services.cache import MARKET_CACHE, ttl_for

logger = logging.getLogger(__name__)

# NSE trading symbols are upper-case alphanumerics plus a few punctuation marks
# (M&M, BAJAJ-AUTO, NIFTYBEES). Anything else is not a symbol we will send upstream -
# it is either a parse artifact or someone probing what the ticker lands in.
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-.]{0,19}$")

# How many tickers go into one upstream request. yfinance fans out internally, so this
# bounds the thread burst per call as well as the URL size.
_BATCH_SIZE = 50

# Hard ceiling on distinct symbols resolved in one call. Uploads are row-capped at the
# parser, so reaching this means something unusual; we log rather than silently serve a
# partial portfolio as if it were complete.
_MAX_SYMBOLS = 500


@dataclass(frozen=True)
class Quote:
    """A resolved quote. `prev_close` is the prior session's close, when available."""

    ltp: float
    prev_close: float | None = None

    @property
    def day_change_per_share(self) -> float:
        """Per-share rupee move since the previous close. 0.0 when unknown."""
        if self.prev_close is None:
            return 0.0
        return self.ltp - self.prev_close


def to_yahoo_ticker(symbol: str) -> str:
    """NSE trading symbol -> Yahoo ticker. Already-suffixed symbols pass through."""
    s = str(symbol).upper().strip()
    if s.endswith("-EQ"):
        s = s[:-3]
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def is_valid_symbol(symbol: str) -> bool:
    """Whether a symbol is well-formed enough to send upstream."""
    s = str(symbol).upper().strip()
    if s.endswith("-EQ"):
        s = s[:-3]
    return bool(_SYMBOL_RE.match(s))


def _cache_key(symbol: str) -> str:
    return f"equity_quote_v1:{symbol}"


# ---------------------------------------------------------------------------
# Upstream
# ---------------------------------------------------------------------------

def _close_frame(data, tickers: Sequence[str]):
    """
    Pull a ticker-keyed frame of daily closes out of whatever shape yfinance returned.

    This is the function whose absence caused the original bug. The old code wrote

        close_col = data.get((ticker, "Close")) or data.get(ticker, {}).get("Close")

    and `Series or ...` evaluates `bool(Series)`, which raises "The truth value of a
    Series is ambiguous" for every multi-ticker portfolio. The exception was caught by
    a blanket `except Exception` and logged at DEBUG, so `update_live_prices()` paid
    for N HTTP requests and then updated nothing - silently, in production.

    yfinance's column layout depends on ticker count and on `group_by`, so rather than
    assume one, find the level that actually holds "Close".
    """
    import pandas as pd

    if data is None or len(data) == 0:
        return pd.DataFrame()

    cols = data.columns
    if not isinstance(cols, pd.MultiIndex):
        # Single ticker, flat columns: Open/High/Low/Close/...
        if "Close" not in cols:
            return pd.DataFrame()
        out = data[["Close"]].copy()
        out.columns = [tickers[0]]
        return out

    # Find which level carries the OHLCV field names.
    field_level = None
    for level in range(cols.nlevels):
        if "Close" in cols.get_level_values(level):
            field_level = level
            break
    if field_level is None:
        return pd.DataFrame()

    closes = data.xs("Close", axis=1, level=field_level)
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    return closes


def _download_closes(tickers: Sequence[str]):
    """
    Download recent daily closes for a batch of tickers.

    Separated out as the single seam a test can monkeypatch, so nothing in the test
    suite reaches the network.
    """
    import yfinance as yf

    # 7 calendar days to guarantee at least two trading sessions across weekends and
    # market holidays - `period="2d"` returns one row on a Monday, which leaves no
    # previous close to compute the day's move from.
    data = yf.download(
        tickers,
        period="7d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=min(8, len(tickers)),
        group_by="column",
    )
    return _close_frame(data, tickers)


def _fetch_batch(symbols: Sequence[str]) -> dict[str, Quote]:
    """Resolve one batch of symbols upstream. Never raises."""
    tickers = [to_yahoo_ticker(s) for s in symbols]
    ticker_to_symbol = dict(zip(tickers, symbols))

    try:
        closes = _download_closes(tickers)
    except Exception as e:
        logger.warning("[equity.quotes] download failed for %d symbol(s): %s", len(symbols), e)
        return {}

    if closes is None or closes.empty:
        logger.info("[equity.quotes] upstream returned no rows for %d symbol(s)", len(symbols))
        return {}

    out: dict[str, Quote] = {}
    for ticker in closes.columns:
        symbol = ticker_to_symbol.get(str(ticker))
        if symbol is None:
            continue
        series = closes[ticker].dropna()
        if series.empty:
            continue
        ltp = float(series.iloc[-1])
        prev = float(series.iloc[-2]) if len(series) >= 2 else None
        out[symbol] = Quote(ltp=ltp, prev_close=prev)

    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_quotes(symbols: Iterable[str]) -> dict[str, Quote]:
    """
    Resolve live quotes for `symbols`, serving what is cached and batching the rest.

    Returns a symbol -> Quote mapping that may be *smaller* than the input: a symbol
    the provider does not know is simply absent, and callers keep their existing value
    rather than being handed a zero. Never raises - a quote refresh is an enrichment,
    and a provider outage must not fail the request that triggered it.
    """
    # Normalise, drop malformed, dedupe, preserve order.
    seen: set[str] = set()
    clean: list[str] = []
    rejected = 0
    for raw in symbols:
        s = str(raw).upper().strip()
        if s.endswith("-EQ"):
            s = s[:-3]
        if not s or s in seen:
            continue
        if not is_valid_symbol(s):
            rejected += 1
            continue
        seen.add(s)
        clean.append(s)

    if rejected:
        logger.info("[equity.quotes] skipped %d malformed symbol(s)", rejected)

    if len(clean) > _MAX_SYMBOLS:
        logger.warning(
            "[equity.quotes] %d symbols requested, resolving the first %d; "
            "the rest keep their stored prices",
            len(clean), _MAX_SYMBOLS,
        )
        clean = clean[:_MAX_SYMBOLS]

    if not clean:
        return {}

    # CACHE_TTL_MINUTES <= 0 is the operator kill-switch: it disables market-data
    # caching process-wide and is settable at runtime via POST /market/config. Every
    # mutual-fund provider path honours it (market_data.py:182, market_indices.py:164),
    # so equity has to as well - otherwise "turn caching off and re-check the numbers"
    # silently keeps serving stock prices from L1.
    from shared import config
    caching_enabled = config.CACHE_TTL_MINUTES > 0

    ttl = ttl_for("equity_quote")
    resolved: dict[str, Quote] = {}
    missing: list[str] = []

    if not caching_enabled:
        missing = list(clean)
    else:
        for symbol in clean:
            found, value = MARKET_CACHE.get(_cache_key(symbol))
            if found and isinstance(value, Quote):
                resolved[symbol] = value
            else:
                missing.append(symbol)

    if not missing:
        logger.debug("[equity.quotes] %d symbol(s) served entirely from cache", len(clean))
        return resolved

    for start in range(0, len(missing), _BATCH_SIZE):
        batch = missing[start:start + _BATCH_SIZE]
        fetched = _fetch_batch(batch)
        for symbol, quote in fetched.items():
            if caching_enabled:
                # copy_on_read=False: Quote is frozen, so handing out the same instance
                # is safe and avoids a copy per holding per request.
                MARKET_CACHE.set(_cache_key(symbol), quote, ttl, copy_on_read=False)
            resolved[symbol] = quote

    logger.info(
        "[equity.quotes] resolved %d/%d symbol(s) (%d from cache, %d fetched in %d batch(es))",
        len(resolved), len(clean), len(clean) - len(missing), len(missing),
        (len(missing) + _BATCH_SIZE - 1) // _BATCH_SIZE,
    )
    return resolved


# ---------------------------------------------------------------------------
# Daily close history, for the performance chart
# ---------------------------------------------------------------------------

def _history_key(symbol: str, days: int) -> str:
    return f"equity_hist_v1:{symbol}:{days}"


# ---------------------------------------------------------------------------
# L2: close history on disk
# ---------------------------------------------------------------------------
#
# Why history and not quotes.
#
# MarketCache is a JSON-on-disk tier whose purpose is cold starts: a free-tier instance
# that just woke has an empty L1 but may still hold something usable on disk, and
# re-downloading it is pure latency. Worth it for a 4-hour close series - 250 to 1250
# points per symbol, and the expensive half of the performance chart.
#
# Deliberately NOT applied to live quotes. Their L1 TTL is 5 minutes, while MarketCache
# expires against the global CACHE_TTL_MINUTES (60 by default), so a disk hit would
# happily serve an hour-old last-traded price. The cases where a 5-minute-fresh quote
# survives a process restart are rare enough that the benefit does not justify a tier
# that can hand back a stale price - so quotes stay L1-only, on purpose.

def _series_to_json(series) -> dict:
    """A pandas Series of closes -> JSON-safe dict. MarketCache stores JSON only."""
    return {
        "index": [str(ts.date()) if hasattr(ts, "date") else str(ts) for ts in series.index],
        "values": [float(v) for v in series.values],
    }


def _series_from_json(blob) -> Any:
    """Inverse of _series_to_json. Returns None on anything unexpected."""
    import pandas as pd

    if not isinstance(blob, dict):
        return None
    idx, vals = blob.get("index"), blob.get("values")
    if not isinstance(idx, list) or not isinstance(vals, list) or len(idx) != len(vals):
        return None
    if not idx:
        return None
    try:
        return pd.Series(vals, index=pd.to_datetime(idx), dtype="float64")
    except Exception:
        return None


def _download_history(tickers: Sequence[str], days: int):
    """Download `days` of daily closes for a batch. The seam tests monkeypatch."""
    import yfinance as yf

    data = yf.download(
        tickers,
        period=f"{days}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=min(8, len(tickers)),
        group_by="column",
    )
    return _close_frame(data, tickers)


def fetch_close_history(symbols: Iterable[str], days: int):
    """
    Daily close history for `symbols`, as a DataFrame indexed by date with one column
    per symbol. Cached per symbol, so a portfolio that overlaps a warm one only pays
    for its unique names.

    Returns an empty DataFrame if nothing could be resolved. Never raises.
    """
    import pandas as pd

    seen: set[str] = set()
    clean: list[str] = []
    for raw in symbols:
        s = str(raw).upper().strip()
        if s.endswith("-EQ"):
            s = s[:-3]
        if not s or s in seen or not is_valid_symbol(s):
            continue
        seen.add(s)
        clean.append(s)

    if len(clean) > _MAX_SYMBOLS:
        logger.warning(
            "[equity.quotes] history requested for %d symbols; charting the first %d",
            len(clean), _MAX_SYMBOLS,
        )
        clean = clean[:_MAX_SYMBOLS]

    if not clean:
        return pd.DataFrame()

    days = max(1, int(days))
    ttl = ttl_for("benchmark_data")  # settled series, refreshed a few times a day

    from shared import config
    caching_enabled = config.CACHE_TTL_MINUTES > 0

    series_by_symbol: dict[str, Any] = {}
    missing: list[str] = []
    if not caching_enabled:
        missing = list(clean)
    else:
        # L1 first, then L2 on disk before reaching for the network.
        disk_hits = 0
        for symbol in clean:
            key = _history_key(symbol, days)
            found, value = MARKET_CACHE.get(key)
            if found and value is not None:
                series_by_symbol[symbol] = value
                continue

            restored = _series_from_json(MarketCache.get(key))
            if restored is not None:
                # Promote into L1 so the rest of this request and the next one do not
                # re-read and re-parse the file.
                MARKET_CACHE.set(key, restored, ttl)
                series_by_symbol[symbol] = restored
                disk_hits += 1
                continue

            missing.append(symbol)

        if disk_hits:
            logger.info("[equity.quotes] %d history series restored from disk", disk_hits)

    for start in range(0, len(missing), _BATCH_SIZE):
        batch = missing[start:start + _BATCH_SIZE]
        tickers = [to_yahoo_ticker(s) for s in batch]
        ticker_to_symbol = dict(zip(tickers, batch))
        try:
            closes = _download_history(tickers, days)
        except Exception as e:
            logger.warning("[equity.quotes] history download failed: %s", e)
            continue
        if closes is None or closes.empty:
            continue
        for ticker in closes.columns:
            symbol = ticker_to_symbol.get(str(ticker))
            if symbol is None:
                continue
            series = closes[ticker].dropna()
            if series.empty:
                continue
            if caching_enabled:
                key = _history_key(symbol, days)
                MARKET_CACHE.set(key, series, ttl)
                # L2 too, so a restart does not re-download it. MarketCache no-ops when
                # caching is disabled and bounds its own directory via _maybe_sweep.
                try:
                    MarketCache.set(key, _series_to_json(series))
                except Exception as e:
                    logger.debug("[equity.quotes] disk persist skipped for %s: %s", symbol, e)
            series_by_symbol[symbol] = series

    if not series_by_symbol:
        return pd.DataFrame()

    # One concat rather than a per-cell lookup. The caller then does column arithmetic.
    frame = pd.concat(series_by_symbol, axis=1)
    frame.columns = list(series_by_symbol.keys())
    return frame.sort_index()
