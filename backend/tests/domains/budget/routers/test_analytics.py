
"""Budget analytics and insights routers."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from domains.budget.accounts import Account
from domains.budget.pipeline import BudgetContext
from domains.budget.routers import analytics, insights as budget_insights
from domains.budget.transfers import TransferPair
from shared.identity import Caller, identity_scope

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


def _rich_budget_context():
    from domains.budget.transfers import TransferPair

    df = pd.DataFrame([
        {"txn_id": "t1", "date": "2025-01-05", "amount": 120000.0, "type": "credit", "category": "Salary/Income",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "SALARY JAN", "is_transfer": False, "notes": ""},
        {"txn_id": "t2", "date": "2025-01-06", "amount": 25000.0, "type": "debit", "category": "Rent",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "NEFT RENT", "is_transfer": False, "notes": ""},
        {"txn_id": "t3", "date": "2025-01-07", "amount": 1500.0, "type": "debit", "category": "Food & Dining",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "UPI SWIGGY", "is_transfer": False, "notes": ""},
        {"txn_id": "t4", "date": "2025-01-08", "amount": 5000.0, "type": "debit", "category": "Investments",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "ACH SIP MANDATE", "is_transfer": False, "notes": ""},
        {"txn_id": "t5", "date": "2025-01-09", "amount": 800.0, "type": "debit", "category": "Food & Dining",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "POS VISA CAFE", "is_transfer": False, "notes": ""},
        {"txn_id": "t6", "date": "2025-02-05", "amount": 120000.0, "type": "credit", "category": "Salary/Income",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "SALARY FEB", "is_transfer": False, "notes": ""},
        {"txn_id": "t7", "date": "2025-02-06", "amount": 25000.0, "type": "debit", "category": "Rent",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "NEFT RENT", "is_transfer": False, "notes": ""},
        {"txn_id": "t8", "date": "2025-02-07", "amount": 15000.0, "type": "debit", "category": "Shopping & Groceries",
         "source_bank": "ICICI", "account_type": "Credit Card", "description": "AMAZON E-COMM", "is_transfer": False, "notes": ""},
        {"txn_id": "d1", "date": "2025-02-10", "amount": 5000.0, "type": "debit", "category": "Credit Card Payment",
         "source_bank": "HDFC", "account_type": "Savings Account", "description": "CARD PAYMENT", "is_transfer": True, "notes": ""},
        {"txn_id": "c1", "date": "2025-02-10", "amount": 5000.0, "type": "credit", "category": "Credit Card Payment",
         "source_bank": "ICICI", "account_type": "Credit Card", "description": "PAYMENT RECEIVED", "is_transfer": True, "notes": ""},
    ])
    acc = Account(account_key="HDFC:savings:-", bank="HDFC", kind="savings", closing_balance=150000.0,
                  months_covered=["2025-01", "2025-02"], first_txn="2025-01-05", last_txn="2025-02-10")
    card = Account(account_key="ICICI:credit_card:-", bank="ICICI", kind="credit_card",
                   months_covered=["2025-02"], first_txn="2025-02-07", last_txn="2025-02-10")
    pair = TransferPair(
        debit_txn_id="d1", credit_txn_id="c1", from_account="HDFC:savings:-", to_account="ICICI:credit_card:-",
        amount=5000.0, debit_date="2025-02-10", credit_date="2025-02-10", lag_days=0,
        confidence="high", is_card_payment=True,
    )
    return BudgetContext(df=df, accounts=[acc, card], transfers=[pair], meta={"mode": "single"})


def test_require_caller_unauthenticated():
    res = client.get("/api/budget/sess-1/overview")
    assert res.status_code == 401


def test_apply_budget_filters_all_branches():
    df = pd.DataFrame([
        {"txn_id": "t1", "source_bank": "HDFC", "account_type": "Savings Account", "type": "debit",
         "category": "Food", "amount": 300.0, "description": "UPI SWIGGY", "date": "2025-01-15", "notes": "lunch"},
        {"txn_id": "t2", "source_bank": "ICICI", "account_type": "Credit Card", "type": "credit",
         "category": "Salary", "amount": 15000.0, "description": "NEFT SALARY", "date": "2025-02-01", "notes": ""},
        {"txn_id": "t3", "source_bank": "HDFC", "account_type": "Savings Account", "type": "debit",
         "category": "Rent", "amount": 25000.0, "description": "ATM CASH WDL", "date": "2025-03-01", "notes": ""},
    ])
    assert analytics._apply_budget_filters(pd.DataFrame()).empty
    assert len(analytics._apply_budget_filters(df, account_type="Credit Card")) == 1
    assert len(analytics._apply_budget_filters(df, txn_type="credit")) == 1
    assert len(analytics._apply_budget_filters(df, amount_bracket="micro")) == 1
    assert len(analytics._apply_budget_filters(df, amount_bracket="small")) == 0
    assert len(analytics._apply_budget_filters(df, amount_bracket="medium")) == 0
    assert len(analytics._apply_budget_filters(df, amount_bracket="large")) >= 1
    assert len(analytics._apply_budget_filters(df, payment_mode="upi")) == 1
    assert len(analytics._apply_budget_filters(df, payment_mode="atm")) == 1
    assert len(analytics._apply_budget_filters(df, search="swiggy")) == 1
    assert len(analytics._apply_budget_filters(df, date_range="30d")) >= 1
    assert len(analytics._apply_budget_filters(df, date_range="90d")) == 3
    assert len(analytics._apply_budget_filters(df, date_range="180d")) == 3
    assert len(analytics._apply_budget_filters(df, date_range="ytd")) == 3
    assert len(analytics._apply_budget_filters(df, date_range="custom", from_date="2025-02-01", to_date="2025-03-01")) == 2


def test_build_overview_branches(monkeypatch):
    ctx = _rich_budget_context()
    out = analytics._build_overview(ctx, bank="HDFC")
    assert out["total_income"] > 0
    assert out["budget_50_30_20"]["health_score"] >= 0
    assert out["transfers_excluded"]["card_payments"] == 5000.0

    empty_ctx = BudgetContext(df=pd.DataFrame(), accounts=[], transfers=[], meta={})
    with pytest.raises(Exception):
        analytics._build_overview(empty_ctx)

    filtered_empty = analytics._build_overview(ctx, bank="NONEXISTENT")
    assert filtered_empty["total_income"] == 0.0

    no_cat_df = ctx.real.drop(columns=["category"], errors="ignore").copy()
    no_cat_full = pd.concat([no_cat_df, ctx.internal], ignore_index=True)
    no_cat_ctx = BudgetContext(df=no_cat_full, accounts=ctx.accounts, transfers=ctx.transfers, meta=ctx.meta)
    no_cat = analytics._build_overview(no_cat_ctx)
    assert "budget_50_30_20" in no_cat


def test_analytics_endpoints_extended(monkeypatch):
    ctx = _rich_budget_context()
    monkeypatch.setattr(analytics, "load_context", lambda sid, uid: ctx)
    monkeypatch.setattr(budget_insights, "load_context", lambda sid, uid: ctx)
    monkeypatch.setattr(analytics, "update_budget_transactions", lambda uid, sid, updates: True)

    with identity_scope(TEST_CALLER):
        overview = client.get("/api/budget/sess-1/overview?date_range=90d&amount_bracket=large")
        assert overview.status_code == 200
        assert "budget_50_30_20" in overview.json()

        txns = client.get("/api/budget/sess-1/transactions?include_transfers=true&limit=2&offset=0&search=RENT")
        assert txns.status_code == 200
        body = txns.json()
        assert body["total"] >= 1
        assert body["has_more"] in (True, False)

        drill = client.get("/api/budget/sess-1/categories?category=Rent&txn_type=debit")
        assert drill.status_code == 200
        assert drill.json()["is_drilldown"] is True

        empty_cat = client.get("/api/budget/sess-1/categories?category=Nonexistent&txn_type=debit")
        assert empty_cat.status_code == 200

        bulk = client.put("/api/budget/transactions/update", json=[
            {"txn_id": "t1", "session_id": "sess-1", "category": "Food", "notes": "updated"},
        ])
        assert bulk.status_code == 200


def test_analytics_empty_session_paths(monkeypatch):
    empty = BudgetContext(df=pd.DataFrame(), accounts=[], transfers=[], meta={})
    monkeypatch.setattr(analytics, "load_context", lambda sid, uid: empty)

    with identity_scope(TEST_CALLER):
        cats = client.get("/api/budget/sess-1/categories")
        assert cats.status_code == 200
        assert cats.json()["categories"] == []

        txns = client.get("/api/budget/sess-1/transactions")
        assert txns.status_code == 200
        assert txns.json()["total"] == 0


def test_insights_router_endpoints(monkeypatch):
    ctx = _rich_budget_context()
    monkeypatch.setattr(budget_insights, "load_context", lambda sid, uid: ctx)
    monkeypatch.setattr(budget_insights, "set_flag", lambda uid, txn_id, flag: None)
    monkeypatch.setattr(budget_insights, "set_alias", lambda uid, desc, name: "alias-key")
    monkeypatch.setattr(budget_insights.planning, "load_envelopes", lambda uid: {"Rent": 30000.0})
    monkeypatch.setattr(budget_insights.planning, "set_envelope", lambda uid, cat, cap: None)

    with identity_scope(TEST_CALLER):
        transfers = client.get("/api/budget/insights/sess-1/transfers")
        assert transfers.status_code == 200
        assert transfers.json()["count"] == 1

        recurring = client.get("/api/budget/insights/sess-1/recurring")
        assert recurring.status_code == 200

        forecast = client.get("/api/budget/insights/sess-1/forecast")
        assert forecast.status_code == 200

        anomalies = client.get("/api/budget/insights/sess-1/anomalies")
        assert anomalies.status_code == 200

        recon = client.get("/api/budget/insights/sess-1/reconciliation")
        assert recon.status_code == 200

        coverage = client.get("/api/budget/insights/sess-1/coverage")
        assert coverage.status_code == 200
        assert coverage.json()["accounts"]

        envelopes = client.get("/api/budget/insights/sess-1/envelopes")
        assert envelopes.status_code == 200

        flag_ok = client.post("/api/budget/insights/transfers/flag", json={"txn_id": "t1", "flag": "transfer"})
        assert flag_ok.status_code == 200

        flag_bad = client.post("/api/budget/insights/transfers/flag", json={"txn_id": "t1", "flag": "invalid"})
        assert flag_bad.status_code == 422

        env_put = client.put("/api/budget/insights/envelopes", json={"category": "Food", "monthly_cap": 5000.0})
        assert env_put.status_code == 200

        env_bad = client.put("/api/budget/insights/envelopes", json={"category": "Food", "monthly_cap": -1.0})
        assert env_bad.status_code == 422

        alias_ok = client.put("/api/budget/insights/merchants/alias",
                              json={"description": "UPI SWIGGY", "display_name": "Swiggy"})
        assert alias_ok.status_code == 200

        alias_bad = client.put("/api/budget/insights/merchants/alias",
                               json={"description": "UPI SWIGGY", "display_name": "  "})
        assert alias_bad.status_code == 422

def test_analytics_router_auth_and_bulk_update(monkeypatch):
    from domains.budget.routers import analytics as analytics_router

    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            analytics_router._require_caller()
        assert exc.value.status_code == 401

    monkeypatch.setattr(analytics_router, "update_budget_transactions", lambda uid, sid, txns: True)

    with identity_scope(TEST_CALLER):
        ok = analytics_router.bulk_update_transactions([
            analytics_router.TransactionUpdate(
                session_id="s1", txn_id="t1", category="Food",
            ),
        ])
        assert ok["status"] == "ok"

        monkeypatch.setattr(analytics_router, "update_budget_transactions", lambda uid, sid, txns: False)
        with pytest.raises(HTTPException) as exc2:
            analytics_router.bulk_update_transactions([
                analytics_router.TransactionUpdate(session_id="s1", txn_id="t1"),
            ])
        assert exc2.value.status_code == 400



def test_analytics_infer_payment_and_overview(monkeypatch):
    from domains.budget import derived

    assert analytics._infer_payment_mode("unknown vendor") == "other"
    assert analytics._infer_payment_mode("UPI@paytm") == "upi"

    caller = Caller(user_id="u-analytics", status="active", role="user", email="a@test.com")
    df = pd.DataFrame([
        {"txn_id": "1", "date": "2025-04-01", "description": "NEFT SALARY", "amount": 120000.0,
         "type": "credit", "source_bank": "HDFC", "account_type": "Savings", "category": "Salary/Income",
         "is_transfer": False},
        {"txn_id": "2", "date": "2025-04-05", "description": "RENT ACH", "amount": 70000.0,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings", "category": "Rent",
         "is_transfer": False},
    ])
    ctx = BudgetContext(df=df, accounts=[], transfers=[], meta={})
    monkeypatch.setattr(analytics, "load_context", lambda session_id, user_id: ctx)
    monkeypatch.setattr(derived, "overview", lambda real, sig, fn: fn())

    with identity_scope(caller):
        out = analytics.get_budget_overview("sid")
    assert isinstance(out, dict)
