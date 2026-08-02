"""
User-defined categorization rules.

Every pattern is validated before it is stored, and again before it is run - see
domains/budget/rules_safety.py for why the check has to be conclusive up front rather
than bounded by a timeout at match time.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared import db, identity
from domains.budget.rules_safety import (
    MATCH_TYPES,
    MAX_PATTERN_LENGTH,
    MAX_RULES_PER_USER,
    UnsafePattern,
    validate_category,
    validate_pattern,
)
from domains.budget.sessions import reapply_rules_to_all_sessions

router = APIRouter(tags=["budget"])


class RuleCreate(BaseModel):
    pattern: str = Field(..., max_length=MAX_PATTERN_LENGTH)
    category: str = Field(..., max_length=64)
    match_type: str = "contains"


class RuleResponse(RuleCreate):
    rule_id: str
    match_count: int


def _require_caller() -> str:
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to manage categorization rules.")
    return user_id


@router.get("/rules/match-types")
def list_match_types():
    """The match types the UI may offer, so it cannot drift from what the server accepts."""
    return {
        "match_types": list(MATCH_TYPES),
        "max_pattern_length": MAX_PATTERN_LENGTH,
        "max_rules": MAX_RULES_PER_USER,
    }


@router.get("/rules", response_model=List[RuleResponse])
def get_rules():
    user_id = _require_caller()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT rule_id, pattern, category, match_type, match_count
            FROM budget_rules WHERE user_id = %s ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [
        {
            "rule_id": r[0],
            "pattern": r[1],
            "category": r[2],
            "match_type": r[3],
            "match_count": r[4],
        }
        for r in rows
    ]


@router.post("/rules", response_model=RuleResponse)
def create_rule(rule: RuleCreate):
    user_id = _require_caller()

    try:
        pattern = validate_pattern(rule.pattern, rule.match_type)
        category = validate_category(rule.category)
    except UnsafePattern as e:
        raise HTTPException(status_code=422, detail=str(e))

    rule_id = uuid.uuid4().hex
    with db.connect() as conn:
        # Bounded per user: rules are applied per transaction, so the count multiplies
        # the cost of every upload and every re-categorization run.
        existing = conn.execute(
            "SELECT count(*) FROM budget_rules WHERE user_id = %s", (user_id,)
        ).fetchone()[0]
        if existing >= MAX_RULES_PER_USER:
            raise HTTPException(
                status_code=422,
                detail=f"You already have {MAX_RULES_PER_USER} rules, which is the maximum. "
                       "Delete one before adding another.",
            )
        conn.execute(
            """
            INSERT INTO budget_rules (rule_id, user_id, pattern, category, match_type)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (rule_id, user_id, pattern, category, rule.match_type),
        )

    return {
        "rule_id": rule_id,
        "pattern": pattern,
        "category": category,
        "match_type": rule.match_type,
        "match_count": 0,
    }


@router.post("/rules/test")
def test_rule(rule: RuleCreate, description: str = ""):
    """
    Check a pattern against one description without storing it.

    Server-side so the UI does not have to compile user regexes in the browser, which
    is where the same catastrophic-backtracking hazard would freeze the tab.
    """
    _require_caller()
    try:
        pattern = validate_pattern(rule.pattern, rule.match_type)
    except UnsafePattern as e:
        return {"valid": False, "matches": False, "error": str(e)}

    from domains.budget.rules_safety import CompiledRule, clip_subject

    subject = clip_subject(description)
    compiled = CompiledRule("preview", pattern, rule.category, rule.match_type)
    return {"valid": True, "matches": compiled.matches(subject, subject.lower()), "error": None}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    user_id = _require_caller()
    with db.connect() as conn:
        deleted = conn.execute(
            "DELETE FROM budget_rules WHERE rule_id = %s AND user_id = %s",
            (rule_id, user_id),
        ).rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found.")
    return {"status": "ok"}


@router.post("/rules/apply-all")
def apply_rules_to_all():
    user_id = _require_caller()
    updated_count = reapply_rules_to_all_sessions(user_id)
    return {"status": "ok", "transactions_recalculated": updated_count}
