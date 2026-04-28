"""
logic_adapter.py
Thin adapter that makes logic.py usable without Streamlit.
Drop your original logic.py next to this file — do NOT modify it.
We monkey-patch st.cache_data before importing so nothing breaks.
"""

import sys
import types

# ── Stub out streamlit so logic.py can be imported in a FastAPI context ──
_st_stub = types.ModuleType("streamlit")

def _passthrough(fn=None, **kwargs):
    """Replacement for @st.cache_data — just returns the function unchanged."""
    if fn is not None:
        return fn
    def decorator(f):
        return f
    return decorator

_st_stub.cache_data = _passthrough
_st_stub.session_state = {}
sys.modules.setdefault("streamlit", _st_stub)

# Now import logic.py — all @st.cache_data decorators are no-ops
from logic import (                          # noqa: E402  (import after stub)
    # Constants
    BENCHMARKS,
    PERIOD_MAP,
    CATEGORY_COLORS,
    FUND_BENCH_BY_CAP,
    FUND_BENCH_BY_CAT,
    RISK_TIERS,
    MAX_DD_ESTIMATE,
    SECTOR_COLORS,
    EXP_RATIOS,
    GOAL_TIMELINE,
    # Helpers
    fmt_inr,
    parse_cas,
    fetch_benchmark,
    compute_xirr,
    compute_benchmark_xirr,
    compute_period_comparison,
    compute_rolling_returns,
    estimate_expense_drag,
    elss_lock_in_analysis,
    compute_portfolio_score,
    sip_consistency_score,
    stepup_sip_projection,
    calculate_redemption_impact,
    get_sector_profile,
    compute_fund_overlap,
    # Chart helpers (Plotly figures — serialised to JSON for the API)
    make_area_chart,
    make_donut,
    make_bar_chart,
    make_waterfall,
    make_gauge,
)

__all__ = [
    "BENCHMARKS", "PERIOD_MAP", "CATEGORY_COLORS",
    "FUND_BENCH_BY_CAP", "FUND_BENCH_BY_CAT",
    "RISK_TIERS", "MAX_DD_ESTIMATE", "SECTOR_COLORS",
    "EXP_RATIOS", "GOAL_TIMELINE",
    "fmt_inr", "parse_cas", "fetch_benchmark",
    "compute_xirr", "compute_benchmark_xirr",
    "compute_period_comparison", "compute_rolling_returns",
    "estimate_expense_drag", "elss_lock_in_analysis",
    "compute_portfolio_score", "sip_consistency_score",
    "stepup_sip_projection",
    "calculate_redemption_impact", "get_sector_profile", "compute_fund_overlap",
    "make_area_chart", "make_donut", "make_bar_chart",
    "make_waterfall", "make_gauge",
]
