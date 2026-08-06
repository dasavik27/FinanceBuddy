
"""Budget transfer detection and pairing."""

import pandas as pd
import pytest

from domains.budget.transfers import detect_transfers, mark_transfers, split_real_flows


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


def test_a_card_payment_is_identified_as_such(multi_account):
    pairs = detect_transfers(multi_account)
    card_payments = [p for p in pairs if p.is_card_payment]
    assert len(card_payments) == 1
    assert card_payments[0].amount == 8000.0

def test_a_payment_to_someone_else_is_not_a_transfer():
    """
    Only a matched pair reclassifies. A lone debit saying "TRANSFER" is a real expense -
    treating the narration as proof would silently delete money the user actually spent.
    """
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "IMPS TRANSFER TO RAHUL", 5000.0, "debit"),
        _txn("a2", "2025-04-01", "SALARY", 50000.0, "credit"),
    ])
    df, _ = mark_transfers(df)
    real, _ = split_real_flows(df)
    assert real[real["type"] == "debit"]["amount"].sum() == pytest.approx(5000.0)

def test_a_single_account_cannot_produce_a_transfer():
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER OUT", 5000.0, "debit"),
        _txn("a2", "2025-04-01", "TRANSFER IN", 5000.0, "credit"),
    ])
    assert detect_transfers(df) == []

def test_a_user_override_beats_the_heuristic(multi_account):
    df, pairs = mark_transfers(multi_account, flags={"a2": "not_transfer", "b1": "not_transfer"})
    real, _ = split_real_flows(df)
    assert real[real["type"] == "debit"]["amount"].sum() == pytest.approx(59200.0)

def test_amounts_must_match_exactly():
    """A tolerance would pair a 5,000 rent payment with a 5,001 salary advance."""
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER", 5000.0, "debit"),
        _txn("b1", "2025-04-01", "RECEIVED", 5001.0, "credit", bank="ICICI"),
    ])
    assert detect_transfers(df) == []

def test_card_spend_is_counted_once_not_twice(multi_account):
    """
    The 8,000 Amazon purchase is spending. The 8,000 bill payment that settles it is
    not additional spending - it is the same money, moved.
    """
    df, _ = mark_transfers(multi_account)
    real, _ = split_real_flows(df)
    debits = real[real["type"] == "debit"]

    assert sorted(debits["description"]) == ["AMAZON", "SWIGGY"]
    assert debits["amount"].sum() == pytest.approx(9200.0)

def test_legs_too_far_apart_are_not_paired():
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER", 5000.0, "debit"),
        _txn("b1", "2025-04-30", "RECEIVED", 5000.0, "credit", bank="ICICI"),
    ])
    assert detect_transfers(df) == []

def test_self_transfer_is_paired(multi_account):
    pairs = detect_transfers(multi_account)
    amounts = sorted(p.amount for p in pairs)
    assert amounts == [8000.0, 50000.0]

def test_transfers_are_excluded_from_income_and_expense(multi_account):
    df, pairs = mark_transfers(multi_account)
    real, internal = split_real_flows(df)

    income = real[real["type"] == "credit"]["amount"].sum()
    expense = real[real["type"] == "debit"]["amount"].sum()

    # Naively these are 178,000 and 67,200.
    assert income == pytest.approx(120000.0)
    assert expense == pytest.approx(9200.0)



"""Budget transfers — mocked coverage."""

import pandas as pd
import pytest

from domains.budget.transfers import (
    TransferPair,
    detect_transfers,
    load_flags,
    mark_transfers,
    set_flag,
    split_real_flows,
)


def test_transfer_pair_and_flags(monkeypatch):
    pair = TransferPair(
        debit_txn_id="d1", credit_txn_id="c1", from_account="a1", to_account="a2",
        amount=1000.0, debit_date="2025-01-01", credit_date="2025-01-02",
        lag_days=1, confidence="high", is_card_payment=True,
    )
    d = pair.as_dict()
    assert d["is_card_payment"] is True and d["amount"] == 1000.0

    assert detect_transfers(None) == []
    assert detect_transfers(pd.DataFrame()) == []

    df = pd.DataFrame([
        {"txn_id": "d1", "date": "2025-01-01", "amount": 500.0, "type": "debit",
         "source_bank": "HDFC", "account_type": "Savings", "description": "xfer"},
        {"txn_id": "c1", "date": "2025-01-10", "amount": 500.0, "type": "credit",
         "source_bank": "ICICI", "account_type": "Savings", "description": "xfer"},
    ])
    assert detect_transfers(df) == []  # lag too large

    df2 = pd.DataFrame([
        {"txn_id": "d1", "date": "bad-date", "amount": 100.0, "type": "debit",
         "source_bank": "HDFC", "account_type": "Savings"},
        {"txn_id": "c1", "date": "2025-01-01", "amount": 100.0, "type": "credit",
         "source_bank": "ICICI", "account_type": "Savings"},
    ])
    assert detect_transfers(df2) == []

    class FlagConn:
        def execute(self, sql, params=None):
            if "SELECT" in sql:
                class R:
                    def fetchall(self_inner):
                        return [("t1", "transfer")]
                return R()
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("domains.budget.transfers.db.connect", lambda: FlagConn())
    assert load_flags("user-1")["t1"] == "transfer"
    assert load_flags(None) == {}

    class WriteConn:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=None):
            self.calls.append((sql, params))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    wc = WriteConn()
    monkeypatch.setattr("domains.budget.transfers.db.connect", lambda: wc)
    set_flag("u1", "t1", "transfer")
    set_flag("u1", "t1", None)
    assert any("DELETE" in c[0] for c in wc.calls)

    df3 = pd.DataFrame([{"amount": 100, "type": "debit"}])
    marked, kept = mark_transfers(df3, [], flags={"x": "transfer", "y": "not_transfer"})
    assert "is_transfer" not in marked.columns or marked["is_transfer"].dtype == bool

    real, internal = split_real_flows(None)
    assert real is None
    df4 = pd.DataFrame([{"txn_id": "t1", "is_transfer": True}, {"txn_id": "t2", "is_transfer": False}])
    real, internal = split_real_flows(df4)
    assert len(real) == 1 and len(internal) == 1

def test_transfers_card_payment_and_mark_empty():
    df = pd.DataFrame([
        {"txn_id": "d1", "date": "2025-01-01", "amount": 1000.0, "type": "debit",
         "source_bank": "HDFC", "account_type": "Savings", "description": "card payment"},
        {"txn_id": "c1", "date": "2025-01-01", "amount": 1000.0, "type": "credit",
         "source_bank": "HDFC", "account_type": "Credit Card", "description": "payment received"},
    ])
    pairs = detect_transfers(df)
    assert pairs and pairs[0].is_card_payment

    empty_df, kept = mark_transfers(pd.DataFrame(), None)
    assert empty_df.empty and kept == []

    df_no_flag = pd.DataFrame([{"txn_id": "t1", "is_transfer": False}])
    real, internal = split_real_flows(df_no_flag.drop(columns=["is_transfer"]))
    assert len(real) == 1 and internal.empty

def test_transfers_same_bank_pair(monkeypatch):
    df = pd.DataFrame([
        {
            "txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 1000.0,
            "type": "debit", "source_bank": "HDFC", "account_key": "acc_1", "description": "xfer",
        },
        {
            "txn_id": "t2", "date": pd.Timestamp("2025-01-01"), "amount": 1000.0,
            "type": "credit", "source_bank": "HDFC", "account_key": "acc_2", "description": "xfer",
        },
    ])
    pairs = detect_transfers(df)
    marked, kept = mark_transfers(df, pairs, flags={})
    assert "is_transfer" in marked.columns

def test_detect_transfers_empty_after_bad_dates():
    df = pd.DataFrame([
        {"date": "not-a-date", "amount": 100.0, "type": "debit", "account_key": "A:savings:1"},
        {"date": "also-bad", "amount": 100.0, "type": "credit", "account_key": "B:savings:2"},
    ])
    assert detect_transfers(df) == []

