"""
shared/services/returns.py - point-to-point return maths on a price/NAV series.

Why this is not in a domain
---------------------------
This function takes a datetime-indexed pd.Series of prices and returns trailing
performance. Nothing about it is fund-specific - it works identically on a mutual-fund
NAV series, an index level series, or a stock's close price.

It lived in domains/mutual_funds/finance.py, and shared/services/market_indices.py
imported it from there to compute benchmark returns:

    from domains.mutual_funds.finance import compute_trailing_returns

That is a shared -> domain import, and because domains/equity/routers/performance.py
uses market_indices, it meant the Equity domain transitively executed Mutual Funds code
to render its own performance tab. Moving the function down here keeps exactly one
implementation - the numbers a fund and its benchmark are compared on must come from
the same code, or the comparison is meaningless - while removing the inverted
dependency.

domains/mutual_funds/finance.py re-exports it under its original name, so the five
call sites in that domain are unchanged.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: Standard industry horizons. Calendar offsets rather than fixed day counts, so "1Y"
#: means the same calendar date last year regardless of leap years.
_PERIODS = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
    "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
}

PERIOD_LABELS = tuple(_PERIODS)


def compute_trailing_returns(nav_series: pd.Series) -> Dict[str, Optional[float]]:
    """
    Compute point-to-point trailing returns for standard periods.
    Returns <1Y as simple return, >=1Y as annualised CAGR.

    Returns
    -------
    Dict keyed by period label: {"1M": 4.2, "3M": 8.1, "6M": 12.3,
                                  "1Y": 14.5, "3Y": 19.2, "5Y": 22.1}
    None if insufficient history for that period.
    """
    if nav_series is None or nav_series.empty:
        return {p: None for p in PERIOD_LABELS}

    nav_sorted = nav_series.sort_index().dropna()
    if nav_sorted.empty:
        return {p: None for p in PERIOD_LABELS}

    end_date   = nav_sorted.index[-1]
    end_nav    = float(nav_sorted.iloc[-1])

    result   = {}
    _start_navs = {}  # For cross-period sanity check

    for label, offset in _PERIODS.items():
        target_date = end_date - offset
        candidates  = nav_sorted[nav_sorted.index <= target_date]

        if candidates.empty:
            result[label] = None
            continue

        start_date = candidates.index[-1]
        start_nav  = float(candidates.iloc[-1])
        if start_nav <= 0:
            result[label] = None
            continue

        _start_navs[label] = (start_date, start_nav)
        days_actual = (end_date - start_date).days
        years = days_actual / 365.25
        if years < 0.99:  # Simple return for < 1Y
            ret = (end_nav / start_nav - 1) * 100
        else:             # CAGR for >= 1Y
            ret = ((end_nav / start_nav) ** (1.0 / years) - 1) * 100

        result[label] = round(ret, 2)

    # ── Sanity Check: Cross-period NAV proximity (catches data alignment bugs) ──
    # If 3Y and 5Y starting NAVs are within 2% of each other, the identical
    # returns are a data issue (fund NAV flat in years 4-5) — worth logging.
    if "3Y" in _start_navs and "5Y" in _start_navs:
        nav_3y = _start_navs["3Y"][1]
        nav_5y = _start_navs["5Y"][1]
        if nav_5y > 0:
            pct_diff = abs(nav_3y - nav_5y) / nav_5y * 100
            if pct_diff < 2.0:  # Less than 2% difference
                logger.warning(f"[TRAILING RETURNS WARN] 3Y ({_start_navs['3Y'][0].date()} NAV={nav_3y:.2f}) and "
                      f"5Y ({_start_navs['5Y'][0].date()} NAV={nav_5y:.2f}) start NAVs differ by only {pct_diff:.2f}%. "
                      f"Returns 3Y={result.get('3Y')}% 5Y={result.get('5Y')}% — verify NAV data availability.")

    return result
