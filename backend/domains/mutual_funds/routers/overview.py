"""
routers/tabs/overview.py

Institutional Cockpit Overview & Allocation Analytics
=====================================================
Consolidated REST gateway driving the primary AlphaTrack Pro dashboard interface.
Executes multi-threaded historical performance curve synthesis and asset allocation roll-ups.
"""

from fastapi import APIRouter
from core.sessions import get_session
from core.config import BENCHMARKS, PERIOD_MAP
from services.market_indices import fetch_benchmark_series
from core.finance import compute_period_comparison

router = APIRouter()

@router.get("/{session_id}/summary")
def get_summary(session_id: str, benchmark: str = "Nifty 50"):
    """
    Retrieves the high-level executive summary of the portfolio.
    Computes total invested capital, current market value, and overarching XIRR.
    """
    portfolio = get_session(session_id)
    return portfolio.get_summary(benchmark)

@router.get("/{session_id}/overview")
def get_overview(session_id: str, period: str = "1Y", benchmark: str = "Nifty 50", refresh: bool = False):
    """
    Generates the primary time-series chart data for the Overview dashboard.
    Dynamically splices historical portfolio cashflows against the selected benchmark.
    """
    portfolio = get_session(session_id)
    df_t = portfolio.df_t
    df_h = portfolio.df_h
    total_val = portfolio.total_value
    perf_days = PERIOD_MAP.get(period, 365)
    
    ticker = BENCHMARKS.get(benchmark, benchmark)
    bench_data = fetch_benchmark_series(ticker, 1825, refresh=refresh)
    
    comp = compute_period_comparison(df_t, df_h, total_val, bench_data, perf_days)
    return {
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

@router.get("/{session_id}/benchmark-overlay")
def get_benchmark_overlay(session_id: str, period: str = "1Y", benchmarks: str = "Nifty 50,S&P 500,Gold", refresh: bool = False):
    """
    Multi-benchmark interactive chart overlay.
    Returns synchronized normalized series (base 100) for all requested benchmarks.
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
    default_bm = BENCHMARKS.get(bm_list[0] if bm_list else "Nifty 50", bm_list[0] if bm_list else "^NSEI")
    default_bench_data = fetch_benchmark_series(default_bm, 1825, refresh=refresh)
    comp = compute_period_comparison(df_t, df_h, total_val, default_bench_data, perf_days)
    
    result["dates"] = comp.get("dates", [])
    result["series"]["Portfolio"] = comp.get("portfolio", [])
    
    if not bm_list or not result["dates"]:
        return result
        
    start_val = result["series"]["Portfolio"][0] if result["series"]["Portfolio"] else 100.0

    # 2. Fetch and synchronize each requested benchmark
    for bm_name in bm_list:
        ticker = BENCHMARKS.get(bm_name, bm_name)
        if not ticker: continue
        
        bench_data = fetch_benchmark_series(ticker, 1825, refresh=refresh)
        bm_comp = compute_period_comparison(df_t, df_h, total_val, bench_data, perf_days)
        
        dates = bm_comp.get("dates", [])
        values = bm_comp.get("benchmark", [])
        
        if values and values[0] > 0:
            scale = start_val / values[0]
            values = [round(v * scale, 2) for v in values]
            
        if len(dates) > len(result["dates"]):
            result["dates"] = dates

        result["series"][bm_name] = values

    return result

@router.get("/{session_id}/allocation")
def get_allocation(session_id: str):
    portfolio = get_session(session_id)
    return portfolio.get_allocation_data()
