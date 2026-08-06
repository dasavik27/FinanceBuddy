"""Mutual fund Portfolio model."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds.models import Portfolio


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



def test_portfolio_summary_bad_nav_date():
    from domains.mutual_funds.models import Portfolio

    df_h = pd.DataFrame([{"Fund": "F", "Market Value": 100.0, "Invested": 90.0, "NAV Date": "not-a-date"}])
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())
    summary = p.get_summary()
    assert summary["nav_date"] == "not-a-date"

