"""
test_budget_full_pipeline_coverage.py

Comprehensive tests for Budget domain:
- domains.budget.pipeline (BudgetContext, signature, real/internal frames, available balance)
- domains.budget.transfers (detect_transfers, mark_transfers, TransferPair)
- domains.budget.merchants (apply_aliases, load_aliases, normalise_key)
- domains.budget.rules_safety (validate_pattern, validate_category, CompiledRule, UnsafePattern)
"""

import pandas as pd
import pytest
from unittest.mock import MagicMock

from domains.budget.accounts import Account
from domains.budget.pipeline import BudgetContext, _signature
from domains.budget.transfers import detect_transfers, mark_transfers
from domains.budget.merchants import apply_aliases, normalise_key
from domains.budget import rules_safety


def test_budget_context_properties():
    df = pd.DataFrame({
        "txn_id": ["t1", "t2"],
        "amount": [100.0, 500.0],
        "is_transfer": [False, True],
    })
    acc1 = Account(account_key="acc_1", bank="HDFC", kind="savings", closing_balance=25000.0)
    acc2 = Account(account_key="acc_2", bank="ICICI", kind="credit_card", closing_balance=-5000.0)

    ctx = BudgetContext(df=df, accounts=[acc1, acc2], transfers=[], meta={})

    assert len(ctx.real) == 1
    assert ctx.real.iloc[0]["txn_id"] == "t1"
    assert len(ctx.internal) == 1
    assert ctx.internal.iloc[0]["txn_id"] == "t2"
    assert ctx.account("acc_1") == acc1
    assert ctx.account("non_existent") is None
    # Available balance sums non-card deposit accounts with known balances
    assert ctx.available_balance == 25000.0


def test_signature_stability():
    dict1 = {"b": 2, "a": 1}
    dict2 = {"a": 1, "b": 2}
    sig1 = _signature(dict1)
    sig2 = _signature(dict2)
    assert sig1 == sig2
    assert len(sig1) == 16


def test_transfers_detect_and_mark():
    df = pd.DataFrame([
        {"txn_id": "t1", "date": pd.Timestamp("2025-01-01"), "amount": 5000.0, "type": "debit", "source_bank": "HDFC", "account_key": "acc_1", "description": "Transfer to ICICI"},
        {"txn_id": "t2", "date": pd.Timestamp("2025-01-01"), "amount": 5000.0, "type": "credit", "source_bank": "ICICI", "account_key": "acc_2", "description": "Received from HDFC"},
        {"txn_id": "t3", "date": pd.Timestamp("2025-01-02"), "amount": 250.0, "type": "debit", "source_bank": "HDFC", "account_key": "acc_1", "description": "Swiggy"},
    ])

    pairs = detect_transfers(df)
    assert len(pairs) >= 1
    marked_df, kept = mark_transfers(df, pairs)
    assert "is_transfer" in marked_df.columns
    assert bool(marked_df.loc[marked_df["txn_id"] == "t1", "is_transfer"].iloc[0]) is True
    assert bool(marked_df.loc[marked_df["txn_id"] == "t3", "is_transfer"].iloc[0]) is False


def test_merchants_apply_aliases_and_normalise():
    norm_key = normalise_key("UPI/DR/1234/SWIGGY BANGALORE")
    assert "swiggy" in norm_key

    aliases = {norm_key: "Custom Swiggy"}
    resolved = apply_aliases("UPI/DR/1234/SWIGGY BANGALORE", aliases)
    assert resolved == "Custom Swiggy"

    # Default heuristic normalisation
    unaliased = apply_aliases("UPI/DR/9999/ZOMATO RESTAURANT", {})
    assert "Zomato" in unaliased


def test_rules_safety_validation():
    # Valid patterns
    assert rules_safety.validate_pattern("AMAZON", "contains") == "AMAZON"
    assert rules_safety.validate_pattern(r"^\d{4}$", "regex") == r"^\d{4}$"

    # Catastrophic backtracking regex raises UnsafePattern
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern(r"(a+)+$", "regex")

    # Empty pattern raises UnsafePattern
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_pattern("", "contains")

    # Category validation
    assert rules_safety.validate_category("Shopping") == "Shopping"
    with pytest.raises(rules_safety.UnsafePattern):
        rules_safety.validate_category("")


def test_compiled_rule_matching():
    rule = rules_safety.CompiledRule(rule_id="r1", pattern="swiggy", category="Food", match_type="contains")
    assert rule.matches("Paid to SWIGGY", "paid to swiggy") is True
    assert rule.matches("Paid to ZOMATO", "paid to zomato") is False
