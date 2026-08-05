"""
domains/equity/stock_analyzer.py

Stock research and portfolio impact analysis engine.

Fetches fundamental data from Yahoo Finance (yfinance) and computes
how adding a new position would shift an existing equity portfolio's
sector allocation, beta, and diversification score.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from domains.equity import nse_corporate, nse_results
from domains.equity.bse_client import bse_client
from domains.equity.sector_map import SECTOR_MAP, get_sector
from shared.cache import MarketCache as DiskCache
from shared.services import market_hours, refresh
from shared.services.cache import MARKET_CACHE, ttl_for
from shared.services.refresh import WARM
from domains.equity.quotes import fetch_quotes, is_valid_symbol, to_yahoo_ticker

logger = logging.getLogger(__name__)


class UnknownSymbol(ValueError):
    """Raised when a symbol is not well-formed enough to look up."""


#: Deadline for every outbound yfinance call. The sync-handler threadpool is capped at
#: 8 (main.py), so a single untimed download can hold an eighth of the server's request
#: capacity for as long as the far end keeps the socket open - and no yfinance call in
#: this codebase previously passed a timeout at all.
_YF_TIMEOUT = 20

#: Maximum points shipped per chart timeframe. A line chart is drawn a few hundred
#: pixels wide, so beyond this the extra points cost bytes and cache budget without
#: being visible.
_MAX_CHART_POINTS = 260


# ── NSE → Yahoo Finance ticker conversion ────────────────────────────────────

def _to_yf_ticker(symbol: str) -> str:
    return to_yahoo_ticker(symbol)


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("-EQ", "").replace(".NS", "").replace(".BO", "")


def _company_name(symbol: str) -> str:
    """Company name from NSE's master list, falling back to the symbol itself."""
    try:
        return nse_client.name_for(symbol) or symbol
    except Exception:
        return symbol


# ── Search ───────────────────────────────────────────────────────────────────

# A small curated index of popular NSE stocks for fast search
_SEARCH_INDEX: list[dict] = [
    {"symbol": "RELIANCE", "name": "Reliance Industries Ltd"},
    {"symbol": "TCS", "name": "Tata Consultancy Services Ltd"},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Ltd"},
    {"symbol": "INFY", "name": "Infosys Ltd"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Ltd"},
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Ltd"},
    {"symbol": "ITC", "name": "ITC Ltd"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Ltd"},
    {"symbol": "LT", "name": "Larsen & Toubro Ltd"},
    {"symbol": "SBIN", "name": "State Bank of India"},
    {"symbol": "AXISBANK", "name": "Axis Bank Ltd"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd"},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Ltd"},
    {"symbol": "WIPRO", "name": "Wipro Ltd"},
    {"symbol": "HCLTECH", "name": "HCL Technologies Ltd"},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Ltd"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd"},
    {"symbol": "TATAMOTORS", "name": "Tata Motors Ltd"},
    {"symbol": "TATASTEEL", "name": "Tata Steel Ltd"},
    {"symbol": "NTPC", "name": "NTPC Ltd"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Ltd"},
    {"symbol": "ONGC", "name": "Oil and Natural Gas Corporation Ltd"},
    {"symbol": "NESTLEIND", "name": "Nestle India Ltd"},
    {"symbol": "TITAN", "name": "Titan Company Ltd"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Ltd"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Ltd"},
    {"symbol": "ADANIPORTS", "name": "Adani Ports and Special Economic Zone Ltd"},
    {"symbol": "COALINDIA", "name": "Coal India Ltd"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel Ltd"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd"},
    {"symbol": "ASIANPAINT", "name": "Asian Paints Ltd"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Ltd"},
    {"symbol": "CIPLA", "name": "Cipla Ltd"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories Ltd"},
    {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance Company Ltd"},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance Company Ltd"},
    {"symbol": "EICHERMOT", "name": "Eicher Motors Ltd"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries Ltd"},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Ltd"},
    {"symbol": "GRASIM", "name": "Grasim Industries Ltd"},
    {"symbol": "TECHM", "name": "Tech Mahindra Ltd"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank Ltd"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries Ltd"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Ltd"},
    {"symbol": "ZOMATO", "name": "Zomato Ltd"},
    {"symbol": "TRENT", "name": "Trent Ltd"},
    {"symbol": "DMART", "name": "Avenue Supermarts Ltd (DMart)"},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Ltd"},
    {"symbol": "HAL", "name": "Hindustan Aeronautics Ltd"},
    {"symbol": "BEL", "name": "Bharat Electronics Ltd"},
    {"symbol": "LTIM", "name": "LTIMindtree Ltd"},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries Ltd"},
    {"symbol": "SIEMENS", "name": "Siemens India Ltd"},
    {"symbol": "ABB", "name": "ABB India Ltd"},
    {"symbol": "TATAPOWER", "name": "Tata Power Company Ltd"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems Ltd"},
    {"symbol": "MPHASIS", "name": "Mphasis Ltd"},
    {"symbol": "COFORGE", "name": "Coforge Ltd"},
    {"symbol": "NYKAA", "name": "FSN E-Commerce Ventures Ltd (Nykaa)"},
    {"symbol": "ANGELONE", "name": "Angel One Ltd"},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Ltd"},
]


from domains.equity.nse_client import nse_client


def search_stocks(query: str, limit: int = 15) -> list[dict]:
    """
    Search across the complete master list of ~2,200+ NSE equity stocks.
    Returns list of {symbol, name, sector, industry, ticker}.
    """
    return nse_client.search(query, limit=limit)


# ── Stock Analysis ───────────────────────────────────────────────────────────

#: How long a *stale* analysis is still worth serving while a fresh one is fetched.
#: Far longer than the freshness window: past its soft deadline the payload is out of
#: date, but it is still enormously better than making someone wait ~30s for a cold
#: rebuild, and better than the zeros the old path returned when upstream was down.
_ANALYSIS_STALE_TTL = 24 * 3600

_ANALYSIS_KEY = "equity_analysis_v2:{}"


def analyze_stock(symbol: str) -> dict[str, Any]:
    """
    Fundamental + technical data for one NSE stock.

    Stale-while-revalidate. The cache holds an envelope with its own soft deadline and
    a much longer hard TTL, so a request past the freshness window is answered from the
    existing copy *immediately* and the rebuild happens on the janitor thread instead of
    inside someone's request. A cold rebuild was measured at 48.7s against a threadpool
    of 8, and the previous code did that work inline on every expiry.

    Entries are user-independent - a stock's fundamentals are the same for everyone - so
    one fetch serves every caller.
    """
    clean = _clean_symbol(symbol)
    if not is_valid_symbol(clean):
        # Rejected here rather than concatenated into an upstream URL. The symbol was
        # only upper-cased and stripped before, so a value containing path separators
        # or query characters was interpolated straight into the provider request.
        raise UnknownSymbol(f"{symbol!r} is not a valid NSE symbol.")

    # Someone is looking at this name, so it earns a place in the refresh rotation.
    WARM.touch(clean)

    # Honours the process-wide cache kill-switch, same as every mutual-fund provider
    # path does. Without this, POST /market/config with ttl=0 would still serve
    # fundamentals from L1.
    from shared import config
    if config.CACHE_TTL_MINUTES <= 0:
        return _analyze_stock_uncached(clean)

    key = _ANALYSIS_KEY.format(clean)

    found, envelope = MARKET_CACHE.get(key)
    if not found:
        # L1 is per-process and dies with it, so every restart - and `--reload` fires
        # one on each edit - meant the next request paid a ~30s rebuild. The disk tier
        # is already bounded (64 MB budget, LRU-evicted by the janitor sweep), so
        # reusing it costs no new store and no new size discipline to get wrong.
        envelope = DiskCache.get(key)
        if isinstance(envelope, dict) and "data" in envelope:
            # Re-seed L1 so the next read in this process does not touch disk again.
            MARKET_CACHE.set(key, envelope, _ANALYSIS_STALE_TTL, copy_on_read=False)

    if isinstance(envelope, dict) and "data" in envelope:
        if time.time() < envelope.get("fresh_until", 0):
            return envelope["data"]
        # Past the soft deadline: hand back what we have and let the sweep replace it.
        # The `stale` flag is what lets the UI say "as of" honestly instead of
        # presenting an hours-old price as current.
        return {**envelope["data"], "stale": True}

    return _refresh_analysis(clean)


def _refresh_analysis(symbol: str) -> dict[str, Any]:
    """
    Rebuild one symbol's analysis and replace its cache envelope.

    Also the tier refresher, so the background sweep and a cold request go through
    exactly one code path.
    """
    clean = _clean_symbol(symbol)
    key = _ANALYSIS_KEY.format(clean)
    data = _analyze_stock_uncached(clean)
    
    # Smart negative cache: shorter TTL for degraded responses
    is_degraded = (
        data.get("pe_ratio") is None
        and data.get("market_cap_cr") is None
        and data.get("eps") is None
    )
    cache_ttl = 30 if is_degraded else market_hours.fundamentals_ttl()
    
    if is_degraded:
        logger.warning(
            "[analyzer] %s returned degraded data (no P/E, market cap, or EPS); "
            "caching for 30s only", clean
        )
    
    envelope = {
        "data": data,
        "fresh_until": time.time() + cache_ttl,
    }
    MARKET_CACHE.set(
        key, envelope, _ANALYSIS_STALE_TTL,
        # The payload is serialised to JSON and discarded; nothing mutates it. Deep
        # copying ~45 KB on every read would cost more than it protects.
        copy_on_read=False,
    )
    # Write through to disk so the work survives a restart. Failures here are logged
    # and swallowed inside DiskCache - a full or read-only disk must not fail a request
    # whose data we already have in hand.
    DiskCache.set(key, envelope)
    return data


import numpy as np


def _fetch_yf_info(ticker_ns: str) -> tuple[dict, str]:
    """
    Try .NS first; if info is empty or missing, fall back to .BO.
    
    Returns (info_dict, ticker_used). This fixes blank tiles for stocks like
    TATAMOTORS, LTIM, ZOMATO where .NS returns HTTP 404 but .BO succeeds.
    
    Why this works: TATAMOTORS.BO, LTIM.BO, ZOMATO.BO all return 150+ key payloads
    with P/E, EPS, Market Cap, Beta, Dividend Yield fields.
    """
    import yfinance as yf
    
    for suffix in (".NS", ".BO"):
        sym = ticker_ns.replace(".NS", suffix).replace(".BO", suffix)
        try:
            ticker_obj = yf.Ticker(sym)
            info = ticker_obj.info or {}
            # Real payload check: an error stub or empty response has < 10 keys
            if len(info) > 10:
                logger.debug("[analyzer] %s resolved with %d info keys", sym, len(info))
                return info, sym
        except Exception as e:
            logger.debug("[analyzer] %s fetch failed: %s", sym, e)
            continue
    
    logger.warning("[analyzer] both .NS and .BO failed for %s", ticker_ns)
    return {}, ticker_ns


def _compute_beta(stock_hist: pd.DataFrame, symbol: str) -> float | None:
    """
    Compute 250-day beta of stock vs Nifty 50 from daily log returns.
    
    Primary source for Beta — Yahoo's beta is the fallback when < 60 trading
    days of data exist for the stock.
    
    Formula: Beta = Covariance(stock_returns, market_returns) / Variance(market_returns)
    """
    nifty_map = _nifty_close_series()
    if not nifty_map or len(nifty_map) < 60:
        logger.debug("[analyzer] insufficient Nifty data for beta calculation")
        return None
    
    if stock_hist.empty or "Close" not in stock_hist.columns:
        return None
    
    # Extract close prices
    close = stock_hist["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    stock_prices = close.dropna()
    
    if len(stock_prices) < 60:
        logger.debug("[analyzer] %s has < 60 days of data, skipping math beta", symbol)
        return None
    
    # Convert Nifty dict to Series aligned with stock dates
    nifty_series = pd.Series(nifty_map, dtype=float)
    nifty_series.index = pd.to_datetime(nifty_series.index)
    
    # Align both series on common dates
    stock_aligned = stock_prices.reindex(nifty_series.index)
    nifty_aligned = nifty_series.reindex(stock_prices.index)
    
    # Compute percentage returns
    stock_returns = stock_aligned.pct_change().dropna()
    nifty_returns = nifty_aligned.pct_change().dropna()
    
    # Align on common dates again after pct_change
    aligned_df = pd.DataFrame({
        "stock": stock_returns,
        "nifty": nifty_returns
    }).dropna()
    
    if len(aligned_df) < 60:
        logger.debug("[analyzer] %s has < 60 aligned days after returns, skipping math beta", symbol)
        return None
    
    # Take last 250 days if available
    aligned_df = aligned_df.iloc[-250:]
    
    # Calculate covariance and variance
    cov_matrix = aligned_df.cov()
    if "stock" not in cov_matrix.columns or "nifty" not in cov_matrix.columns:
        return None
    
    covariance = cov_matrix.loc["stock", "nifty"]
    variance = aligned_df["nifty"].var()
    
    if variance == 0 or pd.isna(variance) or pd.isna(covariance):
        return None
    
    beta = covariance / variance
    result = round(float(beta), 3)
    logger.debug("[analyzer] %s computed beta: %.3f from %d days", symbol, result, len(aligned_df))
    return result


def _nse_dividend_yield(actions: list[dict], current_price: float) -> float | None:
    """
    Sum all cash dividend amounts paid in the trailing 12 months from NSE
    corporate actions. Divide by current price to get yield percentage.
    
    Returns None if no dividends in last 12 months or price is invalid.
    """
    if not actions or not current_price or current_price <= 0:
        return None
    
    from datetime import datetime, timedelta, timezone
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    total_div = 0.0
    
    for action in actions:
        if not isinstance(action, dict):
            continue
        
        # Check if it's a dividend action
        action_type = action.get("type", "").lower()
        if action_type != "dividend":
            # Also check subject for dividend keywords
            subject = action.get("subject", "").upper()
            if "DIVIDEND" not in subject:
                continue
        
        try:
            # Extract dividend amount
            # NSE doesn't always have a separate "amount" field, parse from subject
            subject = action.get("subject", "")
            amount_match = re.search(r'RS?\.?\s*(\d+(?:\.\d+)?)', subject, re.I)
            if amount_match:
                amount = float(amount_match.group(1))
            else:
                # Try face_value or other fields
                amount = float(str(action.get("amount", "0")).replace(",", ""))
            
            if amount <= 0:
                continue
            
            # Check ex-date
            ex_date_str = action.get("ex_date")
            if not ex_date_str:
                continue
            
            ex_date = pd.to_datetime(ex_date_str, errors="coerce")
            if pd.isna(ex_date):
                continue
            
            # Make timezone aware for comparison
            if ex_date.tzinfo is None:
                ex_date = ex_date.tz_localize("UTC")
            
            if ex_date >= cutoff:
                total_div += amount
                logger.debug("[analyzer] dividend: Rs %.2f on %s", amount, ex_date_str)
                
        except Exception as e:
            logger.debug("[analyzer] failed to parse dividend action: %s", e)
            continue
    
    if total_div > 0:
        yield_pct = (total_div / current_price) * 100
        result = round(yield_pct, 2)
        logger.debug("[analyzer] NSE dividend yield: %.2f%% (Rs %.2f / Rs %.2f)", 
                    result, total_div, current_price)
        return result
    
    return None


def _compute_rsi(prices_series: pd.Series, period: int = 14) -> float | None:
    """Compute standard 14-period Relative Strength Index (RSI)."""
    if len(prices_series) < period + 1:
        return None
    delta = prices_series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    valid = rsi.dropna()
    if valid.empty:
        return None
    val = float(valid.iloc[-1])
    return round(val, 1) if not np.isnan(val) else None


def _compute_technicals(
    prices: pd.Series,
    current_price: float,
    week52_high: float | None,
    week52_low: float | None,
) -> dict[str, Any]:
    """Compute moving averages, trend status, RSI(14), and 52-week proximity."""
    if prices.empty:
        return {
            "sma_50": None,
            "sma_200": None,
            "above_50_dma": None,
            "above_200_dma": None,
            "rsi_14": None,
            "rsi_status": "Neutral",
            "trend": "Neutral",
            "dist_52w_high_pct": None,
            "dist_52w_low_pct": None,
        }

    sma_50 = round(float(prices.iloc[-50:].mean()), 2) if len(prices) >= 50 else None
    sma_200 = round(float(prices.iloc[-200:].mean()), 2) if len(prices) >= 200 else None

    above_50 = (current_price > sma_50) if (sma_50 is not None and current_price > 0) else None
    above_200 = (current_price > sma_200) if (sma_200 is not None and current_price > 0) else None

    rsi_14 = _compute_rsi(prices, 14)
    if rsi_14 is not None:
        if rsi_14 < 30:
            rsi_status = "Oversold"
        elif rsi_14 > 70:
            rsi_status = "Overbought"
        else:
            rsi_status = "Neutral"
    else:
        rsi_status = "Neutral"

    if above_200 is True and above_50 is True:
        trend = "Strong Uptrend"
    elif above_200 is True:
        trend = "Uptrend"
    elif above_200 is False and above_50 is False:
        trend = "Downtrend"
    else:
        trend = "Consolidating"

    dist_high = (
        round(((current_price - week52_high) / week52_high) * 100, 1)
        if (week52_high and current_price and week52_high > 0)
        else None
    )
    dist_low = (
        round(((current_price - week52_low) / week52_low) * 100, 1)
        if (week52_low and current_price and week52_low > 0)
        else None
    )

    return {
        "sma_50": sma_50,
        "sma_200": sma_200,
        "above_50_dma": above_50,
        "above_200_dma": above_200,
        "rsi_14": rsi_14,
        "rsi_status": rsi_status,
        "trend": trend,
        "dist_52w_high_pct": dist_high,
        "dist_52w_low_pct": dist_low,
    }


def get_market_indices() -> list[dict[str, Any]]:
    """
    Fetch live levels for top Indian market indices:
    NIFTY 50, SENSEX, NIFTY BANK, NIFTY IT.
    """
    indices_config = [
        {"symbol": "^NSEI", "name": "NIFTY 50", "display_symbol": "NIFTY 50"},
        {"symbol": "^BSESN", "name": "BSE SENSEX", "display_symbol": "SENSEX"},
        {"symbol": "^NSEBANK", "name": "NIFTY BANK", "display_symbol": "BANK NIFTY"},
        {"symbol": "^CNXIT", "name": "NIFTY IT", "display_symbol": "NIFTY IT"},
    ]

    def _fetch_indices():
        results = []
        try:
            import yfinance as yf
            tickers = [item["symbol"] for item in indices_config]
            data = yf.download(
                tickers, period="5d", interval="1d",
                progress=False, group_by="ticker", timeout=_YF_TIMEOUT,
            )
            
            for item in indices_config:
                sym = item["symbol"]
                try:
                    df = data[sym] if sym in data else pd.DataFrame()
                    if not df.empty and "Close" in df.columns:
                        closes = df["Close"].dropna()
                        if len(closes) >= 2:
                            curr = float(closes.iloc[-1])
                            prev = float(closes.iloc[-2])
                            chg = round(curr - prev, 2)
                            pchg = round((chg / prev) * 100, 2) if prev else 0.0
                            results.append({
                                "symbol": item["display_symbol"],
                                "name": item["name"],
                                "price": round(curr, 2),
                                "change": chg,
                                "p_change": pchg,
                            })
                            continue
                except Exception:
                    pass
                # Fallback item if individual fetch fails
                results.append({
                    "symbol": item["display_symbol"],
                    "name": item["name"],
                    "price": 0.0,
                    "change": 0.0,
                    "p_change": 0.0,
                })
        except Exception as e:
            logger.warning("[analyzer] get_market_indices failed: %s", e)
        return results

    return MARKET_CACHE.get_or_compute(
        "market_indices_v1",
        _fetch_indices,
        ttl_for("live_navs"),
    )


def _peer_symbols(clean: str, sector: str, industry: str, limit: int) -> list[str]:
    """
    Peer candidates derived from SECTOR_MAP itself, nearest-first.

    This used to read a second, hand-maintained SECTOR_PEERS_MAP keyed on NSE's sector
    vocabulary ("Financial Services", "Oil, Gas & Consumable Fuels") while `get_sector`
    returns GICS-style names ("Financials", "Energy"). The two vocabularies intersected
    on exactly two keys, so 157 of 190 mapped symbols missed and fell through to a fixed
    fallback: every one of them was shown RELIANCE/TCS/HDFCBANK/INFY/ICICIBANK as its
    "sector peers". Deriving peers from the same table the sector came from makes that
    class of drift structurally impossible.
    """
    same_industry: list[str] = []
    same_sector: list[str] = []
    for sym, (sec, ind) in SECTOR_MAP.items():
        if sym == clean:
            continue
        if industry and ind == industry:
            same_industry.append(sym)
        elif sector and sec == sector:
            same_sector.append(sym)
    return (same_industry + same_sector)[:limit]


def get_sector_peers(symbol: str, sector: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Peer companies in the same industry (falling back to the same sector), with
    last price and day move.

    Quotes come from the batched, cached `fetch_quotes` rather than one NSE call per
    peer. The per-peer loop issued `limit` sequential requests to NSE's quote-equity
    endpoint, which returns 403 by exchange policy - so it cost ~10s per analysis and
    every peer card rendered with a null price. P/E and market cap are no longer
    claimed here: sourcing them needs a full `.info` fetch per peer, which is the same
    trap in a different shape.
    """
    clean = _clean_symbol(symbol)
    _, industry = get_sector(clean)
    candidates = _peer_symbols(clean, sector, industry, limit)
    if not candidates:
        return []

    try:
        quotes = fetch_quotes(candidates)
    except Exception as e:
        logger.warning("[analyzer] peer quote fetch failed: %s", e)
        quotes = {}

    peers = []
    for p in candidates:
        p_sector, _p_ind = get_sector(p)
        q = quotes.get(p)
        change = q.day_change_per_share if q else None
        p_change = (
            round((change / q.prev_close) * 100, 2)
            if (q and change is not None and q.prev_close)
            else None
        )
        peers.append({
            "symbol": p,
            "name": _company_name(p),
            "current_price": round(q.ltp, 2) if q else None,
            "change": round(change, 2) if change is not None else None,
            "p_change": p_change,
            "sector": p_sector,
        })
    return peers


def _now_iso() -> str:
    """UTC timestamp for the payload's `as_of`, so the UI can show data age."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dividend_yield_pct(info: dict[str, Any]) -> float | None:
    """
    Trailing dividend yield as a percentage, or None when it cannot be established.

    Yahoo's v7 /quote endpoint - which is what `.info` reads - returns this already
    scaled: RELIANCE.NS comes back as 0.46 against a real 0.46% yield, and ITC.NS as
    5.69 against 5.69%. The previous `* 100` therefore rendered Reliance at 46%.

    `dividendRate / price` is the arithmetic cross-check (ITC: 16.0 / 281.0 = 5.69%),
    so it is preferred where both legs are present. The bare value is only trusted
    inside a plausible band; a yield above 30% is far likelier to be a units flip than
    a real payout, and 0 is returned as None rather than as a confident "0.0%".
    """
    rate = info.get("dividendRate")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if rate and price:
        try:
            return round((float(rate) / float(price)) * 100, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    raw = info.get("dividendYield")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    if val > 30:
        # Almost certainly a fraction-vs-percent flip upstream; withhold rather than
        # print an implausible number with two decimal places of false precision.
        logger.warning("[analyzer] implausible dividendYield %.4f, withholding", val)
        return None
    return round(val, 2)


def _fx_to_inr(currency: str | None) -> float | None:
    """
    Multiplier converting `currency` into INR, or None when it cannot be resolved.

    Yahoo quotes some NSE companies in INR but reports their *statements* in another
    currency - INFY.NS is `currency=INR, financialCurrency=USD`, and its `totalRevenue`
    comes back as 20.3bn USD. Dividing that by 1e7 and labelling it "Rs Cr" understated
    Infosys' free cash flow by roughly 85x. Anything not INR is converted here or the
    figure is withheld; it is never relabelled.
    """
    if not currency or currency.upper() == "INR":
        return 1.0

    def _fetch() -> float | None:
        try:
            import yfinance as yf
            fx = yf.Ticker(f"{currency.upper()}INR=X").fast_info
            rate = float(getattr(fx, "last_price", 0) or 0)
            return rate if rate > 0 else None
        except Exception as e:
            logger.warning("[analyzer] FX %s->INR lookup failed: %s", currency, e)
            return None

    # One rate per currency per day: a statement figure does not need intraday FX, and
    # this must not become a per-analysis upstream call.
    return MARKET_CACHE.get_or_compute(
        f"fx_inr_v1:{currency.upper()}", _fetch, 24 * 3600,
    )


def _fetch_consensus(yf_ticker, info: dict[str, Any]) -> dict[str, Any]:
    """
    Forward analyst consensus, or `{}` when nobody covers the name.

    Coverage tracks sell-side following, not size: a Rs 2,000 cr name with one analyst
    has estimates while a Rs 9,000 cr name with none does not. So this gates on the
    data, never on market cap.

    Three of Yahoo's "no coverage" responses are truthy and would pass a naive check:

      * `revenue_estimate` comes back as a 4x4 frame of literal zeros with
        numberOfAnalysts=0 rather than an empty frame, so `if not df.empty` renders a
        confident "forecast revenue Rs 0";
      * `analyst_price_targets` degrades to `{'current': <price>}`, a truthy dict with
        no consensus in it at all;
      * `recommendationKey` reads 'none' even for names with real analyst counts, so it
        is not a usable coverage flag either.

    The gate is therefore numberOfAnalysts > 0 on the estimate frame plus an explicit
    'mean' key on the targets dict.
    """
    out: dict[str, Any] = {}

    try:
        est = yf_ticker.earnings_estimate
        rev = yf_ticker.revenue_estimate
    except Exception:
        return {}

    def _covered(df) -> bool:
        if df is None or getattr(df, "empty", True):
            return False
        if "numberOfAnalysts" not in df.columns:
            return False
        try:
            return float(df["numberOfAnalysts"].max() or 0) > 0
        except (TypeError, ValueError):
            return False

    if not _covered(est) and not _covered(rev):
        return {}

    def _row(df, period: str, field: str):
        try:
            if df is None or df.empty or period not in df.index or field not in df.columns:
                return None
            v = df.loc[period, field]
            return None if v is None or pd.isna(v) else float(v)
        except Exception:
            return None

    if _covered(est):
        out["eps"] = {
            p: {
                "avg": _row(est, p, "avg"),
                "low": _row(est, p, "low"),
                "high": _row(est, p, "high"),
                "analysts": int(_row(est, p, "numberOfAnalysts") or 0),
            }
            for p in ("0q", "+1q", "0y", "+1y")
            if _row(est, p, "numberOfAnalysts")
        }
    if _covered(rev):
        out["revenue_cr"] = {
            p: {
                "avg": round(v / 1e7, 2) if (v := _row(rev, p, "avg")) else None,
                "analysts": int(_row(rev, p, "numberOfAnalysts") or 0),
            }
            for p in ("0q", "+1q", "0y", "+1y")
            if _row(rev, p, "numberOfAnalysts")
        }

    try:
        targets = yf_ticker.analyst_price_targets or {}
    except Exception:
        targets = {}
    # A dict without 'mean' is the degraded `{'current': price}` shape, not a target.
    if isinstance(targets, dict) and "mean" in targets:
        out["price_target"] = {
            k: targets.get(k) for k in ("low", "high", "mean", "median") if targets.get(k) is not None
        }

    opinions = info.get("numberOfAnalystOpinions")
    if opinions:
        out["analyst_count"] = int(opinions)
        rec = info.get("recommendationKey")
        # 'none' co-occurs with genuine analyst counts, so it is dropped rather than shown.
        if rec and rec != "none":
            out["recommendation"] = rec
        if info.get("recommendationMean") is not None:
            out["recommendation_mean"] = round(float(info["recommendationMean"]), 2)

    return out


def _nifty_close_series() -> dict[str, float]:
    """
    NIFTY 50 daily closes for the last ~6 months, keyed by ISO date.

    Cached once process-wide and shared by every analysis: the index level is the same
    for every stock and every user, so this must not become one download per request.

    The Compare tab previously drew its "NIFTY 50 (Benchmark)" line from
    `(i / totalPoints) * stock.year_return * 0.55` - a straight line synthesised from
    the *target stock's own* return, carrying a real-looking legend entry. Nothing was
    ever fetched for it.
    """
    def _fetch() -> dict[str, float]:
        try:
            import yfinance as yf
            hist = yf.download(
                "^NSEI", period="6mo", interval="1d",
                auto_adjust=True, progress=False, timeout=_YF_TIMEOUT,
            )
            if hist is None or hist.empty or "Close" not in hist.columns:
                return {}
            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            return {d.strftime("%Y-%m-%d"): round(float(v), 2)
                    for d, v in zip(close.index, close.values)}
        except Exception as e:
            logger.warning("[analyzer] NIFTY benchmark fetch failed: %s", e)
            return {}

    return MARKET_CACHE.get_or_compute("nifty_close_6mo_v1", _fetch, 12 * 3600)


def _build_timeframe_charts(hist: pd.DataFrame, current_price: float) -> dict[str, Any]:
    """
    Build 1D, 5D, 1M, 6M, YTD, 1Y, 5Y chart slices with change and % change.
    """
    if hist.empty or "Close" not in hist.columns:
        return {}

    close_series = hist["Close"]
    if isinstance(close_series, pd.DataFrame):
        close_series = close_series.iloc[:, 0]
    close_series = close_series.dropna()

    if close_series.empty:
        return {}

    def _slice_tf(series: pd.Series, points: int | None = None, start_dt: pd.Timestamp | None = None):
        if start_dt is not None:
            s = series[series.index >= start_dt]
        elif points is not None:
            s = series.iloc[-points:] if len(series) >= points else series
        else:
            s = series

        if s.empty:
            return {"dates": [], "prices": [], "change": 0.0, "p_change": 0.0}

        st_val = float(s.iloc[0])
        end_val = float(s.iloc[-1])
        chg = round(end_val - st_val, 2)
        pchg = round((chg / st_val) * 100, 2) if st_val else 0.0

        # Endpoints are computed from the *full* slice above, then the points are
        # thinned for transport. The 5Y slice was 1,239 daily points and `timeframes`
        # alone was 40.7 KB of a 56 KB payload - more resolution than a ~600px chart
        # can draw, paid for on every response and in every cache entry. Stride
        # sampling keeps the first and last point so the line still starts and ends
        # where the numbers beside it say it does.
        idx, vals = s.index, s.values
        n = len(s)
        if n > _MAX_CHART_POINTS:
            stride = (n // _MAX_CHART_POINTS) + 1
            keep = list(range(0, n - 1, stride)) + [n - 1]
            idx, vals = idx[keep], vals[keep]

        return {
            "dates": [d.strftime("%Y-%m-%d") for d in idx],
            "prices": [round(float(v), 2) for v in vals],
            "start_price": round(st_val, 2),
            "end_price": round(end_val, 2),
            "change": chg,
            "p_change": pchg,
        }

    now = pd.Timestamp.now()
    start_ytd = pd.Timestamp(year=now.year, month=1, day=1)

    return {
        "1D": _slice_tf(close_series, points=2),
        "5D": _slice_tf(close_series, points=5),
        "1M": _slice_tf(close_series, points=22),
        "6M": _slice_tf(close_series, points=125),
        "YTD": _slice_tf(close_series, start_dt=start_ytd),
        "1Y": _slice_tf(close_series, points=250),
        "5Y": _slice_tf(close_series),
    }


def _yahoo_source_label(eff_ticker: str) -> str:
    """Human-readable Yahoo provenance, including which exchange suffix won."""
    if str(eff_ticker).upper().endswith(".BO"):
        return "Yahoo Finance (.BO)"
    return "Yahoo Finance (.NS)"


def _analyze_stock_uncached(clean: str) -> dict[str, Any]:
    ticker = _to_yf_ticker(clean)
    sector, industry = get_sector(clean)
    effective_ticker = ticker  # may cascade to .BO
    hist = pd.DataFrame()

    # 1. Fetch Official Quote directly from NSE
    nse_quote = nse_client.get_equity_quote(clean)

    # 2. Fetch Extended Fundamentals / Historical prices
    info: dict[str, Any] = {}
    quarterly_fin: list[dict[str, Any]] = []
    earnings_hist: list[dict[str, Any]] = []
    financial_statements: dict[str, Any] = {
        "quarterly": {"income_statement": [], "balance_sheet": [], "cash_flow": []},
        "annual": {"income_statement": [], "balance_sheet": [], "cash_flow": []},
    }
    earnings_summary: dict[str, Any] = {}
    consensus: dict[str, Any] = {}

    try:
        import yfinance as yf
        
        # Use .NS to .BO cascade for info
        info, effective_ticker = _fetch_yf_info(ticker)
        if effective_ticker != ticker:
            logger.info("[analyzer] %s cascaded to %s", ticker, effective_ticker)
        
        # Use the effective ticker for the yf.Ticker object
        yf_ticker = yf.Ticker(effective_ticker)
        
        # If _fetch_yf_info returned empty, try fast_info fallback
        if not info or len(info) <= 10:
            logger.warning("[analyzer] .info failed for %s, falling back to fast_info", effective_ticker)
            try:
                fi = yf_ticker.fast_info
                info = {}
                for src, dst in (
                    ("last_price", "currentPrice"),
                    ("market_cap", "marketCap"),
                    ("year_high", "fiftyTwoWeekHigh"),
                    ("year_low", "fiftyTwoWeekLow"),
                    ("open", "open"),
                    ("day_high", "dayHigh"),
                    ("day_low", "dayLow"),
                    ("currency", "currency"),
                ):
                    val = getattr(fi, src, None)
                    if val is not None:
                        info[dst] = val
            except Exception:
                pass

        def _val(df, row_name, col):
            if df is None or df.empty or row_name not in df.index or col not in df.columns:
                return None
            v = df.loc[row_name, col]
            if v is None or pd.isna(v):
                return None
            return float(v)

        # Statements are denominated in `financialCurrency`, which is not always the
        # quote currency. `fin_fx` is 1.0 for the INR majority and a live rate
        # otherwise; None means we could not resolve one, in which case every derived
        # figure is withheld rather than shown under a "Rs Cr" label it does not have.
        fin_fx = _fx_to_inr(info.get("financialCurrency"))

        def _cr(v):
            if v is None or fin_fx is None:
                return None
            return round((v * fin_fx) / 1e7, 2)

        def _fmt_period(dt, is_quarterly=True):
            col_dt = pd.to_datetime(dt)
            if is_quarterly:
                month_abbr = col_dt.strftime("%b")
                return f"{month_abbr} {col_dt.year}"
            return f"FY {col_dt.year}"

        def _parse_statements(is_quarterly=True):
            q_inc = yf_ticker.quarterly_income_stmt if is_quarterly else yf_ticker.income_stmt
            q_bs = yf_ticker.quarterly_balance_sheet if is_quarterly else yf_ticker.balance_sheet
            q_cf = yf_ticker.quarterly_cashflow if is_quarterly else yf_ticker.cashflow

            cols_set = set()
            for df in (q_inc, q_bs, q_cf):
                if df is not None and not df.empty:
                    cols_set.update(list(df.columns))

            sorted_cols = sorted(list(cols_set), reverse=False)[-5:]

            income_stmt_list = []
            balance_sheet_list = []
            cash_flow_list = []

            for col in sorted_cols:
                period_str = _fmt_period(col, is_quarterly)
                dt_str = pd.to_datetime(col).strftime("%Y-%m-%d")

                # Income Statement
                rev = _val(q_inc, "Total Revenue", col) or _val(q_inc, "Operating Revenue", col)
                op_exp = _val(q_inc, "Operating Expense", col) or _val(q_inc, "Total Expenses", col)
                net_inc = _val(q_inc, "Net Income", col) or _val(q_inc, "Net Income Common Stockholders", col)
                eps = _val(q_inc, "Diluted EPS", col) or _val(q_inc, "Basic EPS", col)
                ebitda = _val(q_inc, "EBITDA", col) or _val(q_inc, "Normalized EBITDA", col)
                tax_rate = _val(q_inc, "Tax Rate For Calcs", col)

                net_margin = round((net_inc / rev * 100), 2) if (net_inc is not None and rev and rev > 0) else None

                income_stmt_list.append({
                    "period": period_str,
                    "date": dt_str,
                    "revenue_cr": _cr(rev),
                    "operating_expense_cr": _cr(op_exp),
                    "net_income_cr": _cr(net_inc),
                    "net_margin_pct": net_margin,
                    # Per-share too, so it carries the same reporting currency.
                    "eps": round(eps * fin_fx, 2) if (eps is not None and fin_fx) else None,
                    "ebitda_cr": _cr(ebitda),
                    "effective_tax_rate_pct": round(tax_rate * 100, 1) if (tax_rate is not None and tax_rate <= 1.0) else (round(tax_rate, 1) if tax_rate is not None else None),
                })

                # Balance Sheet
                cash = _val(q_bs, "Cash Cash Equivalents And Short Term Investments", col) or _val(q_bs, "Cash And Cash Equivalents", col)
                tot_assets = _val(q_bs, "Total Assets", col)
                tot_liab = _val(q_bs, "Total Liabilities Net Minority Interest", col) or _val(q_bs, "Total Liabilities", col)
                equity = _val(q_bs, "Stockholders Equity", col) or _val(q_bs, "Common Stock Equity", col)
                shares = _val(q_bs, "Ordinary Shares Number", col) or _val(q_bs, "Share Issued", col)
                
                roa = round((net_inc / tot_assets * 100), 2) if (net_inc is not None and tot_assets and tot_assets > 0) else None

                balance_sheet_list.append({
                    "period": period_str,
                    "date": dt_str,
                    "cash_and_equivalents_cr": _cr(cash),
                    "total_assets_cr": _cr(tot_assets),
                    "total_liabilities_cr": _cr(tot_liab),
                    "total_equity_cr": _cr(equity),
                    "shares_outstanding": int(shares) if shares is not None else None,
                    # Assets/equity is the equity multiplier - a leverage ratio with no
                    # price term in it. It was labelled "price_to_book" and rendered in
                    # the balance-sheet table under that name.
                    "equity_multiplier": round(tot_assets / equity, 2) if (tot_assets and equity and equity > 0) else None,
                    "return_on_assets_pct": roa,
                })

                # Cash Flow
                cfo = _val(q_cf, "Operating Cash Flow", col)
                cfi = _val(q_cf, "Investing Cash Flow", col)
                cff = _val(q_cf, "Financing Cash Flow", col)
                chg_cash = _val(q_cf, "Changes In Cash", col)
                fcf = _val(q_cf, "Free Cash Flow", col)
                inv = _val(q_cf, "Change In Inventory", col)
                gain_loss = _val(q_cf, "Gain Loss On Sale Of PPE", col) or _val(q_cf, "Gain Loss On Investment Securities", col)

                cash_flow_list.append({
                    "period": period_str,
                    "date": dt_str,
                    "net_income_cr": _cr(net_inc),
                    "cash_from_operations_cr": _cr(cfo),
                    "cash_from_investing_cr": _cr(cfi),
                    "cash_from_financing_cr": _cr(cff),
                    "net_change_in_cash_cr": _cr(chg_cash),
                    "free_cash_flow_cr": _cr(fcf),
                    "change_in_inventories_cr": _cr(inv),
                    "gain_loss_on_sale_assets_cr": _cr(gain_loss),
                })

            return {
                "income_statement": income_stmt_list,
                "balance_sheet": balance_sheet_list,
                "cash_flow": cash_flow_list,
            }

        q_stmts = _parse_statements(is_quarterly=True)
        a_stmts = _parse_statements(is_quarterly=False)
        financial_statements = {
            "quarterly": q_stmts,
            "annual": a_stmts,
        }

        # Format backward compatible quarterly_fin
        for row in q_stmts["income_statement"]:
            quarterly_fin.append({
                "quarter": row["period"],
                "date": row["date"],
                "revenue_cr": row["revenue_cr"] or 0.0,
                "net_income_cr": row["net_income_cr"] or 0.0,
                "operating_income_cr": row["operating_expense_cr"] or 0.0,
                "net_margin_pct": row["net_margin_pct"] or 0.0,
            })

        # Earnings history: reported actuals only.
        #
        # Every "estimate" here used to be synthesised from the actual it was compared
        # against - `estimated_eps = reported_eps * 0.97`, `estimated_revenue = revenue
        # * 0.98` - so every quarter beat by exactly +3.09% on EPS and +2.04% on
        # revenue, and the UI presented that as analyst consensus under a "Surprise %"
        # column. Yahoo publishes no *historical* consensus for NSE names, so there is
        # nothing to compare a past quarter against. We report what the company
        # reported and leave the estimate fields null; the UI already omits the slot
        # when an estimate is missing. Forward consensus, where it exists, is a
        # separate field (`consensus`) and is never mixed into reported history.
        cal = yf_ticker.calendar or {}
        latest_q = q_stmts["income_statement"][-1] if q_stmts["income_statement"] else None
        last_rep_dt = cal.get("Earnings Date")
        if isinstance(last_rep_dt, list) and len(last_rep_dt) > 0:
            last_rep_date_str = pd.to_datetime(last_rep_dt[0]).strftime("%d %b %Y")
        elif latest_q:
            last_rep_date_str = pd.to_datetime(latest_q["date"]).strftime("%d %b %Y")
        else:
            last_rep_date_str = None

        earnings_quarters = []
        for inc_row in q_stmts["income_statement"]:
            item = {
                "period": inc_row["period"],
                "date": inc_row["date"],
                "reported_eps": inc_row.get("eps"),
                "estimated_eps": None,
                "surprise_pct": None,
                "eps_surprise_type": None,
                "reported_revenue_cr": inc_row.get("revenue_cr"),
                "estimated_revenue_cr": None,
                "revenue_surprise_pct": None,
                "revenue_surprise_type": None,
            }
            earnings_quarters.append(item)
            earnings_hist.append({
                "date": inc_row["date"],
                "quarter": inc_row["period"],
                "reported_eps": inc_row.get("eps"),
                "estimated_eps": None,
                "surprise_pct": None,
            })

        earnings_summary = {
            "last_report_date": last_rep_date_str,
            "financial_period": latest_q["period"] if latest_q else None,
            "reported_eps": latest_q.get("eps") if latest_q else None,
            "reported_revenue_cr": latest_q.get("revenue_cr") if latest_q else None,
            "history": earnings_quarters,
        }

        consensus = _fetch_consensus(yf_ticker, info)

    except Exception as e:
        logger.warning("[analyzer] extended info failed for %s: %s", ticker, e)
        info = {}

    prices = pd.Series(dtype=float)
    current_price = 0.0
    year_return = 0.0
    price_dates: list[str] = []
    price_values: list[float] = []
    sma_50_series: list[float | None] = []
    sma_200_series: list[float | None] = []
    volume_values: list[int] = []
    timeframe_charts: dict[str, Any] = {}

    try:
        import yfinance as yf
        hist = yf.download(
            effective_ticker, period="5y", interval="1d",
            auto_adjust=True, progress=False, timeout=_YF_TIMEOUT,
        )
        if not hist.empty:
            # yfinance returns MultiIndex columns ("Close", "RELIANCE.NS") for a single
            # ticker on some paths and flat ones on others, and which you get is not
            # stable across symbols. The `Close` reads below coped, but the per-row
            # candlestick loop did not: `row.get("Open")` returned a Series and
            # float() raised, which the blanket except caught and logged as
            # "price history failed". The whole block was then skipped, so the chart,
            # all seven timeframes, candlesticks, volume AND technicals came back
            # empty while the rest of the payload looked fine. Flattened once here so
            # every consumer below sees one shape.
            if isinstance(hist.columns, pd.MultiIndex):
                hist = hist.droplevel(-1, axis=1)
                hist = hist.loc[:, ~hist.columns.duplicated()]

            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            prices = close.dropna()
            current_price = round(float(prices.iloc[-1]), 2) if len(prices) else 0.0
            
            # 1Y endpoints
            p_1y = prices.iloc[-250:] if len(prices) >= 250 else prices
            year_start = float(p_1y.iloc[0]) if len(p_1y) else 0.0
            year_return = round((current_price / year_start - 1) * 100, 2) if year_start else 0.0
            
            # 90-day tail for standard view
            tail = prices.iloc[-90:]
            price_dates = [d.strftime("%Y-%m-%d") for d in tail.index]
            price_values = [round(float(v), 2) for v in tail.values]

            # Moving-average *series*, not the scalars alone. The UI plotted
            # `technicals.sma_50` - a single number - against every point, so the
            # "50 DMA" and "200 DMA" overlays rendered as flat horizontal lines that
            # were visually indistinguishable from a real moving average. Computed off
            # the full 5y series so the 200-day window is genuinely 200 days, then
            # sliced to the same 90-point window as the price line.
            def _sma_tail(window: int) -> list[float | None]:
                if len(prices) < window:
                    return []
                s = prices.rolling(window=window).mean().iloc[-90:]
                return [None if pd.isna(v) else round(float(v), 2) for v in s.values]

            sma_50_series = _sma_tail(50)
            sma_200_series = _sma_tail(200)

            # Multi-timeframe charts
            timeframe_charts = _build_timeframe_charts(hist, current_price)

            # Daily volume for the same 90-day window as `chart`, as a parallel array.
            #
            # This used to ship two array-of-object series - `candlesticks` (date, open,
            # high, low, close) and `volume_series` (date, volume, is_up) - totalling
            # 13.1 KB of a 58 KB payload. Nothing rendered the candlesticks at all: the
            # switcher only offers area and line, and Recharts has no candle primitive,
            # so it was dead weight in every response and every cache entry. The volume
            # series repeated a date string per row that `chart.dates` already carries,
            # and `is_up` is derivable from the price series beside it.
            #
            # Columnar and aligned to `chart.dates` instead: ~0.6 KB for the same
            # information. If a candlestick chart is built later, OHLC comes back the
            # same way rather than as 90 dicts.
            if "Volume" in hist.columns:
                vol_tail = hist["Volume"].iloc[-90:]
                volume_values = [
                    0 if pd.isna(v) else int(v) for v in vol_tail.values
                ]
    except Exception as e:
        logger.warning("[analyzer] price history failed for %s: %s", ticker, e)

    def _f(key, default=None):
        val = info.get(key, default)
        if val is None or val != val:
            return default
        return val

    # Merge official NSE data with extended indicators
    effective_name = (nse_quote.get("name") if nse_quote else None) or _f("longName", clean)
    effective_price = (nse_quote.get("current_price") if (nse_quote and nse_quote.get("current_price")) else None) or current_price or _f("currentPrice", 0)
    effective_sector = (nse_quote.get("sector") if nse_quote else None) or sector
    effective_industry = (nse_quote.get("industry") if nse_quote else None) or industry
    # Rounded at the source. `fast_info` returns full float precision
    # (1611.800048828125), which is noise in a rupee price and costs bytes in every
    # response and cache entry.
    def _r2(v):
        return round(float(v), 2) if isinstance(v, (int, float)) else v

    week52_high = _r2((nse_quote.get("week52_high") if nse_quote else None) or _f("fiftyTwoWeekHigh"))
    week52_low = _r2((nse_quote.get("week52_low") if nse_quote else None) or _f("fiftyTwoWeekLow"))
    market_cap_cr = (nse_quote.get("market_cap_cr") if nse_quote else None) or (round(_f("marketCap", 0) / 1e7, 0) if _f("marketCap") else None)
    pe_ratio = (nse_quote.get("pe_ratio") if (nse_quote and nse_quote.get("pe_ratio") is not None) else None) or _f("trailingPE")
    sector_pe = nse_quote.get("sector_pe") if nse_quote else None
    vwap = nse_quote.get("vwap") if nse_quote else None
    delivery_pct = nse_quote.get("delivery_pct") if nse_quote else None
    isin = (nse_quote.get("isin") if nse_quote else None) or info.get("isin")
    series = (nse_quote.get("series") if nse_quote else None) or "EQ"

    # Day Open, High, Low
    day_open = _r2(_f("open") or _f("regularMarketOpen"))
    day_high = _r2(_f("dayHigh") or _f("regularMarketDayHigh") or effective_price)
    day_low = _r2(_f("dayLow") or _f("regularMarketDayLow") or effective_price)

    technicals = _compute_technicals(prices, effective_price, week52_high, week52_low)
    peers = get_sector_peers(clean, effective_sector, limit=5)

    # NSE's disclosure endpoints still serve, unlike its quote API. These fail soft to
    # empty lists - notably on a cloud host, where NSE blocks datacenter IPs outright -
    # so the analyzer degrades to "no corporate actions" rather than to an error.
    # Four independent NSE lookups, overlapped rather than run in series.
    #
    # Each is a separate cache entry and a separate round trip, and NSE is slow: run
    # sequentially they took a cold SWIGGY analysis from ~35s to 91.6s. They are pure
    # I/O wait, so the threads cost almost no CPU, and the pool is sized to exactly the
    # number of tasks so nothing is left idle. Each already fails soft to an
    # empty result, so a failure here degrades one section rather than the response.
    #
    #   corporate_actions - dividends, bonuses, splits (NSE is authoritative; yfinance
    #                       reports bonuses as splits and mis-scales compound actions)
    #   event_calendar    - upcoming board meetings and results dates
    #   latest_results    - the company's own most recent filing, with its basis and
    #                       audit status stated; fills the quarter yfinance leaves thin
    #   announcements     - per-symbol exchange filings, used in place of a news feed
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="nse") as pool:
        f_actions = pool.submit(nse_corporate.corporate_actions, clean)
        f_events = pool.submit(nse_corporate.event_calendar, clean)
        f_filing = pool.submit(nse_results.latest_results, clean)
        f_announce = pool.submit(nse_corporate.announcements, clean, 6)

        def _settled(future, default):
            try:
                return future.result()
            except Exception as e:
                logger.warning("[analyzer] NSE lookup failed for %s: %s", clean, e)
                return default

        actions = _settled(f_actions, [])
        calendar_events = _settled(f_events, [])
        latest_filing = _settled(f_filing, None)
        recent_filings = _settled(f_announce, [])

    fin_currency = _f("financialCurrency") or "INR"
    stmt_fx = _fx_to_inr(fin_currency)
    
    # Compute math-based beta (primary) with Yahoo beta as fallback
    math_beta = _compute_beta(hist, clean)
    yahoo_beta = _f("beta")
    effective_beta = math_beta or yahoo_beta
    
    # Compute NSE dividend yield (primary) with Yahoo yield as fallback
    nse_yield = _nse_dividend_yield(actions, effective_price)
    yahoo_yield = _dividend_yield_pct(info)
    effective_dividend_yield = nse_yield or yahoo_yield
    
    # Fetch BSE VWAP
    bse_vwap = bse_client.get_vwap(clean)
    effective_vwap = bse_vwap or vwap

    yahoo_lbl = _yahoo_source_label(effective_ticker)

    def _pick_src(preferred: str | None, *candidates: tuple[Any, str]) -> str:
        """First non-None value wins; label the winning source."""
        for val, label in candidates:
            if val is not None:
                return label
        return preferred or "Unavailable"

    price_src = _pick_src(
        None,
        (nse_quote.get("current_price") if nse_quote else None, "NSE"),
        (current_price or None, yahoo_lbl),
        (_f("currentPrice"), yahoo_lbl),
    )
    day_src = yahoo_lbl if (day_open or day_high or day_low) else "Unavailable"
    mcap_src = _pick_src(
        None,
        (nse_quote.get("market_cap_cr") if nse_quote else None, "NSE"),
        (_f("marketCap"), yahoo_lbl),
    )
    pe_src = _pick_src(
        None,
        (nse_quote.get("pe_ratio") if nse_quote else None, "NSE"),
        (_f("trailingPE"), yahoo_lbl),
    )
    pb_src = _pick_src(None, (_f("priceToBook"), yahoo_lbl))
    eps_src = _pick_src(None, (_f("trailingEps"), yahoo_lbl))
    div_src = _pick_src(
        None,
        (nse_yield, "NSE Corporate Actions"),
        (yahoo_yield, yahoo_lbl),
    )
    beta_src = _pick_src(
        None,
        (math_beta, "Math (vs Nifty 50)"),
        (yahoo_beta, yahoo_lbl),
    )
    vwap_src = _pick_src(
        None,
        (bse_vwap, "BSE"),
        (vwap, "NSE"),
    )
    has_statements = bool(
        financial_statements.get("quarterly", {}).get("income_statement")
        or financial_statements.get("annual", {}).get("income_statement")
        or quarterly_fin
    )
    sources = {
        "price": price_src,
        "day_range": day_src,
        "market_cap": mcap_src,
        "pe_ratio": pe_src,
        "pb_ratio": pb_src,
        "eps": eps_src,
        "dividend_yield": div_src,
        "beta": beta_src,
        "vwap": vwap_src,
        "delivery_pct": "NSE" if delivery_pct is not None else "Unavailable",
        # Card-level summaries for section info icons
        "charts": yahoo_lbl if (price_dates or timeframe_charts) else "Unavailable",
        "valuation": (
            f"Market Cap: {mcap_src} · P/E: {pe_src} · P/B: {pb_src} · EPS: {eps_src} · "
            f"Dividend Yield: {div_src} · Beta: {beta_src} · VWAP: {vwap_src}"
        ),
        "technicals": (
            "Computed from Yahoo price history" if not prices.empty else "Unavailable"
        ),
        "peers": "Yahoo quotes + NSE sector map" if peers else "Unavailable",
        "financials": yahoo_lbl if has_statements else "Unavailable",
        "earnings": yahoo_lbl if (earnings_hist or earnings_summary) else "Unavailable",
        "consensus": yahoo_lbl if consensus else "Unavailable",
        "corporate_actions": "NSE Disclosures" if actions else "Unavailable",
        "events": "NSE Event Calendar" if calendar_events else "Unavailable",
        "announcements": "NSE Announcements" if recent_filings else "Unavailable",
        "latest_filing": "NSE Integrated Filings" if latest_filing else "Unavailable",
        "compare": yahoo_lbl,
        "description": yahoo_lbl if _f("longBusinessSummary") else "Unavailable",
    }

    result = {
        # Provenance, so the UI can stop asserting "NSE Live Terminal" over data that
        # did not come from NSE. quote-equity returns 403 by exchange policy, so
        # `nse_quote` is normally None and everything below is Yahoo-sourced.
        "source": "NSE" if nse_quote else yahoo_lbl,
        "sources": sources,
        "as_of": _now_iso(),
        "financial_currency": fin_currency,
        "symbol": clean,
        "name": effective_name,
        "sector": effective_sector,
        "industry": effective_industry,
        "ticker": ticker,
        "isin": isin,
        "series": series,
        "current_price": effective_price,
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "market_cap": _f("marketCap"),
        "market_cap_cr": market_cap_cr,
        "pe_ratio": pe_ratio,
        "sector_pe": sector_pe,
        "forward_pe": _f("forwardPE"),
        "peg_ratio": _f("pegRatio"),
        "pb_ratio": _f("priceToBook"),
        "price_to_sales": _f("priceToSalesTrailing12Months"),
        # NOT FX-converted, unlike the statement figures below. Yahoo splits `.info` by
        # provenance: quote-derived fields (trailingEps, dividendRate, marketCap) are in
        # the *quote* currency, while statement-derived ones (freeCashflow, totalRevenue)
        # follow `financialCurrency`. Verified on INFY.NS, whose statements are USD:
        # trailingEps 77.52 against a price of 1148.6 reproduces trailingPE 14.82
        # exactly, so it is already INR.
        "eps": _f("trailingEps"),
        # Already a percentage on this endpoint: Yahoo's v7 /quote returns 0.46 for
        # RELIANCE, whose yield is 0.46%. The *100 here rendered it as 46%. Guarded
        # rather than merely un-multiplied, because Yahoo has flipped these units
        # before - dividendRate/price is the cross-check when both are present.
        "dividend_yield": effective_dividend_yield,
        "roe": round(_f("returnOnEquity", 0) * 100, 2) if _f("returnOnEquity") else None,
        "profit_margins": round(_f("profitMargins", 0) * 100, 2) if _f("profitMargins") else None,
        "operating_margins": round(_f("operatingMargins", 0) * 100, 2) if _f("operatingMargins") else None,
        "debt_to_equity": _f("debtToEquity"),
        "free_cash_flow_cr": (
            round((_f("freeCashflow") * stmt_fx) / 1e7, 0)
            if (_f("freeCashflow") and stmt_fx) else None
        ),
        "week52_high": week52_high,
        "week52_low": week52_low,
        "vwap": effective_vwap,  # BSE VWAP (primary) or NSE VWAP (fallback)
        "delivery_pct": delivery_pct,
        "avg_volume": _f("averageVolume"),
        "volume": _f("volume"),
        "beta": effective_beta,
        "year_return": year_return,
        "technicals": technicals,
        "peers": peers,
        "financials": quarterly_fin,
        "financial_statements": financial_statements,
        "earnings": earnings_hist,
        "earnings_summary": earnings_summary,
        "consensus": consensus,
        # Authoritative, and the one place NSE beats Yahoo outright: yfinance reports
        # Indian bonus issues as splits indistinguishably, and gets compound actions
        # wrong outright (BAJFINANCE Jun-2025 is 10x; yfinance says 2.0).
        "corporate_actions": actions[:12],
        "upcoming_events": [e for e in calendar_events if e.get("date")][:6],
        "latest_filing": latest_filing,
        "announcements": recent_filings,
        "description": (_f("longBusinessSummary", "")[:600] + "...") if _f("longBusinessSummary") else "",
        "chart": {
            "dates": price_dates,
            "prices": price_values,
            "sma_50": sma_50_series,
            "sma_200": sma_200_series,
            "volume": volume_values,
            # Real index closes aligned to the same dates, so the Compare tab can plot
            # a benchmark instead of synthesising one. None on days the index has no
            # print for a date the stock does.
            "benchmark": [_nifty.get(d) for d in price_dates] if (_nifty := _nifty_close_series()) else [],
        },
        "timeframes": timeframe_charts,
    }
    
    return result


# The background sweep rebuilds warm symbols on the janitor thread. Registered at
# import, like every other janitor sweep in the codebase, so mounting the equity router
# is what turns it on - and importing this module in a test does not start a thread.
refresh.register(refresh.TIER_DAILY, _refresh_analysis)


# ── Portfolio Impact ─────────────────────────────────────────────────────────

def compute_portfolio_impact(
    symbol: str,
    amount: float,
    current_holdings: list[dict],
    current_total: float,
) -> dict[str, Any]:
    """
    Simulate adding `amount` rupees of `symbol` to the portfolio.
    Returns before/after sector allocation, weight change, and diversification delta.
    """
    clean = _clean_symbol(symbol)
    sector, industry = get_sector(clean)

    # Compute BEFORE sector allocation
    df = pd.DataFrame(current_holdings) if current_holdings else pd.DataFrame()
    total_before = current_total

    before_sectors: dict[str, float] = {}
    if not df.empty and "sector" in df.columns and "current_value" in df.columns:
        grp = df.groupby("sector")["current_value"].sum()
        for s, v in grp.items():
            before_sectors[str(s)] = round(v / total_before * 100, 2) if total_before else 0

    # AFTER: add the new position
    total_after = total_before + amount
    after_sectors = {}
    for s, pct in before_sectors.items():
        after_sectors[s] = round(pct * total_before / total_after, 2)
    after_sectors[sector] = round(
        (before_sectors.get(sector, 0) / 100 * total_before + amount) / total_after * 100, 2
    )

    # Already owned?
    existing = {}
    if not df.empty and "symbol" in df.columns:
        row = df[df["symbol"].str.upper() == clean]
        if not row.empty:
            existing = {
                "quantity": float(row.iloc[0].get("quantity", 0)),
                "avg_price": float(row.iloc[0].get("avg_price", 0)),
                "current_value": float(row.iloc[0].get("current_value", 0)),
            }

    sector_delta = round(
        after_sectors.get(sector, 0) - before_sectors.get(sector, 0), 2
    )

    return {
        "symbol": clean,
        "sector": sector,
        "industry": industry,
        "investment_amount": round(amount, 2),
        "portfolio_weight_after": round(amount / total_after * 100, 2) if total_after else 0,
        "sector_weight_before": round(before_sectors.get(sector, 0), 2),
        "sector_weight_after": round(after_sectors.get(sector, 0), 2),
        "sector_delta": sector_delta,
        "before_allocation": [{"sector": k, "pct": v} for k, v in sorted(before_sectors.items(), key=lambda x: -x[1])],
        "after_allocation": [{"sector": k, "pct": v} for k, v in sorted(after_sectors.items(), key=lambda x: -x[1])],
        "already_owned": bool(existing),
        "existing_position": existing,
        "concentration_warning": (amount / total_after * 100) > 15 if total_after else False,
    }
