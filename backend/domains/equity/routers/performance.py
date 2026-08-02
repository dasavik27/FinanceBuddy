"""domains/equity/routers/performance.py"""
import logging

import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from domains.equity import sessions as eq_sessions
from shared.config import BENCHMARKS
from shared.services.cache import get_cache_headers
from domains.equity.quotes import fetch_close_history
from shared.services.market_indices import fetch_benchmark_series

logger = logging.getLogger(__name__)
router = APIRouter()

_PERIOD_MAP = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825}

_EMPTY = {"dates": [], "portfolio": [], "benchmark": []}


@router.get("/{session_id}/performance")
def get_performance(
    session_id: str,
    period: str = Query("1Y"),
    benchmark: str = Query("Nifty 50"),
):
    """
    Portfolio value over time against a benchmark.

    The portfolio series is a single vectorized reduction: closes x quantity, summed
    across columns. It used to be a nested `for date in dates: for sym in symbols:`
    loop that indexed `hist[ticker]["Close"].loc[date]` per cell, rebuilding a
    sub-DataFrame every iteration. Measured at ~1.5 ms per cell, that is ~19 s of CPU
    for 1Y x 50 holdings and ~95 s for 5Y x 50 - per request, uncached, on a shared
    vCPU. The reduction below is the same arithmetic in one pass.
    """
    portfolio = eq_sessions.get_session(session_id)
    days = _PERIOD_MAP.get(period.upper(), 365)
    ticker = BENCHMARKS.get(benchmark, "^NSEI")

    df = portfolio.df_holdings
    if df.empty:
        return JSONResponse(content=dict(_EMPTY))

    try:
        # Quantities per symbol. Summed, because a broker export can list the same
        # symbol on two exchanges and the chart wants the combined position.
        qty = (
            pd.to_numeric(df["quantity"], errors="coerce")
            .groupby(df["symbol"].astype(str))
            .sum()
        )
        avg_price = (
            pd.to_numeric(df["avg_price"], errors="coerce")
            .groupby(df["symbol"].astype(str))
            .mean()
        )

        closes = fetch_close_history(qty.index.tolist(), days)
        if closes is None or closes.empty:
            return JSONResponse(content=dict(_EMPTY))

        # Align on the symbols we actually got history for.
        symbols = [s for s in closes.columns if s in qty.index]
        if not symbols:
            return JSONResponse(content=dict(_EMPTY))
        closes = closes[symbols]

        # Carry the last known price across non-trading gaps, then fall back to the
        # holding's average cost for leading NaNs (a stock listed mid-window has no
        # earlier price; its cost basis is the least-wrong stand-in).
        closes = closes.ffill()
        closes = closes.fillna(avg_price.reindex(symbols))

        portfolio_series = closes.mul(qty.reindex(symbols), axis=1).sum(axis=1).round(2)
        portfolio_values = portfolio_series.tolist()
        dates = portfolio_series.index
        date_strs = [d.strftime("%Y-%m-%d") for d in dates]

        bench_values: list[float] = []
        try:
            bench_data = fetch_benchmark_series(ticker, days)
        except Exception as e:
            logger.warning("[equity/performance] benchmark fetch failed: %s", e)
            bench_data = None

        if bench_data is not None and not bench_data.empty and portfolio_values:
            # Trim by index, not Series.last(): `.last("<n>D")` was removed in
            # pandas 3.0 (this repo pins 3.0.2), so the call raised AttributeError
            # into a debug-level except and the benchmark line was permanently empty.
            cutoff = dates[-1] - pd.Timedelta(days=days)
            bench_slice = bench_data[bench_data.index >= cutoff]
            bench_raw = bench_slice.reindex(dates, method="ffill").dropna()
            if not bench_raw.empty and float(bench_raw.iloc[0]) > 0:
                # Rebase the benchmark to the portfolio's opening value so the two
                # lines are comparable in shape rather than in absolute level.
                scale = portfolio_values[0] / float(bench_raw.iloc[0])
                bench_values = [round(float(v) * scale, 2) for v in bench_raw]

        return JSONResponse(
            content={
                "dates": date_strs,
                "portfolio": portfolio_values,
                "benchmark": bench_values,
                "benchmark_name": benchmark,
                "period": period,
                "priced_symbols": len(symbols),
                "total_symbols": int(len(qty)),
            },
            headers=get_cache_headers("holdings_detail"),
        )

    except Exception:
        # logger.exception keeps the traceback server-side. The response carries no
        # exception text: this used to return `"error": str(e)` in a 200 body, which
        # both leaked internals and told the client "success".
        logger.exception("[equity/performance] failed for session %s", session_id)
        return JSONResponse(
            status_code=502,
            content={**_EMPTY, "detail": "Could not build the performance series. Please retry."},
        )
