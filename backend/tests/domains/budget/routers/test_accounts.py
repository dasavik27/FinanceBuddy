
"""Budget accounts router."""

from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException

from domains.budget.accounts import Account, CREDIT_CARD, SAVINGS
from domains.budget.pipeline import BudgetContext
from domains.budget.routers import accounts as accounts_router
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="budget@test.com")


def _mock_budget_context():
    df = pd.DataFrame([
        {
            "txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 100000.0,
            "type": "credit", "category": "Salary", "source_bank": "HDFC",
            "description": "Salary Dec", "is_transfer": False,
        },
        {
            "txn_id": "t2", "date": pd.Timestamp("2025-01-02"), "amount": 25000.0,
            "type": "debit", "category": "Rent", "source_bank": "HDFC",
            "description": "Rent Transfer", "is_transfer": False,
        },
    ])
    savings = Account(
        account_key="HDFC:savings:1234", bank="HDFC", kind=SAVINGS,
        closing_balance=75000.0, last4="1234",
    )
    card = Account(
        account_key="HDFC:credit_card:5678", bank="HDFC", kind=CREDIT_CARD,
        last4="5678", credit_limit=100000.0, inflow=5000.0, outflow=45000.0,
    )
    return BudgetContext(df=df, accounts=[card, savings], transfers=[], meta={})


def test_accounts_router_auth():
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            accounts_router._require_caller()
        assert exc.value.status_code == 401

    with identity_scope(CALLER):
        assert accounts_router._require_caller() == USER_ID

def test_accounts_router_list_accounts(monkeypatch):
    monkeypatch.setattr(accounts_router, "load_context", lambda sid, uid: _mock_budget_context())

    with identity_scope(CALLER):
        resp = accounts_router.list_accounts(MagicMock(), session_id="overall")

    assert resp["totals"]["account_count"] == 2
    assert resp["totals"]["card_count"] == 1
    assert resp["totals"]["deposit_balance"] == 75000.0
    assert len(resp["utilisation_warnings"]) >= 1
    assert "cards_missing_limit" in resp

def test_accounts_router_update_account(monkeypatch):
    monkeypatch.setattr(accounts_router, "upsert_account_meta", MagicMock())

    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            accounts_router.update_account("HDFC:savings:1234", accounts_router.AccountMetaUpdate())
        assert exc.value.status_code == 422

        with pytest.raises(HTTPException) as exc2:
            accounts_router.update_account(
                "HDFC:savings:1234",
                accounts_router.AccountMetaUpdate(last4="abcd"),
            )
        assert exc2.value.status_code == 422

        res = accounts_router.update_account(
            "HDFC:savings:1234",
            accounts_router.AccountMetaUpdate(label="Main Savings", credit_limit=50000.0),
        )
        assert res["status"] == "ok"
        accounts_router.upsert_account_meta.assert_called_once()

