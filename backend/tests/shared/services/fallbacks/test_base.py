"""Insight fallback strategy base class."""

import pytest

from shared.services.fallbacks.base import InsightFallbackStrategy


class _StubFallback(InsightFallbackStrategy):
    def generate_fallbacks(self, isin, category, fund_name, partial):
        return {"stub": True}


def test_insight_fallback_strategy_concrete():
    fb = _StubFallback()
    assert fb.generate_fallbacks("INF1", "Large Cap", "Fund A", {}) == {"stub": True}

def test_insight_fallback_strategy_is_abstract():
    with pytest.raises(TypeError):
        InsightFallbackStrategy()

