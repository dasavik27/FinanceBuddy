"""Mutual fund categorization engine."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds.logic import CategorizationEngine


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

