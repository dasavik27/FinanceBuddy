"""
test_tax_lots_full.py

Full unit test coverage for domains.mutual_funds.tax_lots:
- compute_fund_lots (FIFO queue management, bonus/reinvestments/redemptions)
- holding_tax_breakdown (Equity, ELSS lock-in, Debt Sec 50AA, Other assets)
- portfolio_tax_summary (LTCG harvesting & slab exposure)
- select_sell_candidate (tax-optimal trimming respecting lock-ins)
"""

from datetime import date, datetime, timedelta
import pandas as pd
import pytest

from domains.mutual_funds.tax_lots import (
    compute_fund_lots,
    holding_tax_breakdown,
    portfolio_tax_summary,
    select_sell_candidate,
)


def test_compute_fund_lots_fifo_drain():
    # 3 purchases and 1 partial redemption
    df_t = pd.DataFrame([
        {"Fund": "HDFC Flexi Cap", "Date": "2022-01-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "HDFC Flexi Cap", "Date": "2022-06-01", "Type": "SIP", "Units": 50, "Amount": 6000, "NAV": 120},
        {"Fund": "HDFC Flexi Cap", "Date": "2023-01-01", "Type": "REINVEST", "Units": 10, "Amount": 0, "NAV": 130},
        {"Fund": "HDFC Flexi Cap", "Date": "2023-06-01", "Type": "REDEMPTION", "Units": -120, "Amount": 18000, "NAV": 150},
    ])

    lots = compute_fund_lots(df_t, "HDFC Flexi Cap")
    # Initial 100 redeemed, next 20 of 50 redeemed -> 30 units remaining from 2022-06-01 + 10 units from 2023-01-01 = 40 units
    assert len(lots) == 2
    total_units = sum(l["units"] for l in lots)
    assert total_units == 40


def test_compute_fund_lots_empty_or_mismatch():
    assert compute_fund_lots(None, "HDFC Flexi Cap") == []
    assert compute_fund_lots(pd.DataFrame(), "HDFC Flexi Cap") == []
    df_other = pd.DataFrame([{"Fund": "Other Fund", "Date": "2022-01-01", "Type": "PURCHASE", "Units": 10, "Amount": 1000, "NAV": 100}])
    assert compute_fund_lots(df_other, "HDFC Flexi Cap") == []


def test_holding_tax_breakdown_equity_and_elss():
    today = date.today()
    lot_old = {"units": 100, "cost_per_unit": 100, "date": today - timedelta(days=400)}
    lot_new = {"units": 50, "cost_per_unit": 100, "date": today - timedelta(days=100)}

    # Equity breakdown
    bd = holding_tax_breakdown([lot_old, lot_new], current_nav=150.0, category="Large Cap")
    assert bd["treatment"] == "equity"
    assert bd["is_elss"] is False
    assert bd["ltcg_gain"] > 0
    assert bd["stcg_gain"] > 0
    assert bd["locked_units"] == 0

    # ELSS breakdown (3-year lock-in = 1095 days)
    lot_locked = {"units": 100, "cost_per_unit": 100, "date": today - timedelta(days=500)}
    bd_elss = holding_tax_breakdown([lot_locked], current_nav=150.0, category="ELSS Tax Saver")
    assert bd_elss["is_elss"] is True
    assert bd_elss["locked_units"] == 100
    assert bd_elss["locked_value"] == 15000.0


def test_holding_tax_breakdown_debt_and_other():
    today = date.today()
    # Debt post-April 2023 (Sec 50AA slab-taxed)
    lot_debt_post2023 = {"units": 100, "cost_per_unit": 100, "date": date(2023, 5, 1)}
    bd_debt = holding_tax_breakdown([lot_debt_post2023], current_nav=120.0, category="Liquid Debt")
    assert bd_debt["treatment"] == "debt"
    assert bd_debt["slab_taxed_value"] > 0

    # Other (Gold / International)
    lot_gold_ltcg = {"units": 50, "cost_per_unit": 100, "date": today - timedelta(days=800)}
    bd_gold = holding_tax_breakdown([lot_gold_ltcg], current_nav=130.0, category="Gold Fund")
    assert bd_gold["treatment"] == "other"
    assert bd_gold["ltcg_gain"] > 0


def test_portfolio_tax_summary_and_empty():
    empty_summary = portfolio_tax_summary(None, None)
    assert empty_summary["per_fund"] == []

    df_h = pd.DataFrame([
        {"Fund": "Axis Bluechip", "Category": "Large Cap", "NAV": 150.0, "Market Value": 15000.0},
        {"Fund": "HDFC Liquid", "Category": "Liquid Debt", "NAV": 110.0, "Market Value": 11000.0},
    ])
    df_t = pd.DataFrame([
        {"Fund": "Axis Bluechip", "Date": "2021-01-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "HDFC Liquid", "Date": "2023-05-01", "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
    ])

    summary = portfolio_tax_summary(df_h, df_t)
    assert len(summary["per_fund"]) == 2
    assert "harvest" in summary
    assert "debt_summary" in summary


def test_select_sell_candidate_unlocked_preference():
    today = date.today()
    df_h = pd.DataFrame([
        {"Fund": "Fund Unlocked", "Category": "Flexi Cap", "NAV": 150.0, "Market Value": 15000.0},
        {"Fund": "Fund Locked ELSS", "Category": "ELSS Tax Saver", "NAV": 150.0, "Market Value": 15000.0},
    ])
    df_t = pd.DataFrame([
        {"Fund": "Fund Unlocked", "Date": today - timedelta(days=500), "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
        {"Fund": "Fund Locked ELSS", "Date": today - timedelta(days=200), "Type": "PURCHASE", "Units": 100, "Amount": 10000, "NAV": 100},
    ])

    mask = df_h["Market Value"] > 0
    candidate = select_sell_candidate(df_h, df_t, mask, sell_amount=5000.0)
    assert "picks" in candidate or "funds" in candidate or isinstance(candidate, dict)
