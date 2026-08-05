"""
test_fallbacks_and_indices_full.py

Comprehensive tests for:
- shared.services.fallbacks (Deterministic fallback engine & factory)
- shared.services.market_indices (live summary caching, index series fetching & fallback cascade)
"""

import pandas as pd
import pytest
from unittest.mock import MagicMock

from shared.services.fallbacks.deterministic import DeterministicFallback
from shared.services.fallbacks.factory import get_fallback_engine
from shared.services import market_indices
from shared.services.cache import MARKET_CACHE


def test_deterministic_fallback_repeatability():
    engine = DeterministicFallback()
    isin = "INF179K01BE2"
    fund_name = "HDFC Top 100 Fund Direct Growth"
    category = "Large Cap"

    res1 = engine.generate_fallbacks(isin, category, fund_name, {})
    res2 = engine.generate_fallbacks(isin, category, fund_name, {})

    assert res1["aum"] == res2["aum"]
    assert res1["risk"] == res2["risk"]
    assert res1["exit_load"] == res2["exit_load"]
    assert res1["expense_ratio"] == res2["expense_ratio"]
    assert res1["expense_ratio_fallback"] is True


def test_deterministic_fallback_debt_heuristics():
    engine = DeterministicFallback()
    isin = "INF179K01DE9"
    fund_name = "HDFC Liquid Fund Direct Plan"
    category = "Liquid Debt Fund"

    res = engine.generate_fallbacks(isin, category, fund_name, {})
    assert res["risk"] in ("LOW", "MODERATE")
    assert res["exit_load"] == "Nil"
    # Debt fund expense ratio base is typically lower
    assert res["expense_ratio"] <= 0.60


def test_deterministic_fallback_small_cap_risk():
    engine = DeterministicFallback()
    isin = "INF179K01SC1"
    fund_name = "Nippon India Small Cap Fund"
    category = "Small Cap Fund"

    res = engine.generate_fallbacks(isin, category, fund_name, {})
    assert res["risk"] == "VERY HIGH"


def test_deterministic_fallback_regular_markup():
    engine = DeterministicFallback()
    isin = "INF179K01REG"
    fund_direct = "Axis Bluechip Fund Direct Growth"
    fund_reg = "Axis Bluechip Fund Regular Growth"
    category = "Flexi Cap"

    res_dir = engine.generate_fallbacks(isin, category, fund_direct, {})
    res_reg = engine.generate_fallbacks(isin, category, fund_reg, {})

    assert res_reg["expense_ratio"] > res_dir["expense_ratio"]


def test_fallback_factory_resolution():
    engine = get_fallback_engine()
    assert isinstance(engine, DeterministicFallback)


def test_clear_benchmark_cache():
    MARKET_CACHE.set("bench_full|TEST", "dummy", ttl=60)
    hit, val = MARKET_CACHE.get("bench_full|TEST")
    assert hit is True and val == "dummy"
    market_indices.clear_benchmark_cache()
    hit, val = MARKET_CACHE.get("bench_full|TEST")
    assert hit is False


def test_fetch_live_market_summary_fallback(monkeypatch):
    """When Yahoo finance fails or fast_info errors, returns safe default summary."""
    market_indices.clear_benchmark_cache()
    summary = market_indices.fetch_live_market_summary()
    assert "nifty" in summary
    assert "price" in summary["nifty"]
    assert "change" in summary["nifty"]
