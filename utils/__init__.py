"""
FolioIQ Utils Module
Business logic for formatting, parsing, and calculations
"""

from .formatting import fmt_inr, fmt_percentage, fmt_decimal, color_positive_negative
from .parsers import (
    parse_cas,
    detect_category,
    detect_cap_type,
    detect_amc,
    estimate_invested,
)
from .calculations import (
    fetch_benchmark,
    compute_xirr,
    compute_benchmark_xirr,
    compute_period_comparison,
    compute_rolling_returns,
    estimate_expense_drag,
    expense_leakage_20yr,
    elss_lock_in_analysis,
    detect_sector,
    compute_portfolio_score,
)

__all__ = [
    "fmt_inr",
    "fmt_percentage",
    "fmt_decimal",
    "color_positive_negative",
    "parse_cas",
    "detect_category",
    "detect_cap_type",
    "detect_amc",
    "estimate_invested",
    "fetch_benchmark",
    "compute_xirr",
    "compute_benchmark_xirr",
    "compute_period_comparison",
    "compute_rolling_returns",
    "estimate_expense_drag",
    "expense_leakage_20yr",
    "elss_lock_in_analysis",
    "detect_sector",
    "compute_portfolio_score",
]
