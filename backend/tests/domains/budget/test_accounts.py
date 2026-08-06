
"""Budget accounts module."""

import pandas as pd
import pytest

from domains.budget.accounts import (
    Account,
    account_key,
    attach_account_keys,
    extract_last4,
    is_credit_card,
    kind_from_account_type,
    summarise_accounts,
    _split_key,
)
from tests.helpers import FakeDbConn


def _txn(txn_id, date, description, amount, kind, bank="HDFC",
         account_type="Savings Account", category="Uncategorized", balance=None):
    row = {
        "txn_id": txn_id, "date": date, "description": description, "amount": amount,
        "type": kind, "source_bank": bank, "account_type": account_type,
        "category": category, "notes": "",
    }
    if balance is not None:
        row["balance"] = balance
    return row


@pytest.fixture
def multi_account():
    return pd.DataFrame([
        _txn("a1", "2025-04-01", "SALARY APRIL", 120000.0, "credit", category="Salary/Income"),
        _txn("a2", "2025-04-02", "IMPS TRANSFER TO SELF", 50000.0, "debit"),
        _txn("b1", "2025-04-02", "IMPS FROM HDFC", 50000.0, "credit", bank="ICICI"),
        _txn("c1", "2025-04-05", "AMAZON", 8000.0, "debit",
             account_type="Credit Card", category="Shopping & Groceries"),
        _txn("a3", "2025-04-20", "CREDIT CARD PAYMENT", 8000.0, "debit"),
        _txn("c2", "2025-04-20", "PAYMENT RECEIVED", 8000.0, "credit", account_type="Credit Card"),
        _txn("a4", "2025-04-07", "SWIGGY", 1200.0, "debit", category="Food & Dining"),
    ])


def test_a_deposit_account_has_no_outstanding():
    """A zero here would read as "nothing owed" rather than "not applicable"."""
    savings = Account(account_key="HDFC:savings:-", bank="HDFC", kind="savings")
    assert savings.outstanding is None
    assert savings.utilisation is None

def test_account_key_is_stable_and_distinguishes_accounts():
    assert account_key("HDFC", "Savings Account", "1234") == "HDFC:savings:1234"
    assert account_key("HDFC", "Savings Account", "1234") != account_key("HDFC", "Savings Account", "5678")
    assert account_key("hdfc", "Credit Card") == "HDFC:credit_card:-"

@pytest.mark.parametrize("label,expected", [
    ("Credit Card", "credit_card"), ("credit card", "credit_card"),
    ("Savings Account", "savings"), ("Current Account", "current"),
    ("Salary Account", "salary"), ("", "savings"), (None, "savings"),
])
def test_account_kind_mapping(label, expected):
    assert kind_from_account_type(label) == expected

def test_attach_account_keys_empty_and_defaults():
    assert attach_account_keys(None) is None
    empty = pd.DataFrame()
    assert attach_account_keys(empty).empty

    df = pd.DataFrame({"date": ["2025-01-01"], "type": ["debit"], "amount": [100.0]})
    out = attach_account_keys(df)
    assert "account_key" in out.columns
    assert out.iloc[0]["account_key"].startswith("GENERIC:savings:")

def test_balance_falls_back_to_opening_plus_flow():
    account = Account(account_key="k", bank="HDFC", kind="savings",
                      opening_balance=1000.0, inflow=500.0, outflow=200.0)
    assert account.balance == pytest.approx(1300.0)

def test_balance_none_without_opening_or_closing():
    account = Account(account_key="k", bank="HDFC", kind="savings", inflow=100.0, outflow=50.0)
    assert account.balance is None

def test_balance_prefers_the_printed_running_balance():
    account = Account(account_key="k", bank="HDFC", kind="savings",
                      opening_balance=1000.0, inflow=500.0, outflow=200.0,
                      closing_balance=9999.0)
    assert account.balance == pytest.approx(9999.0)

def test_card_outstanding_is_purchases_less_payments(multi_account):
    accounts = summarise_accounts(multi_account, meta={})
    card = next(a for a in accounts if a.is_card)
    assert card.outstanding == pytest.approx(0.0)  # 8000 spent, 8000 paid

def test_card_utilisation_and_status():
    card = Account(account_key="HDFC:credit_card:-", bank="HDFC", kind="credit_card",
                   credit_limit=100000.0, outflow=45000.0, inflow=0.0)
    assert card.utilisation == pytest.approx(0.45)
    assert card.utilisation_status == "warning"

    card.outflow = 60000.0
    assert card.utilisation_status == "critical"
    card.outflow = 10000.0
    assert card.utilisation_status == "healthy"

def test_extract_last4_patterns():
    assert extract_last4("XXXX1234") == "1234"
    assert extract_last4("ending 5678") == "5678"
    assert extract_last4(None) is None
    assert extract_last4("no digits") is None

def test_kind_card_without_credit_keyword():
    assert kind_from_account_type("Debit Card") == "savings"
    assert kind_from_account_type("Visa Card") == "credit_card"
    assert is_credit_card("Visa Card") is True

def test_load_and_upsert_account_meta(monkeypatch):
    from tests.helpers import FakeDbConn
    from domains.budget.accounts import load_account_meta, upsert_account_meta

    conn = FakeDbConn()
    conn.queue_result(fetchall=[
        ("HDFC:savings:1234", "Main", "savings", "1234", 50000.0, 1, 15, 1000.0, False),
    ])
    monkeypatch.setattr("domains.budget.accounts.db.connect", lambda: conn)

    meta = load_account_meta("user-1")
    assert meta["HDFC:savings:1234"]["label"] == "Main"
    assert load_account_meta("") == {}

    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=("Old Label", "savings", "1234", None, 1, 15, 500.0))
    monkeypatch.setattr("domains.budget.accounts.db.connect", lambda: conn2)
    upsert_account_meta("user-1", "HDFC:savings:1234", {"label": "Updated", "credit_limit": 75000.0})
    assert any("INSERT INTO budget_account_meta" in sql for sql, _ in conn2.executed)

    conn3 = FakeDbConn()
    conn3.queue_result(fetchone=None)
    monkeypatch.setattr("domains.budget.accounts.db.connect", lambda: conn3)
    upsert_account_meta("user-1", "HDFC:credit_card:-", {"label": "Card"})
    assert conn3.executed

    upsert_account_meta("user-1", "HDFC:savings:1234", {"archived": True})  # ignored field

def test_summarise_accounts_closing_balance_and_split_key():
    df = pd.DataFrame([
        {"date": "2025-01-15", "type": "debit", "amount": 100.0, "source_bank": "HDFC",
         "account_type": "Savings Account", "balance": 900.0},
        {"date": "2025-01-01", "type": "credit", "amount": 500.0, "source_bank": "HDFC",
         "account_type": "Savings Account", "balance": 1000.0},
    ])
    accounts = summarise_accounts(df, meta={})
    assert len(accounts) == 1
    assert accounts[0].closing_balance == pytest.approx(900.0)

    bank, kind, last4 = _split_key("HDFC")
    assert bank == "HDFC"
    assert kind == "-"
    assert last4 == "-"



def test_summarise_accounts_none_returns_empty():
    from domains.budget import accounts

    assert accounts.summarise_accounts(None, {}) == []
