
"""Budget transaction categorizer."""

from collections import Counter
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.budget import categorizer
from domains.budget.rules_safety import CompiledRule
from tests.helpers import FakeDbConn

USER_ID = "00000000-0000-0000-0000-000000000001"


def test_budget_categorizer_description_cache():
    df = pd.DataFrame([
        {"description": "SWIGGY FOOD", "amount": 500.0, "type": "debit"},
        {"description": "SWIGGY FOOD", "amount": 600.0, "type": "debit"},
    ])
    out, hits = categorizer.categorize_transactions(df)
    assert len(out) == 2


def test_categorizer_compile_rules_hit_count():
    from domains.budget.rules_safety import compile_rules

    rules = compile_rules([("r1", "SWIGGY", "Food", "contains")])
    df_cat = pd.DataFrame([
        {"description": "SWIGGY FOOD", "amount": 100.0, "type": "debit"},
        {"description": "SWIGGY FOOD", "amount": 200.0, "type": "debit"},
    ])
    out, hits = categorizer.categorize_transactions(df_cat, rules=rules)
    assert out.iloc[0]["category"] == "Food"
    assert hits["r1"] == 2


def test_categorizer_load_user_rules_no_user():
    assert categorizer.load_user_rules(None) == []
    assert categorizer.load_user_rules("") == []

def test_categorizer_load_user_rules_from_db(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(fetchall=[
        ("r1", "swiggy", "My Food", "contains"),
    ])
    monkeypatch.setattr(categorizer.db, "connect", lambda: conn)

    rules = categorizer.load_user_rules(USER_ID)
    assert len(rules) == 1
    assert rules[0].rule_id == "r1"
    assert rules[0].category == "My Food"

def test_categorizer_empty_and_missing_description():
    empty, hits = categorizer.categorize_transactions(pd.DataFrame())
    assert empty.empty
    assert hits == Counter()

    none_df, hits2 = categorizer.categorize_transactions(None)
    assert none_df is None
    assert hits2 == Counter()

    no_desc = pd.DataFrame([{"amount": 100.0}])
    out, hits3 = categorizer.categorize_transactions(no_desc)
    assert list(out["category"]) == [categorizer.UNCATEGORIZED]
    assert hits3 == Counter()

def test_categorizer_default_and_user_rules():
    df = pd.DataFrame([
        {"description": "UPI/SWIGGY/123@okaxis"},
        {"description": "UPI/SWIGGY/456@okaxis"},  # repeat -> cache path
        {"description": "UNKNOWN MERCHANT XYZ"},
    ])
    user_rule = CompiledRule("rule-1", "unknown merchant", "Custom", "contains")
    out, hits = categorizer.categorize_transactions(df, rules=[user_rule])

    assert out.iloc[0]["category"] == "Food & Dining"
    assert out.iloc[1]["category"] == "Food & Dining"
    assert out.iloc[2]["category"] == "Custom"
    assert hits["rule-1"] == 1

def test_categorizer_persist_match_counts(monkeypatch):
    categorizer.persist_match_counts(Counter())

    conn = FakeDbConn()
    monkeypatch.setattr(categorizer.db, "connect", lambda: conn)
    categorizer.persist_match_counts(Counter({"r1": 2, "r2": 1}))
    assert len(conn.executed) == 2

    monkeypatch.setattr(categorizer.db, "connect", MagicMock(side_effect=RuntimeError("DB down")))
    categorizer.persist_match_counts(Counter({"r1": 1}))  # must not raise

