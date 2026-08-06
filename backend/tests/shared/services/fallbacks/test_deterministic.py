"""Unit tests for shared/services/fallbacks/deterministic.py and factory."""

from shared.services.fallbacks.deterministic import DeterministicFallback
from shared.services.fallbacks.factory import get_fallback_engine


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
