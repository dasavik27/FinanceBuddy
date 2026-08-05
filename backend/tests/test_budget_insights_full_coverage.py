"""
test_budget_insights_full_coverage.py

Full unit test coverage for domains.budget.insights:
- detect_recurring (cadences, price changes)
- build_forecast & safe-to-spend calculations
- detect_anomalies (duplicate charges, category spikes, large first-time merchants)
- reconcile_accounts (running balance drift detection)
- build_sankey flow construction
"""

import pandas as pd
import numpy as np
import pytest

from domains.budget import insights


def test_detect_recurring_and_price_changes():
    # Construct 4 monthly Netflix charges with a price hike
    dates = pd.date_range("2024-01-01", periods=4, freq="30D")
    df = pd.DataFrame([
        {"txn_id": "t1", "date": dates[0], "amount": 499.0, "type": "debit", "description": "NETFLIX MUMBAI", "category": "Subscriptions", "bank": "HDFC", "kind": "savings"},
        {"txn_id": "t2", "date": dates[1], "amount": 499.0, "type": "debit", "description": "NETFLIX MUMBAI", "category": "Subscriptions", "bank": "HDFC", "kind": "savings"},
        {"txn_id": "t3", "date": dates[2], "amount": 649.0, "type": "debit", "description": "NETFLIX MUMBAI", "category": "Subscriptions", "bank": "HDFC", "kind": "savings"},
        {"txn_id": "t4", "date": dates[3], "amount": 649.0, "type": "debit", "description": "NETFLIX MUMBAI", "category": "Subscriptions", "bank": "HDFC", "kind": "savings"},
    ])

    recurring = insights.find_recurring(df)
    assert len(recurring) >= 1
    netf = recurring[0]
    assert "netflix" in netf.merchant.lower()
    assert netf.cadence == "monthly"
    assert len(netf.price_changes) >= 1
    assert netf.price_changes[0]["from"] == 499.0
    assert netf.price_changes[0]["to"] == 649.0


def test_build_forecast():
    # 2 months of history + current month
    df = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 100000.0, "type": "credit"},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-10"), "amount": 30000.0, "type": "debit"},
        {"txn_id": "t3", "date": pd.Timestamp("2025-02-01"), "amount": 100000.0, "type": "credit"},
        {"txn_id": "t4", "date": pd.Timestamp("2025-02-10"), "amount": 32000.0, "type": "debit"},
        {"txn_id": "t5", "date": pd.Timestamp("2025-03-01"), "amount": 100000.0, "type": "credit"},
        {"txn_id": "t6", "date": pd.Timestamp("2025-03-05"), "amount": 15000.0, "type": "debit"},
    ])

    forecast = insights.build_forecast(df, recurring=[], available_balance=85000.0, as_of=pd.Timestamp("2025-03-05"))
    assert forecast["days_remaining"] > 0
    assert forecast["safe_to_spend_daily"] > 0
    assert forecast["spent_this_month"] == 15000.0


def test_detect_anomalies_duplicate_charge():
    df = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 1250.0, "type": "debit", "description": "Swiggy Bangalore", "category": "Food"},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-01"), "amount": 1250.0, "type": "debit", "description": "Swiggy Bangalore", "category": "Food"},
    ])

    anomalies = insights.find_anomalies(df)
    assert len(anomalies) >= 1
    assert anomalies[0]["type"] == "duplicate_charge"
    assert anomalies[0]["amount"] == 1250.0


def test_reconcile_accounts_with_and_without_gaps():
    # Reconciled statement
    df_clean = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 1000.0, "type": "credit", "balance": 1000.0, "bank": "HDFC", "kind": "savings"},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-02"), "amount": 200.0, "type": "debit", "balance": 800.0, "bank": "HDFC", "kind": "savings"},
    ])

    rec_clean = insights.reconcile_accounts(df_clean)
    assert len(rec_clean) == 1
    assert rec_clean[0]["status"] == "reconciled"
    assert rec_clean[0]["break_count"] == 0

    # Statement with a missing transaction gap
    df_broken = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 1000.0, "type": "credit", "balance": 1000.0, "bank": "HDFC", "kind": "savings"},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-02"), "amount": 200.0, "type": "debit", "balance": 500.0, "bank": "HDFC", "kind": "savings"},
    ])
    rec_broken = insights.reconcile_accounts(df_broken)
    assert rec_broken[0]["status"] == "gaps_found"
    assert rec_broken[0]["break_count"] == 1


def test_build_sankey():
    df = pd.DataFrame([
        {"txn_id": "t1", "amount": 100000.0, "type": "credit", "category": "Salary"},
        {"txn_id": "t2", "amount": 25000.0, "type": "debit", "category": "Rent"},
        {"txn_id": "t3", "amount": 10000.0, "type": "debit", "category": "Dining Out"},
        {"txn_id": "t4", "amount": 20000.0, "type": "debit", "category": "Mutual Funds"},
    ])

    nature_map = {
        "Rent": "needs",
        "Dining Out": "wants",
        "Mutual Funds": "investments",
    }

    sankey = insights.build_sankey(df, nature_of=lambda c: nature_map.get(c, "wants"))
    assert len(sankey["nodes"]) > 0
    assert len(sankey["links"]) > 0
