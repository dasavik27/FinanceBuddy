"""
routers/tabs/compare.py

Institutional Peer Comparison & Alpha Scoring Matrix
====================================================
Synthesizes real-time dynamic mutual fund peer universes. Conducts multi-point comparative
audits across expense ratio drag, 1Y/3Y/5Y trailing CAGRs, risk-adjusted returns (Sharpe/Sortino),
and head-to-head consistency scoring for institutional peer selection.
"""

from fastapi import APIRouter
from shared.config import (
    BENCHMARKS, PE_ESTIMATES, GOAL_TIMELINE, EXP_RATIO_BANDS,
    FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT
)
from shared.services.market_indices import fetch_benchmark_series
from shared.services.market_data import (
    search_mutual_funds, get_nse_indices, fetch_fund_ter, fetch_nav_series_by_code
)
from domains.mutual_funds.finance import (
    compute_consistency_score, compute_risk_metrics, compute_trailing_returns
)
import pandas as pd
import logging
logger = logging.getLogger(__name__)


router = APIRouter()

@router.get("/list")
def list_benchmarks():
    return {"benchmarks": list(BENCHMARKS.keys())}

@router.get("/search")
def search_ticker(q: str):
    logger.info(f"[REALTIME] Searching for: {q}")
    results = get_nse_indices(q) + search_mutual_funds(q)
    return {"results": results, "peers": results}

@router.get("/history")
def get_history(ticker: str, days: int = 365):
    series = fetch_benchmark_series(ticker, days)
    if series.empty:
        return {"dates": [], "values": []}
    
    norm = (series / series.iloc[0] * 100).round(2)
    return {
        "dates": series.index.strftime("%Y-%m-%d").tolist(),
        "values": norm.tolist(),
        "raw": series.round(2).tolist(),
    }

@router.get("/peers")
def get_category_peers(category: str = "Large Cap"):
    from domains.mutual_funds.tab_common import get_diverse_category_peers
    diverse_peers, fallback_triggered = get_diverse_category_peers(category)

    return {
        "peers": diverse_peers,
        "fallback_triggered": fallback_triggered
    }

@router.get("/metrics")
def get_comparison_metrics(fund: str, vs: str, session_id: str = ""):
    """
    Head-to-head metrics comparison between two funds/indices.
    Scoring: Fund A beats Fund B on specific metric = 1 Win.
    """
    from shared.services.market_data import fetch_nav_series_by_code
    from shared.services.market_indices import fetch_benchmark_series
    from domains.mutual_funds.finance import compute_trailing_returns, compute_risk_metrics, compute_consistency_score

    # Fetch Data
    # 'fund' is always a scheme code
    s1 = fetch_nav_series_by_code(fund, days=1825 + 60)
    
    # 'vs' could be ticker or scheme code
    if vs.isdigit() and len(vs) >= 5:
        s2 = fetch_nav_series_by_code(vs, days=1825 + 60)
    else:
        s2 = fetch_benchmark_series(vs, days=1825 + 60)

    if s1.empty or s2.empty:
        return {"wins": {"A": 0, "B": 0}, "metrics": []}

    # 1. Trailing Returns
    t1 = compute_trailing_returns(s1)
    t2 = compute_trailing_returns(s2)

    # FIX H-6: Both funds should use the same benchmark for symmetric comparison.
    # Using Nifty 50 as the common benchmark for fair alpha/beta/Sharpe.
    nifty = fetch_benchmark_series("^NSEI", 1825 + 60)
    r1 = compute_risk_metrics(s1, nifty, risk_free_rate=6.5)
    r2 = compute_risk_metrics(s2, nifty, risk_free_rate=6.5)

    # 3. Consistency (both funds vs Nifty 50 for fairness)
    c1 = compute_consistency_score(s1, nifty)
    c2 = compute_consistency_score(s2, nifty)
    
    from domains.mutual_funds.tab_common import compare_metric
    metrics = []
    wins_a = 0
    wins_b = 0

    def _add(label, v1, v2, higher_better=True):
        nonlocal wins_a, wins_b
        res = compare_metric(label, v1, v2, higher_better)
        if res["winner"] == "A": wins_a += 1
        elif res["winner"] == "B": wins_b += 1
        metrics.append(res)

    # Population
    _add("1Y Return (%)", t1.get("1Y"), t2.get("1Y"))
    _add("3Y Return (%)", t1.get("3Y"), t2.get("3Y"))
    _add("5Y Return (%)", t1.get("5Y"), t2.get("5Y"))
    _add("Sharpe Ratio", r1.get("sharpe"), r2.get("sharpe"))
    _add("Sortino Ratio", r1.get("sortino"), r2.get("sortino"))
    _add("Jensen's Alpha (%)", r1.get("alpha"), r2.get("alpha"))
    _add("Volatility (%)", r1.get("vol"), r2.get("vol"), higher_better=False)
    _add("Max Drawdown (%)", abs(r1.get("max_dd", 0)), abs(r2.get("max_dd", 0)), higher_better=False)
    _add("Consistency Score", c1, c2)  # FIX H-7: Compute both instead of static 5.0

    return {
        "wins": {"A": wins_a, "B": wins_b},
        "metrics": metrics
    }
