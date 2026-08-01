"""domains/equity/routers/performance.py"""
import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from domains.equity import sessions as eq_sessions
from shared.services.cache import get_cache_headers
from shared.config import BENCHMARKS
from shared.services.market_indices import fetch_benchmark_series

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_MAP = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825}


@router.get("/{session_id}/performance")
def get_performance(
    session_id: str,
    period: str = Query("1Y"),
    benchmark: str = Query("Nifty 50"),
):
    """
    Portfolio performance vs benchmark over time.
    Uses the portfolio's total_value (mark-to-market) vs a Nifty 50 baseline.
    """
    portfolio = eq_sessions.get_session(session_id)
    days = _PERIOD_MAP.get(period.upper(), 365)

    ticker = BENCHMARKS.get(benchmark, "^NSEI")
    try:
        bench_data = fetch_benchmark_series(ticker, days)
    except Exception as e:
        logger.warning("[equity/performance] benchmark fetch failed: %s", e)
        bench_data = None

    # Build portfolio value series from yfinance historical data for each holding
    try:
        import yfinance as yf
        import pandas as pd

        df = portfolio.df_holdings
        if df.empty:
            return JSONResponse(content={"dates": [], "portfolio": [], "benchmark": []})

        symbols = df["symbol"].tolist()
        quantities = dict(zip(df["symbol"], df["quantity"]))
        avg_prices = dict(zip(df["symbol"], df["avg_price"]))

        tickers = [s + ".NS" for s in symbols]
        hist = yf.download(tickers, period=f"{days}d", interval="1d", auto_adjust=True, progress=False, group_by="ticker")

        if hist.empty:
            return JSONResponse(content={"dates": [], "portfolio": [], "benchmark": []})

        # Build daily portfolio value
        dates = hist.index
        portfolio_values = []
        for date in dates:
            daily_val = 0.0
            for sym in symbols:
                ticker_key = sym + ".NS"
                try:
                    if len(tickers) == 1:
                        price = float(hist["Close"].loc[date])
                    else:
                        price = float(hist[ticker_key]["Close"].loc[date])
                    if pd.isna(price):
                        price = avg_prices.get(sym, 0)
                except Exception:
                    price = avg_prices.get(sym, 0)
                daily_val += price * quantities.get(sym, 0)
            portfolio_values.append(round(daily_val, 2))

        date_strs = [d.strftime("%Y-%m-%d") for d in dates]

        # Normalize benchmark to portfolio start value
        bench_values = []
        if bench_data is not None and not bench_data.empty and portfolio_values:
            try:
                bench_slice = bench_data.last(f"{days}D")
                bench_raw = bench_slice.reindex(dates, method="ffill").dropna()
                if not bench_raw.empty and bench_raw.iloc[0] > 0:
                    scale = portfolio_values[0] / bench_raw.iloc[0]
                    bench_values = [round(float(v) * scale, 2) for v in bench_raw]
            except Exception as e:
                logger.debug("[equity/performance] benchmark alignment: %s", e)

        return JSONResponse(
            content={
                "dates": date_strs,
                "portfolio": portfolio_values,
                "benchmark": bench_values,
                "benchmark_name": benchmark,
                "period": period,
            },
            headers=get_cache_headers("holdings_detail"),
        )

    except Exception as e:
        logger.error("[equity/performance] failed: %s", e)
        return JSONResponse(content={"dates": [], "portfolio": [], "benchmark": [], "error": str(e)})
