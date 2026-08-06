
"""Budget pipeline: BudgetContext, load_context, signatures."""

import pandas as pd
import pytest

from domains.budget.accounts import Account
from domains.budget.pipeline import BudgetContext, _signature, filter_signature, load_context
from domains.budget.transfers import detect_transfers, mark_transfers
from domains.budget.merchants import apply_aliases, normalise_key
from domains.budget import rules_safety


def test_budget_context_without_transfer_column():
    df = pd.DataFrame({"txn_id": ["t1"], "amount": [100.0]})
    ctx = BudgetContext(df=df, accounts=[], transfers=[], meta={})
    assert len(ctx.real) == 1
    assert ctx.internal.empty
    assert ctx.available_balance is None


def test_budget_context_account_lookup():
    acc = Account(account_key="acc_1", bank="HDFC", kind="savings", last4="1234")
    ctx = BudgetContext(df=pd.DataFrame(), accounts=[acc], transfers=[], meta={})
    assert ctx.account("acc_1") is acc
    assert ctx.account("missing") is None

def test_filter_signature_ignores_none():
    assert filter_signature(a=1, b=None) == filter_signature(a=1)

def test_load_context_overall_and_empty(monkeypatch):
    df = pd.DataFrame([
        {
            "txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 100.0,
            "type": "debit", "source_bank": "HDFC", "account_key": "acc_1",
            "description": "Swiggy", "category": "Food",
        },
    ])
    monkeypatch.setattr("domains.budget.pipeline.get_all_budget_sessions", lambda uid: (df, {"mode": "overall"}))
    monkeypatch.setattr("domains.budget.pipeline.get_budget_session", lambda sid: (df, {}))
    monkeypatch.setattr("domains.budget.pipeline.load_aliases", lambda uid: {})
    monkeypatch.setattr("domains.budget.pipeline.load_flags", lambda uid: {})
    monkeypatch.setattr("domains.budget.pipeline.load_account_meta", lambda uid: {})
    monkeypatch.setattr("domains.budget.pipeline.detect_transfers", lambda d: [])
    monkeypatch.setattr("domains.budget.pipeline.mark_transfers", lambda d, p, f: (d, p))
    monkeypatch.setattr("domains.budget.pipeline.summarise_accounts", lambda d, m: [])

    ctx = load_context("overall", "user-1")
    assert not ctx.df.empty
    assert ctx.meta["mode"] == "overall"

    monkeypatch.setattr("domains.budget.pipeline.get_budget_session", lambda sid: (pd.DataFrame(), {}))
    empty = load_context("sess-1", "user-1")
    assert empty.df.empty

