"""
domains/equity/stock_analyzer.py

Stock research and portfolio impact analysis engine.

Fetches fundamental data from Yahoo Finance (yfinance) and computes
how adding a new position would shift an existing equity portfolio's
sector allocation, beta, and diversification score.
"""

import logging
from typing import Any

import pandas as pd

from domains.equity.sector_map import get_sector

logger = logging.getLogger(__name__)


# ── NSE → Yahoo Finance ticker conversion ────────────────────────────────────

def _to_yf_ticker(symbol: str) -> str:
    s = symbol.upper().strip().replace("-EQ", "")
    if not s.endswith(".NS"):
        return s + ".NS"
    return s


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("-EQ", "").replace(".NS", "").replace(".BO", "")


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


def search_stocks(query: str, limit: int = 10) -> list[dict]:
    """
    Search for NSE stocks by symbol or name.
    Returns list of {symbol, name, sector, industry}.
    """
    q = query.upper().strip()
    results = []
    for item in _SEARCH_INDEX:
        sym = item["symbol"].upper()
        name = item["name"].upper()
        if q in sym or q in name:
            sector, industry = get_sector(sym)
            results.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "sector": sector,
                "industry": industry,
                "ticker": _to_yf_ticker(item["symbol"]),
            })
    return results[:limit]


# ── Stock Analysis ───────────────────────────────────────────────────────────

def analyze_stock(symbol: str) -> dict[str, Any]:
    """
    Fetch comprehensive fundamental + technical data for a single NSE stock.
    Uses yfinance. Returns a rich analysis card.
    """
    clean = _clean_symbol(symbol)
    ticker = _to_yf_ticker(clean)
    sector, industry = get_sector(clean)

    try:
        import yfinance as yf
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
    except Exception as e:
        logger.warning("[analyzer] yfinance info failed for %s: %s", ticker, e)
        info = {}

    # Price history for chart + performance
    try:
        import yfinance as yf
        hist = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False)
        if not hist.empty:
            prices = hist["Close"].dropna()
            price_dates = [d.strftime("%Y-%m-%d") for d in prices.index]
            price_values = [round(float(v), 2) for v in prices.values]
            current_price = price_values[-1] if price_values else 0
            year_start = price_values[0] if price_values else 0
            year_return = round((current_price / year_start - 1) * 100, 2) if year_start else 0.0
        else:
            price_dates, price_values, current_price, year_return = [], [], 0, 0.0
    except Exception as e:
        logger.warning("[analyzer] price history failed for %s: %s", ticker, e)
        price_dates, price_values, current_price, year_return = [], [], 0, 0.0

    # Fundamental metrics
    def _f(key, default=None):
        val = info.get(key, default)
        if val is None or val != val:  # NaN check
            return default
        return val

    return {
        "symbol": clean,
        "name": _f("longName", clean),
        "sector": sector,
        "industry": industry,
        "ticker": ticker,
        "current_price": current_price or _f("currentPrice", 0),
        "market_cap": _f("marketCap"),
        "market_cap_cr": round(_f("marketCap", 0) / 1e7, 0) if _f("marketCap") else None,
        "pe_ratio": _f("trailingPE"),
        "pb_ratio": _f("priceToBook"),
        "eps": _f("trailingEps"),
        "dividend_yield": round(_f("dividendYield", 0) * 100, 2) if _f("dividendYield") else 0,
        "roe": round(_f("returnOnEquity", 0) * 100, 2) if _f("returnOnEquity") else None,
        "debt_to_equity": _f("debtToEquity"),
        "week52_high": _f("fiftyTwoWeekHigh"),
        "week52_low": _f("fiftyTwoWeekLow"),
        "avg_volume": _f("averageVolume"),
        "beta": _f("beta"),
        "year_return": year_return,
        "description": (_f("longBusinessSummary", "")[:400] + "...") if _f("longBusinessSummary") else "",
        "chart": {
            "dates": price_dates[-90:],   # Last 3 months for chart
            "prices": price_values[-90:],
        },
    }


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
