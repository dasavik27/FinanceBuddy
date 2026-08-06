
"""Budget rules router."""

import pytest
from fastapi import HTTPException

from domains.budget.routers import rules as rules_router
from domains.budget.rules_safety import MAX_RULES_PER_USER
from shared.identity import Caller, identity_scope
from tests.helpers import FakeDbConn

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="budget@test.com")


def test_rules_router_auth():
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            rules_router._require_caller()
        assert exc.value.status_code == 401

def test_rules_router_match_types_and_list(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(fetchall=[
        ("r1", "swiggy", "Food", "contains", 5),
    ])
    monkeypatch.setattr(rules_router.db, "connect", lambda: conn)

    with identity_scope(CALLER):
        mt = rules_router.list_match_types()
        assert "contains" in mt["match_types"]

        rules = rules_router.get_rules()
        assert rules[0]["rule_id"] == "r1"
        assert rules[0]["match_count"] == 5

def test_rules_router_create_and_test(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(fetchone=(0,))  # count
    monkeypatch.setattr(rules_router.db, "connect", lambda: conn)

    with identity_scope(CALLER):
        created = rules_router.create_rule(
            rules_router.RuleCreate(pattern="swiggy", category="Food", match_type="contains"),
        )
        assert created["match_count"] == 0
        assert created["pattern"] == "swiggy"

        preview = rules_router.test_rule(
            rules_router.RuleCreate(pattern="swiggy", category="Food"),
            description="UPI SWIGGY ORDER",
        )
        assert preview["valid"] is True
        assert preview["matches"] is True

        bad = rules_router.test_rule(
            rules_router.RuleCreate(pattern="(a+)+$", category="Food", match_type="regex"),
            description="aaaa",
        )
        assert bad["valid"] is False

def test_rules_router_create_max_rules(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(fetchone=(MAX_RULES_PER_USER,))
    monkeypatch.setattr(rules_router.db, "connect", lambda: conn)

    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            rules_router.create_rule(
                rules_router.RuleCreate(pattern="x", category="Misc"),
            )
        assert exc.value.status_code == 422
        assert "maximum" in exc.value.detail.lower()

def test_rules_router_create_unsafe_pattern(monkeypatch):
    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            rules_router.create_rule(
                rules_router.RuleCreate(pattern="", category="Food"),
            )
        assert exc.value.status_code == 422

def test_rules_router_delete_and_apply_all(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(rowcount=0)
    monkeypatch.setattr(rules_router.db, "connect", lambda: conn)
    monkeypatch.setattr(
        rules_router, "reapply_rules_to_all_sessions", lambda uid: 42,
    )

    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            rules_router.delete_rule("missing")
        assert exc.value.status_code == 404

        conn.queue_result(rowcount=1)
        assert rules_router.delete_rule("r1")["status"] == "ok"

        applied = rules_router.apply_rules_to_all()
        assert applied["transactions_recalculated"] == 42

