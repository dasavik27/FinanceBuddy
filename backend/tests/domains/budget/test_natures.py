
"""Budget nature classification and sankey."""

import pandas as pd
import pytest

from domains.budget.insights import build_sankey
from domains.budget.natures import nature_of
from domains.budget.transfers import mark_transfers


@pytest.fixture
def multi_account():
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


@pytest.mark.parametrize("category,expected", [
    ("Utilities & Bills", "needs"), ("Food & Dining", "wants"),
    ("Investments", "investments"), ("Salary/Income", "income"),
    ("Interest Income", "income"),
    ("Credit Card Payment", "transfers"), ("Something Unseen", "wants"),
])
def test_nature_classification(category, expected):
    assert nature_of(category) == expected

def test_sankey_links_income_through_nature_to_category(multi_account):
    df, _ = mark_transfers(multi_account)
    diagram = build_sankey(df, nature_of)
    names = [n["name"] for n in diagram["nodes"]]
    assert "Income" in names
    assert diagram["links"]
    # Every link must reference a node that exists, or the diagram will not render.
    for link in diagram["links"]:
        assert 0 <= link["source"] < len(diagram["nodes"])
        assert 0 <= link["target"] < len(diagram["nodes"])



def test_natures_keyword_fallback():
    assert nature_of("Random Crypto SIP") == "investments"
    assert nature_of("Unknown Merchant") == "wants"

