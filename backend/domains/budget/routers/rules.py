import uuid
from typing import List
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from shared import identity, db
from domains.budget.sessions import reapply_rules_to_all_sessions

router = APIRouter(tags=["budget"])

class RuleCreate(BaseModel):
    pattern: str
    category: str
    match_type: str = "contains"

class RuleResponse(RuleCreate):
    rule_id: str
    match_count: int

@router.get("/rules", response_model=List[RuleResponse])
def get_rules():
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
        
    with db.connect() as conn:
        rows = conn.execute("""
            SELECT rule_id, pattern, category, match_type, match_count
            FROM budget_rules
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()
        
    return [
        {
            "rule_id": r[0],
            "pattern": r[1],
            "category": r[2],
            "match_type": r[3],
            "match_count": r[4]
        }
        for r in rows
    ]

@router.post("/rules", response_model=RuleResponse)
def create_rule(rule: RuleCreate):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
    rule_id = uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO budget_rules (rule_id, user_id, pattern, category, match_type)
            VALUES (%s, %s, %s, %s, %s)
        """, (rule_id, user_id, rule.pattern, rule.category, rule.match_type))
        
    return {
        "rule_id": rule_id,
        "pattern": rule.pattern,
        "category": rule.category,
        "match_type": rule.match_type,
        "match_count": 0
    }

@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
        
    with db.connect() as conn:
        conn.execute("""
            DELETE FROM budget_rules
            WHERE rule_id = %s AND user_id = %s
        """, (rule_id, user_id))
        
    return {"status": "ok"}

@router.post("/rules/apply-all")
def apply_rules_to_all():
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(401, detail="Unauthorized")
        
    updated_count = reapply_rules_to_all_sessions(user_id)
    return {"status": "ok", "transactions_recalculated": updated_count}
