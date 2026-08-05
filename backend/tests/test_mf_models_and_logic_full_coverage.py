"""
test_mf_models_and_logic_full_coverage.py

Comprehensive unit tests for:
- domains/mutual_funds/logic.py (CategorizationEngine category, cap type, AMC, plan, and brand extraction)
- domains/mutual_funds/models.py (Portfolio initialization, live NAV updates, summary KPIs, expense drag, and asset allocation breakdown)
"""

from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds.logic import CategorizationEngine
from domains.mutual_funds.models import Portfolio


def test_categorization_engine_detect_category():
    ce = CategorizationEngine

    # Priority 1: Raw category / type
    assert ce.detect_category("Fund A", raw_cat="ELSS Tax Saver") == "ELSS"
    assert ce.detect_category("Fund B", raw_cat="Overnight / Liquid Fund") == "Liquid"
    assert ce.detect_category("Fund C", raw_cat="Equity Arbitrage") == "Arbitrage"
    assert ce.detect_category("Fund D", raw_cat="Dividend Yield Fund") == "Dividend Yield"
    assert ce.detect_category("Fund E", raw_cat="Thematic / Sectoral") == "Thematic"
    assert ce.detect_category("Fund F", raw_cat="Hybrid Balanced Advantage") == "Hybrid"
    assert ce.detect_category("Fund G", raw_type="DEBT", raw_cat="Income Fund") == "Debt"
    assert ce.detect_category("Fund H", raw_cat="Index ETF") == "Index"
    assert ce.detect_category("Fund I", raw_cat="Retirement Benefit") == "Solution Oriented"

    # Priority 2: Keyword Heuristics
    assert ce.detect_category("Nippon Gold ETF") == "Commodities"
    assert ce.detect_category("Motilal Nasdaq 100 FoF") == "International"
    assert ce.detect_category("Axis Tax Saver Fund") == "ELSS"
    assert ce.detect_category("Kotak Arbitrage Fund") == "Arbitrage"
    assert ce.detect_category("SBI Liquid Fund") == "Liquid"
    assert ce.detect_category("ICICI Balanced Advantage") == "Hybrid"
    assert ce.detect_category("UTI Nifty 50 Index Fund") == "Index"

    # Priority 3: Debt Keywords & Banking
    assert ce.detect_category("SBI Banking & PSU Debt Fund") == "Debt"
    assert ce.detect_category("HDFC Corporate Bond Fund") == "Debt"
    assert ce.detect_category("ICICI Banking Financial Services") == "Thematic"

    # Raw Category fallback & Default
    assert ce.detect_category("Unknown XYZ", raw_cat="Special Fund") == "Special Fund"
    assert ce.detect_category("Unknown XYZ") == "Equity"


def test_categorization_engine_detect_cap_type():
    ce = CategorizationEngine

    # N/A for Debt/Liquid/Arbitrage
    assert ce.detect_cap_type("Fund A", "Debt") == "N/A"
    assert ce.detect_cap_type("Fund B", "Liquid") == "N/A"
    assert ce.detect_cap_type("Fund C", "Arbitrage") == "N/A"

    # Priority 1: Exact Style/Market Matching
    assert ce.detect_cap_type("US Opportunities", "Equity") == "International"
    assert ce.detect_cap_type("Pharma Healthcare", "Equity") == "Thematic"
    assert ce.detect_cap_type("Dividend Yield", "Equity") == "Dividend Yield"
    assert ce.detect_cap_type("Gold ETF", "Equity") == "Commodity"

    # Priority 2: Raw Category cap matches
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Small Cap Fund") == "Small Cap"
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Large & Mid Cap") == "Large & Mid Cap"
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Mid Cap Fund") == "Mid Cap"
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Flexi Cap Fund") == "Flexi Cap"
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Multi Cap Fund") == "Multi Cap"
    assert ce.detect_cap_type("Fund", "Equity", raw_cat="Large Cap Fund") == "Large Cap"

    # Priority 3: Name Keyword matching
    assert ce.detect_cap_type("HDFC Large and Mid Cap", "Equity") == "Large & Mid Cap"
    assert ce.detect_cap_type("Quant Small Cap Fund", "Equity") == "Small Cap"
    assert ce.detect_cap_type("Motilal Mid Cap Fund", "Equity") == "Mid Cap"
    assert ce.detect_cap_type("Parag Parikh Flexi Cap", "Equity") == "Flexi Cap"
    assert ce.detect_cap_type("Nippon Multi Cap", "Equity") == "Multi Cap"
    assert ce.detect_cap_type("SBI Large Cap", "Equity") == "Large Cap"

    # Priority 4: Style labels
    assert ce.detect_cap_type("Templeton Value", "Equity") == "Value"
    assert ce.detect_cap_type("SBI Contra Fund", "Equity") == "Contra"
    assert ce.detect_cap_type("Axis Focused 25", "Equity") == "Focused"

    # Fallbacks
    assert ce.detect_cap_type("Axis ELSS", "ELSS") == "Flexi Cap"
    assert ce.detect_cap_type("Nifty 50 Index", "Index") == "Large Cap"
    assert ce.detect_cap_type("Nifty Midcap 150 Index", "Index") == "Mid Cap"
    assert ce.detect_cap_type("Nifty Smallcap 250 Index", "Index") == "Small Cap"
    assert ce.detect_cap_type("Nifty Next 50 Index", "Index") == "Large Cap"
    assert ce.detect_cap_type("Custom Index", "Index") == "Large Cap"
    assert ce.detect_cap_type("Random Equity", "Equity") == "Large Cap"


def test_categorization_engine_amc_and_plan_and_brand():
    ce = CategorizationEngine

    # AMC
    assert ce.detect_amc("HDFC Top 100", raw_amc="HDFC Mutual Fund") == "HDFC"
    assert ce.detect_amc("Mirae Asset Large Cap") == "Mirae Asset"
    assert ce.detect_amc("Parag Parikh Flexi Cap") == "Parag Parikh"
    assert ce.detect_amc("Some Unknown AMC Fund") == "Other"

    # Plan
    assert ce.detect_plan("HDFC Top 100 Direct Plan Growth") == "Direct"
    assert ce.detect_plan("HDFC Top 100 Regular Plan Growth") == "Regular"
    assert ce.detect_plan("HDFC Top 100 Growth") == "Unknown"

    # AMC Brand extraction
    assert ce.extract_amc_brand("NIPPON INDIA GROWTH FUND") == "NIPPON INDIA"
    assert ce.extract_amc_brand("HDFC TOP 100 FUND") == "HDFC"
    assert ce.extract_amc_brand("CUSTOM FUND") == "CUSTOM"
    assert ce.extract_amc_brand("") == "UNKNOWN"


def test_portfolio_lifecycle_and_live_navs(monkeypatch):
    # 1. Empty portfolio
    empty_p = Portfolio(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert empty_p.total_value == 0.0
    assert empty_p.get_summary() == {}
    assert empty_p.get_allocation_data() == {}
    assert empty_p.compute_expense_drag() == 0.0
    empty_p.update_live_navs()

    # 2. Populated portfolio
    df_h = pd.DataFrame([
        {
            "ISIN": "INF179K01BE2", "Fund": "HDFC Top 100", "Category": "Equity",
            "Units": 100.0, "Invested": 5000.0, "NAV": 60.0, "Market Value": 6000.0,
            "Cap Type": "Large Cap", "Plan": "Direct",
        },
        {
            "ISIN": "INF209K01157", "Fund": "SBI Liquid Fund", "Category": "Liquid",
            "Units": 50.0, "Invested": 5000.0, "NAV": 110.0, "Market Value": 5500.0,
            "Cap Type": "N/A", "Plan": "Direct",
        },
    ])
    df_t = pd.DataFrame([
        {"Date": "2024-01-01", "Fund": "HDFC Top 100", "Type": "PURCHASE", "Units": 100.0, "Amount": 5000.0},
        {"Date": "2024-01-01", "Fund": "SBI Liquid Fund", "Type": "PURCHASE", "Units": 50.0, "Amount": 5000.0},
    ])
    df_s = pd.DataFrame()

    p = Portfolio(df_h, df_t, df_s)
    assert p.total_value == 11500.0
    assert p.total_invested == 10000.0
    assert "CAS NAV" in p.df_h.columns

    # Live NAV Mocking
    live_map = {"INF179K01BE2": 65.0, "INF209K01157": 105.0}  # Liquid NAV regressed (105 < 110)
    date_map = {"INF179K01BE2": "05-Aug-2026", "INF209K01157": "invalid-date"}
    monkeypatch.setattr(
        "shared.services.market_data.fetch_live_navs_with_date",
        lambda refresh=False: (live_map, date_map),
    )
    monkeypatch.setattr(
        "shared.services.market_data.resolve_scheme_code_from_isin",
        lambda isin: "123456",
    )
    monkeypatch.setattr(
        "shared.services.market_data.fetch_fund_ter",
        lambda code, plan: 0.75,
    )

    p.update_live_navs(refresh=True)

    # HDFC updated to 65 -> MV 6500
    # SBI Liquid prevented from regression: stays 110 -> MV 5500
    assert p.total_value == 12000.0
    assert "Weight%" in p.df_h.columns
    assert p.df_h.loc[p.df_h["ISIN"] == "INF179K01BE2", "NAV Date"].values[0] == "2026-08-05"


def test_portfolio_summary_and_allocation(monkeypatch):
    df_h = pd.DataFrame([
        {
            "ISIN": "INF179K01BE2", "Fund": "HDFC Top 100", "Category": "Equity",
            "Units": 100.0, "Invested": 5000.0, "NAV": 65.0, "Market Value": 6500.0,
            "Cap Type": "Large Cap", "TER": 0.80, "NAV Date": "2026-08-05",
        },
        {
            "ISIN": "INF209K01157", "Fund": "SBI Liquid", "Category": "Liquid",
            "Units": 50.0, "Invested": 5000.0, "NAV": 110.0, "Market Value": 5500.0,
            "Cap Type": "N/A", "TER": 0.20, "NAV Date": "2026-08-05",
        },
    ])
    df_t = pd.DataFrame([
        {"Date": "2024-01-01", "Fund": "HDFC Top 100", "Type": "PURCHASE", "Units": 100.0, "Amount": 5000.0},
    ])
    df_s = pd.DataFrame()

    p = Portfolio(df_h, df_t, df_s)

    # Mock market index and XIRR
    monkeypatch.setattr(
        "domains.mutual_funds.models.fetch_benchmark_series",
        lambda ticker, days: pd.DataFrame({"Date": ["2024-01-01"], "NAV": [100.0]}),
    )
    monkeypatch.setattr("domains.mutual_funds.models.compute_xirr", lambda df, mv: 15.5)
    monkeypatch.setattr("domains.mutual_funds.models.compute_benchmark_xirr", lambda df, b: (12.0, None))
    monkeypatch.setattr("domains.mutual_funds.models.is_absolute_return", lambda df: False)

    summary = p.get_summary()
    assert summary["total_value"] == 12000.0
    assert summary["portfolio_xirr"] == 15.5
    assert summary["bench_xirr"] == 12.0
    assert summary["alpha"] == 3.5
    assert summary["is_absolute"] is False
    assert "Aug" in summary["nav_date"]

    # Expense drag calculation: 6500 * 0.008 + 5500 * 0.002 = 52 + 11 = 63
    expense = p.compute_expense_drag()
    assert round(expense, 2) == 63.0

    # Allocation data
    alloc = p.get_allocation_data()
    assert "broad" in alloc
    assert "by_cap" in alloc
    assert "by_category" in alloc
    # N/A converted to Fixed Income / Other
    cap_labels = [c["label"] for c in alloc["by_cap"]]
    assert "Fixed Income / Other" in cap_labels
