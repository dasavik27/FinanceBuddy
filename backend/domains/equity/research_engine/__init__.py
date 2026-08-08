"""
Equity Research Scan Engine.

Pluggable strategy runners (Minervini Trend Template + VCP first) over daily OHLC.
No MarketSmith / broker execution — research ranking only.
"""

from domains.equity.research_engine.runner import (
    evaluate_symbol,
    list_strategies,
    run_scan,
)

__all__ = ["evaluate_symbol", "list_strategies", "run_scan"]
