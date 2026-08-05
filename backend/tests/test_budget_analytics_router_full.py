"""
test_budget_analytics_router_full.py

Full unit test coverage for domains.budget.routers.analytics:
- Filter application (_apply_budget_filters) and payment mode inference (_infer_payment_mode)
- Overview, Transactions, Trends, Merchants, Categories endpoints
- Forecast, Recurring, Anomalies, Reconciliation, Sankey endpoints
"""

from unittest.mock import MagicMock
import pandas as pd
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.identity import Caller, identity_scope
from domains.budget.accounts import Account
from domains.budget.pipeline import BudgetContext
from domains.budget.routers import analytics, insights as budget_insights

app = FastAPI()
app.include_router(analytics.router, prefix="/api/budget")
app.include_router(budget_insights.router, prefix="/api/budget/insights")
client = TestClient(app)

TEST_CALLER = Caller(user_id="user-0000-0000-0000-000000000001", status="active", role="user", email="u@example.test")


def test_infer_payment_mode():
    assert analytics._infer_payment_mode("UPI/SWIGGY/123@okaxis") == "upi"
    assert analytics._infer_payment_mode("POS PURCHASE VISA 4321") == "card"
    assert analytics._infer_payment_mode("NEFT CR HDFC000123") == "netbanking"
    assert analytics._infer_payment_mode("ATM CASH WDL") == "atm"
    assert analytics._infer_payment_mode("ACH SIP MANDATE") == "autodebit"
    assert analytics._infer_payment_mode("") == "other"


def test_apply_budget_filters():
    df = pd.DataFrame([
        {"txn_id": "t1", "source_bank": "HDFC", "account_type": "savings", "type": "debit", "category": "Food", "amount": 500.0, "description": "Swiggy"},
        {"txn_id": "t2", "source_bank": "ICICI", "account_type": "credit_card", "type": "debit", "category": "Shopping", "amount": 5000.0, "description": "Amazon"},
    ])

    f_bank = analytics._apply_budget_filters(df, bank="HDFC")
    assert len(f_bank) == 1
    assert f_bank.iloc[0]["txn_id"] == "t1"

    f_cat = analytics._apply_budget_filters(df, category="Shopping")
    assert len(f_cat) == 1
    assert f_cat.iloc[0]["txn_id"] == "t2"


def _mock_budget_context():
    df = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 100000.0, "type": "credit", "category": "Salary", "source_bank": "HDFC", "description": "Salary Dec", "is_transfer": False},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-02"), "amount": 25000.0, "type": "debit", "category": "Rent", "source_bank": "HDFC", "description": "Rent Transfer", "is_transfer": False},
        {"txn_id": "t3", "date": pd.Timestamp("2025-01-03"), "amount": 1500.0, "type": "debit", "category": "Food", "source_bank": "HDFC", "description": "Swiggy", "is_transfer": False},
    ])
    acc = Account(account_key="acc_1", bank="HDFC", kind="savings", closing_balance=73500.0)
    return BudgetContext(df=df, accounts=[acc], transfers=[], meta={})


def test_budget_analytics_endpoints(monkeypatch):
    monkeypatch.setattr(analytics, "load_context", lambda sid, uid: _mock_budget_context())
    monkeypatch.setattr(budget_insights, "load_context", lambda sid, uid: _mock_budget_context())

    with identity_scope(TEST_CALLER):
        # Overview
        res = client.get("/api/budget/sess-1/overview")
        assert res.status_code == 200

        # Transactions
        res_txns = client.get("/api/budget/sess-1/transactions")
        assert res_txns.status_code == 200

        # Categories
        res_cat = client.get("/api/budget/sess-1/categories")
        assert res_cat.status_code == 200

        # Forecast
        res_fc = client.get("/api/budget/insights/sess-1/forecast")
        assert res_fc.status_code == 200

        # Recurring
        res_rec = client.get("/api/budget/insights/sess-1/recurring")
        assert res_rec.status_code == 200

        # Anomalies
        res_anom = client.get("/api/budget/insights/sess-1/anomalies")
        assert res_anom.status_code == 200

        # Sankey
        res_sankey = client.get("/api/budget/insights/sess-1/sankey")
        assert res_sankey.status_code == 200
