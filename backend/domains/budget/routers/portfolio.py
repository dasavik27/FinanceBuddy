"""
Budget session management: upload, list, delete.

Authorization lives in domains/budget/sessions.py, at the data-access boundary, not
here. The `identity.owns_record(user_id)` lines that used to sit in these handlers
compared the caller to themselves and discarded the result - they enforced nothing.
What is required of a route is that it refuses an *unauthenticated* caller, because
owns_record treats an unowned record as readable by anyone; that is _require_caller().
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from shared import identity
from shared.uploads import UnsupportedUploadType, UploadTooLarge, read_upload
from domains.budget.categorizer import (
    categorize_transactions,
    load_user_rules,
    persist_match_counts,
)
from domains.budget.parser import parse_bank_statement
from domains.budget.sessions import (
    delete_budget_session,
    list_budget_sessions,
    save_budget_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["budget"])


def _require_caller() -> str:
    """
    The authenticated user_id, or 401.

    A write must never land unowned: owns_record() allows any caller to read a record
    with no owner, so an anonymous upload would create data readable by everybody.
    """
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to use the budget analyzer.")
    return user_id


@router.post("/upload")
def upload_bank_statement(
    file: UploadFile = File(...),
    bank: str = Form("HDFC"),
    account_type: str = Form("Savings Account"),
):
    """Parse a bank or credit-card statement (CSV / XLS / XLSX) into a budget session."""
    user_id = _require_caller()

    # `file.file.read(n)` rather than `await file.read()`: the async form takes no size
    # argument, so the whole body is materialised before it can be rejected.
    try:
        raw_bytes = read_upload(file.file, file.filename or "")
    except (UploadTooLarge, UnsupportedUploadType) as e:
        raise HTTPException(status_code=422, detail=str(e))

    result = parse_bank_statement(raw_bytes, file.filename or "", bank, account_type)
    if result.error or result.frame.empty:
        raise HTTPException(
            status_code=400,
            detail=result.error or "No transactions found in this file.",
        )

    rules = load_user_rules(user_id)
    df, hits = categorize_transactions(result.frame, rules=rules)
    persist_match_counts(hits)

    accounts_meta = {
        "filename": file.filename,
        "rows": len(df),
        "account_type": result.account_type,
        "bank": result.bank,
    }

    session_id = save_budget_session(str(uuid.uuid4()), user_id, df, accounts_meta)

    # The parse report is part of the response, not just a log line. A statement that
    # half-parsed has to say so - otherwise the dashboard silently describes 60% of the
    # user's spending as if it were all of it.
    return {
        "session_id": session_id,
        "bank": result.bank,
        "account_type": result.account_type,
        **result.report(),
    }


@router.get("/sessions")
def get_budget_history():
    """List the caller's budget uploads."""
    return {"sessions": list_budget_sessions(_require_caller())}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete one budget upload. 404s if it is not the caller's."""
    user_id = _require_caller()
    delete_budget_session(user_id, session_id)
    return {"status": "deleted"}
