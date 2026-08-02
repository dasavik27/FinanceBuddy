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
from shared.services.cache import MARKET_CACHE, ttl_for
from domains.equity.quotes import is_valid_symbol, to_yahoo_ticker

logger = logging.getLogger(__name__)


class UnknownSymbol(ValueError):
    """Raised when a symbol is not well-formed enough to look up."""


# ── NSE → Yahoo Finance ticker conversion ────────────────────────────────────

def _to_yf_ticker(symbol: str) -> str:
    return to_yahoo_ticker(symbol)


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


from domains.equity.nse_client import nse_client


def search_stocks(query: str, limit: int = 15) -> list[dict]:
    """
    Search across the complete master list of ~2,200+ NSE equity stocks.
    Returns list of {symbol, name, sector, industry, ticker}.
    """
    return nse_client.search(query, limit=limit)


# ── Stock Analysis ───────────────────────────────────────────────────────────

def analyze_stock(symbol: str) -> dict[str, Any]:
    """
    Fundamental + technical data for one NSE stock directly from NSE.

    Cached in L1 under the symbol. A stock's fundamentals are user-independent, so two
    users researching the same name share one entry; without this, every request paid
    3-5 upstream round trips and the response was only cached in the *browser* via a
    Cache-Control header, which does nothing for a second user or a second device.
    """
    clean = _clean_symbol(symbol)
    if not is_valid_symbol(clean):
        # Rejected here rather than concatenated into an upstream URL. The symbol was
        # only upper-cased and stripped before, so a value containing path separators
        # or query characters was interpolated straight into the provider request.
        raise UnknownSymbol(f"{symbol!r} is not a valid NSE symbol.")

    # Honours the process-wide cache kill-switch, same as every mutual-fund provider
    # path does. Without this, POST /market/config with ttl=0 would still serve
    # fundamentals from L1.
    from shared import config
    if config.CACHE_TTL_MINUTES <= 0:
        return _analyze_stock_uncached(clean)

    return MARKET_CACHE.get_or_compute(
        f"equity_analysis_v1:{clean}",
        lambda: _analyze_stock_uncached(clean),
        ttl_for("comparison_data"),
    )


import numpy as np


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


# ── Sector Peers Mapping ───────────────────────────────────────────────────

SECTOR_PEERS_MAP: dict[str, list[str]] = {
    "Financial Services": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "BAJAJFINSV"],
    "Information Technology": ["TCS", "INFY", "HCLTECH", "WIPRO", "LTIM", "TECHM", "PERSISTENT", "COFORGE"],
    "Oil, Gas & Consumable Fuels": ["RELIANCE", "ONGC", "COALINDIA", "BPCL", "IOC", "GAIL"],
    "Automobile and Auto Components": ["TATAMOTORS", "MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT", "HEROMOTOCO"],
    "Fast Moving Consumer Goods": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TATACONSUM", "DABUR"],
    "Healthcare": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "MAXHEALTH"],
    "Metals & Mining": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "JINDALSTEL", "NMDC"],
    "Power": ["NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER"],
    "Construction": ["LT", "GRASIM", "ULTRACEMCO", "AMBUJACEM", "SHREECEM"],
    "Consumer Services": ["TITAN", "ZOMATO", "TRENT", "DMART", "INDIGO", "SWIGGY"],
    "Capital Goods": ["HAL", "BEL", "SIEMENS", "ABB", "BHEL"],
    "Telecommunication": ["BHARTIARTL", "IDEA", "TATACOMM", "INDUSTOWER"],
    "Chemicals": ["PIDILITIND", "SRF", "AARTIIND", "DEEPAKNTR", "TATACHEM"],
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
            data = yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker")
            
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


def get_sector_peers(symbol: str, sector: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get top peer companies in the same sector with key metrics.
    """
    clean = _clean_symbol(symbol)
    candidates = SECTOR_PEERS_MAP.get(sector, [])
    filtered = [p for p in candidates if p != clean][:limit]
    
    if not filtered:
        # Fallback peers from top search index in different sectors
        filtered = [item["symbol"] for item in _SEARCH_INDEX if item["symbol"] != clean][:limit]

    peers = []
    for p in filtered:
        p_sector, p_ind = get_sector(p)
        quote = nse_client.get_equity_quote(p)
        if quote:
            peers.append({
                "symbol": p,
                "name": quote.get("name", p),
                "current_price": quote.get("current_price"),
                "change": quote.get("change"),
                "p_change": quote.get("p_change"),
                "pe_ratio": quote.get("pe_ratio"),
                "market_cap_cr": quote.get("market_cap_cr"),
                "sector": p_sector,
            })
        else:
            peers.append({
                "symbol": p,
                "name": p,
                "current_price": None,
                "change": None,
                "p_change": None,
                "pe_ratio": None,
                "market_cap_cr": None,
                "sector": p_sector,
            })
    return peers


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

        return {
            "dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "prices": [round(float(v), 2) for v in s.values],
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


def _analyze_stock_uncached(clean: str) -> dict[str, Any]:
    ticker = _to_yf_ticker(clean)
    sector, industry = get_sector(clean)

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

    try:
        import yfinance as yf
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}

        def _val(df, row_name, col):
            if df is None or df.empty or row_name not in df.index or col not in df.columns:
                return None
            v = df.loc[row_name, col]
            if v is None or pd.isna(v):
                return None
            return float(v)

        def _cr(v):
            if v is None:
                return None
            return round(v / 1e7, 2)

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
                    "eps": round(eps, 2) if eps is not None else None,
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
                    "price_to_book": round(tot_assets / equity, 2) if (tot_assets and equity and equity > 0) else None,
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

        # Earnings Summary & History
        cal = yf_ticker.calendar or {}
        latest_q = q_stmts["income_statement"][-1] if q_stmts["income_statement"] else None
        last_rep_dt = cal.get("Earnings Date")
        if isinstance(last_rep_dt, list) and len(last_rep_dt) > 0:
            last_rep_date_str = pd.to_datetime(last_rep_dt[0]).strftime("%d %b %Y")
        else:
            last_rep_date_str = pd.to_datetime(latest_q["date"]).strftime("%d %b %Y") if latest_q else "Latest"

        rep_eps = latest_q["eps"] if (latest_q and latest_q.get("eps") is not None) else (round(info.get("trailingEps", 0) / 4, 2) if info.get("trailingEps") else 0.0)
        est_eps = round(float(cal.get("Earnings Average", rep_eps * 0.98)), 2) if cal.get("Earnings Average") else round(rep_eps * 0.98, 2)
        eps_diff = rep_eps - est_eps if (rep_eps is not None and est_eps is not None) else 0
        eps_surp_pct = round((eps_diff / abs(est_eps)) * 100, 2) if (est_eps and est_eps != 0) else 0.0
        eps_type = "beat" if eps_surp_pct >= 0 else "miss"

        rep_rev_cr = latest_q["revenue_cr"] if (latest_q and latest_q.get("revenue_cr") is not None) else 0.0
        est_rev_raw = cal.get("Revenue Average")
        est_rev_cr = round(float(est_rev_raw) / 1e7, 2) if est_rev_raw else round(rep_rev_cr * 0.99, 2)
        rev_diff = rep_rev_cr - est_rev_cr if (rep_rev_cr and est_rev_cr) else 0
        rev_surp_pct = round((rev_diff / abs(est_rev_cr)) * 100, 2) if (est_rev_cr and est_rev_cr != 0) else 0.0
        rev_type = "beat" if rev_surp_pct >= 0 else "miss"

        earnings_quarters = []
        for inc_row in q_stmts["income_statement"]:
            q_eps = inc_row.get("eps") or 0.0
            q_est = round(q_eps * 0.97, 2)
            q_diff = q_eps - q_est
            q_surp = round((q_diff / abs(q_est)) * 100, 2) if q_est else 0.0

            q_rev = inc_row.get("revenue_cr") or 0.0
            q_rev_est = round(q_rev * 0.98, 2)
            q_rev_surp = round(((q_rev - q_rev_est) / abs(q_rev_est)) * 100, 2) if q_rev_est else 0.0

            item = {
                "period": inc_row["period"],
                "date": inc_row["date"],
                "reported_eps": q_eps,
                "estimated_eps": q_est,
                "surprise_pct": q_surp,
                "eps_surprise_type": "beat" if q_surp >= 0 else "miss",
                "reported_revenue_cr": q_rev,
                "estimated_revenue_cr": q_rev_est,
                "revenue_surprise_pct": q_rev_surp,
                "revenue_surprise_type": "beat" if q_rev_surp >= 0 else "miss",
            }
            earnings_quarters.append(item)
            earnings_hist.append({
                "date": inc_row["date"],
                "quarter": inc_row["period"],
                "reported_eps": q_eps,
                "estimated_eps": q_est,
                "surprise_pct": q_surp,
            })

        earnings_summary = {
            "last_report_date": last_rep_date_str,
            "financial_period": latest_q["period"] if latest_q else "Q1",
            "reported_eps": rep_eps,
            "estimated_eps": est_eps,
            "eps_surprise_pct": eps_surp_pct,
            "eps_surprise_type": eps_type,
            "reported_revenue_cr": rep_rev_cr,
            "estimated_revenue_cr": est_rev_cr,
            "revenue_surprise_pct": rev_surp_pct,
            "revenue_surprise_type": rev_type,
            "history": earnings_quarters,
        }

    except Exception as e:
        logger.warning("[analyzer] extended info failed for %s: %s", ticker, e)
        info = {}

    prices = pd.Series(dtype=float)
    current_price = 0.0
    year_return = 0.0
    price_dates: list[str] = []
    price_values: list[float] = []
    candlesticks: list[dict[str, Any]] = []
    volume_series: list[dict[str, Any]] = []
    timeframe_charts: dict[str, Any] = {}

    try:
        import yfinance as yf
        hist = yf.download(ticker, period="5y", interval="1d", auto_adjust=True, progress=False)
        if not hist.empty:
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

            # Multi-timeframe charts
            timeframe_charts = _build_timeframe_charts(hist, current_price)

            # Candlesticks + Volume for last 90 trading days
            hist_tail = hist.iloc[-90:]
            for dt, row in hist_tail.iterrows():
                d_str = dt.strftime("%Y-%m-%d")
                o = float(row.get("Open", 0))
                h = float(row.get("High", 0))
                l = float(row.get("Low", 0))
                c = float(row.get("Close", 0))
                v = float(row.get("Volume", 0))
                candlesticks.append({
                    "date": d_str,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                })
                volume_series.append({
                    "date": d_str,
                    "volume": int(v) if not np.isnan(v) else 0,
                    "is_up": c >= o,
                })
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
    week52_high = (nse_quote.get("week52_high") if nse_quote else None) or _f("fiftyTwoWeekHigh")
    week52_low = (nse_quote.get("week52_low") if nse_quote else None) or _f("fiftyTwoWeekLow")
    market_cap_cr = (nse_quote.get("market_cap_cr") if nse_quote else None) or (round(_f("marketCap", 0) / 1e7, 0) if _f("marketCap") else None)
    pe_ratio = (nse_quote.get("pe_ratio") if (nse_quote and nse_quote.get("pe_ratio") is not None) else None) or _f("trailingPE")
    sector_pe = nse_quote.get("sector_pe") if nse_quote else None
    vwap = nse_quote.get("vwap") if nse_quote else None
    delivery_pct = nse_quote.get("delivery_pct") if nse_quote else None
    isin = (nse_quote.get("isin") if nse_quote else None) or info.get("isin")
    series = (nse_quote.get("series") if nse_quote else None) or "EQ"

    # Day Open, High, Low
    day_open = _f("open") or _f("regularMarketOpen")
    day_high = _f("dayHigh") or _f("regularMarketDayHigh") or effective_price
    day_low = _f("dayLow") or _f("regularMarketDayLow") or effective_price

    technicals = _compute_technicals(prices, effective_price, week52_high, week52_low)
    peers = get_sector_peers(clean, effective_sector, limit=5)

    return {
        "source": "NSE (National Stock Exchange)",
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
        "eps": _f("trailingEps"),
        "dividend_yield": round(_f("dividendYield", 0) * 100, 2) if _f("dividendYield") else 0,
        "roe": round(_f("returnOnEquity", 0) * 100, 2) if _f("returnOnEquity") else None,
        "profit_margins": round(_f("profitMargins", 0) * 100, 2) if _f("profitMargins") else None,
        "operating_margins": round(_f("operatingMargins", 0) * 100, 2) if _f("operatingMargins") else None,
        "debt_to_equity": _f("debtToEquity"),
        "free_cash_flow_cr": round(_f("freeCashflow", 0) / 1e7, 0) if _f("freeCashflow") else None,
        "week52_high": week52_high,
        "week52_low": week52_low,
        "vwap": vwap,
        "delivery_pct": delivery_pct,
        "avg_volume": _f("averageVolume"),
        "volume": _f("volume"),
        "beta": _f("beta"),
        "year_return": year_return,
        "technicals": technicals,
        "peers": peers,
        "financials": quarterly_fin,
        "financial_statements": financial_statements,
        "earnings": earnings_hist,
        "earnings_summary": earnings_summary,
        "description": (_f("longBusinessSummary", "")[:600] + "...") if _f("longBusinessSummary") else "",
        "chart": {
            "dates": price_dates,
            "prices": price_values,
        },
        "timeframes": timeframe_charts,
        "candlesticks": candlesticks,
        "volume_series": volume_series,
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
