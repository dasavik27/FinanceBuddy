"""
routers/overview.py - Mutual Fund Overview & Allocation Analytics

Caching notes:
- The day-by-day portfolio simulation goes through derived.cached_period_comparison,
  which is content-addressed and single-flighted. See that module for why.
- fetch_benchmark_series caches internally (one full-history entry per ticker, sliced
  on return), so there is no wrapper here. An earlier version added a @memoize on top
  of it, which was both redundant and harmful: memoize returned the cached Series by
  reference, undoing the defensive .copy() that fetch_benchmark_series makes
  specifically to stop callers corrupting the cache.
- Cache-Control headers come from get_cache_headers, which marks anything derived from
  a user's holdings as private/no-store rather than public.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from domains.mutual_funds.sessions import get_session
from shared.config import BENCHMARKS, PERIOD_MAP
from shared.services.market_indices import fetch_benchmark_series
from shared.services.cache import get_cache_headers
from domains.mutual_funds.derived import cached_period_comparison

router = APIRouter()


@router.get("/{session_id}/summary")
def get_summary(session_id: str, benchmark: str = "Nifty 50"):
    """Retrieves the high-level executive summary of the portfolio."""
    portfolio = get_session(session_id)
    summary = portfolio.get_summary(benchmark)
    
    # Add cache headers for browser caching
    headers = get_cache_headers("portfolio_summary")
    return JSONResponse(content=summary, headers=headers)


@router.get("/{session_id}/overview")
def get_overview(
    session_id: str,
    period: str = "1Y",
    benchmark: str = "Nifty 50",
    refresh: bool = False
):
    """Generates the primary time-series chart data for the Overview dashboard."""
    portfolio = get_session(session_id)
    df_t = portfolio.df_t
    df_h = portfolio.df_h
    total_val = portfolio.total_value
    perf_days = PERIOD_MAP.get(period, 365)

    ticker = BENCHMARKS.get(benchmark, benchmark)
    bench_data = fetch_benchmark_series(ticker, 1825, refresh=refresh)

    comp = cached_period_comparison(df_t, df_h, total_val, bench_data, perf_days)
    
    result = {
        "port_pct": comp.get("port_pct", 0.0),
        "bench_pct": comp.get("bench_pct", 0.0),
        "port_value": comp.get("port_value", total_val),
        "bench_value": comp.get("bench_value", 0.0),
        "use_xirr": comp.get("use_xirr", False),
        "benchmark_name": benchmark,
        "period": period,
        "chart": {
            "dates": comp.get("dates", []),
            "portfolio": comp.get("portfolio", []),
            "benchmark": comp.get("benchmark", [])
        }
    }
    
    headers = get_cache_headers("holdings_detail")
    return JSONResponse(content=result, headers=headers)


@router.get("/{session_id}/benchmark-overlay")
def get_benchmark_overlay(
    session_id: str,
    period: str = "1Y",
    benchmarks: str = "Nifty 50,S&P 500,Gold",
    refresh: bool = False
):
    """
    Multi-benchmark interactive chart overlay.
    Returns synchronized normalized series (base 100) for all requested benchmarks.

    Note: the loop below runs one simulation per requested benchmark, even though the
    *portfolio* half of each result is identical - only the benchmark curve differs.
    Splitting compute_period_comparison into a portfolio pass plus a cheap benchmark
    alignment would remove that redundancy entirely; for now the cache absorbs the
    overlap between the default benchmark and the first list entry.
    """
    portfolio = get_session(session_id)
    df_t = portfolio.df_t
    df_h = portfolio.df_h
    total_val = portfolio.total_value
    perf_days = PERIOD_MAP.get(period, 365)
    
    bm_list = [b.strip() for b in benchmarks.split(",") if b.strip()]
    
    result = {
        "dates": [],
        "series": {}
    }
    
    # 1. First compute portfolio base series
    default_bm = BENCHMARKS.get(
        bm_list[0] if bm_list else "Nifty 50",
        bm_list[0] if bm_list else "^NSEI"
    )
    default_bench_data = fetch_benchmark_series(default_bm, 1825, refresh=refresh)
    comp = cached_period_comparison(df_t, df_h, total_val, default_bench_data, perf_days)
    
    result["dates"] = comp.get("dates", [])
    result["series"]["Portfolio"] = comp.get("portfolio", [])
    
    if not bm_list or not result["dates"]:
        # NOT "comparison_data": that type is `public`, and this body carries
        # result["series"]["Portfolio"] - the user's own CAS-derived value series.
        # `public` authorizes a CDN or corporate proxy to store one user's portfolio
        # and serve it to another. Only genuinely user-independent market data may
        # ever use a public type; see the note in shared/services/cache.py.
        headers = get_cache_headers("holdings_detail")
        return JSONResponse(content=result, headers=headers)
        
    start_val = result["series"]["Portfolio"][0] if result["series"]["Portfolio"] else 100.0

    # 2. Fetch and synchronize each requested benchmark (CACHED)
    for bm_name in bm_list:
        ticker = BENCHMARKS.get(bm_name, bm_name)
        if not ticker:
            continue
        
        bench_data = fetch_benchmark_series(ticker, 1825, refresh=refresh)
        bm_comp = cached_period_comparison(df_t, df_h, total_val, bench_data, perf_days)
        
        dates = bm_comp.get("dates", [])
        values = bm_comp.get("benchmark", [])
        
        if values and values[0] > 0:
            scale = start_val / values[0]
            values = [round(v * scale, 2) for v in values]
            
        if len(dates) > len(result["dates"]):
            result["dates"] = dates

        result["series"][bm_name] = values

    headers = get_cache_headers("comparison_data")
    return JSONResponse(content=result, headers=headers)


@router.get("/{session_id}/allocation")
def get_allocation(session_id: str):
    """Asset allocation breakdown by category and market cap."""
    portfolio = get_session(session_id)
    allocation = portfolio.get_allocation_data()
    
    headers = get_cache_headers("holdings_detail")
    return JSONResponse(content=allocation, headers=headers)
