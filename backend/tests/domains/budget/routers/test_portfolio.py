
"""Budget portfolio router."""

import io
from collections import Counter
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.budget.parser import ParseResult
from domains.budget.routers import portfolio as portfolio_router
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="budget@test.com")


def _make_upload(data: bytes, filename: str = "stmt.csv") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def test_portfolio_router_auth():
    with identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            portfolio_router._require_caller()
        assert exc.value.status_code == 401

def test_portfolio_router_upload_errors(monkeypatch):
    from shared.uploads import UploadTooLarge, UnsupportedUploadType

    with identity_scope(CALLER):
        monkeypatch.setattr(
            portfolio_router, "read_upload",
            MagicMock(side_effect=UploadTooLarge("too big")),
        )
        with pytest.raises(HTTPException) as exc:
            portfolio_router.upload_bank_statement(_make_upload(b"x"), bank="HDFC")
        assert exc.value.status_code == 422

        monkeypatch.setattr(
            portfolio_router, "read_upload",
            MagicMock(side_effect=UnsupportedUploadType("bad type")),
        )
        with pytest.raises(HTTPException) as exc2:
            portfolio_router.upload_bank_statement(_make_upload(b"x", "doc.pdf"))
        assert exc2.value.status_code == 422

        monkeypatch.setattr(portfolio_router, "read_upload", lambda f, n: b"csv")
        monkeypatch.setattr(
            portfolio_router, "parse_bank_statement",
            lambda raw, fn, bank, at: ParseResult(
                frame=pd.DataFrame(), bank=bank, account_type=at, error="bad parse",
            ),
        )
        with pytest.raises(HTTPException) as exc3:
            portfolio_router.upload_bank_statement(_make_upload(b"csv"))
        assert exc3.value.status_code == 400

def test_portfolio_router_upload_success(monkeypatch):
    frame = pd.DataFrame([
        {"description": "UPI/SWIGGY", "amount": 500.0, "type": "debit"},
    ])
    parse_result = ParseResult(
        frame=frame, bank="HDFC", account_type="Savings Account", parsed=1,
    )

    monkeypatch.setattr(portfolio_router, "read_upload", lambda f, n: b"csv")
    monkeypatch.setattr(
        portfolio_router, "parse_bank_statement",
        lambda raw, fn, bank, at: parse_result,
    )
    monkeypatch.setattr(portfolio_router, "load_user_rules", lambda uid: [])
    monkeypatch.setattr(
        portfolio_router, "categorize_transactions",
        lambda df, rules=None, user_id=None: (df.assign(category=["Food & Dining"]), Counter()),
    )
    monkeypatch.setattr(portfolio_router, "persist_match_counts", MagicMock())
    monkeypatch.setattr(portfolio_router, "save_budget_session", lambda sid, uid, df, meta: sid)

    with identity_scope(CALLER):
        res = portfolio_router.upload_bank_statement(_make_upload(b"csv"))

    assert "session_id" in res
    assert res["bank"] == "HDFC"
    assert res["parsed"] == 1
    portfolio_router.persist_match_counts.assert_called_once()

def test_portfolio_router_sessions(monkeypatch):
    monkeypatch.setattr(
        portfolio_router, "list_budget_sessions",
        lambda uid: [{"session_id": "s1", "filename": "stmt.csv"}],
    )
    monkeypatch.setattr(portfolio_router, "delete_budget_session", MagicMock())

    with identity_scope(CALLER):
        hist = portfolio_router.get_budget_history()
        assert hist["sessions"][0]["session_id"] == "s1"

        deleted = portfolio_router.delete_session("s1")
        assert deleted["status"] == "deleted"
        portfolio_router.delete_budget_session.assert_called_once_with(USER_ID, "s1")

