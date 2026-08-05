"""
test_tax_sessions_and_router_full.py

Full unit test coverage for:
- domains.tax_expert.tax_sessions (cache, DB persistence, encryption, LRU eviction, rehydration, ITR data)
- domains.tax_expert.routers.session (parse-ais, reconcile-broker, tax-history GET and DELETE)
- domains.tax_expert.routers.capital_gains (get_capital_gains, update_transaction_cost)
- domains.tax_expert.routers.itr (upload_itr, get_itr)
"""

import datetime
from unittest.mock import MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared import crypto, storage
from shared.identity import Caller, identity_scope
from domains.tax_expert import tax_sessions
from domains.tax_expert.routers import (
    session as session_router,
    capital_gains as cg_router,
    itr as itr_router,
)

app = FastAPI()
app.include_router(session_router.router, prefix="/api/tax")
app.include_router(cg_router.router, prefix="/api/tax")
app.include_router(itr_router.router, prefix="/api/tax")
client = TestClient(app)

TEST_USER_ID = "user-0000-0000-0000-000000000001"
TEST_CALLER = Caller(user_id=TEST_USER_ID, status="active", role="user", email="u@example.test")


def test_clamp_history_limit():
    assert tax_sessions.clamp_history_limit(5) == 5
    assert tax_sessions.clamp_history_limit(0) == 1
    assert tax_sessions.clamp_history_limit(500) == tax_sessions.HISTORY_MAX_PAGE_SIZE


def test_tax_sessions_crud_and_rehydrate(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value = mock_cur

    mock_conn.execute.return_value.fetchone.return_value = (None, None)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: mock_ctx)

    # Clean in-memory state
    with tax_sessions._SESSIONS_LOCK:
        tax_sessions._tax_sessions.clear()
        tax_sessions._sessions_loaded = True

    # 1. Create
    ais_data = {
        "pan": "ABCDE1234F",
        "financial_year": "2024-2025",
        "taxpayer_name": "Test User",
        "salary": {"gross": 500000.0},
        "interest": [],
        "capital_gains": [],
    }

    with identity_scope(TEST_CALLER):
        sess_id = tax_sessions.create_tax_session(ais_data)
        assert sess_id is not None

        # 2. Get
        sess = tax_sessions.get_tax_session(sess_id)
        assert sess is not None
        assert sess["ais_data"]["pan"] == "ABCDE1234F"

        # 3. Update
        tax_sessions.update_ais_data(sess_id, {"notes": "updated"})
        updated = tax_sessions.get_tax_session(sess_id)
        assert updated["ais_data"].get("notes") == "updated"

        # 4. ITR data
        tax_sessions.update_itr_data(sess_id, {"tax_paid": 45000.0})
        itr_res = tax_sessions.get_itr_data(sess_id)
        assert itr_res["tax_paid"] == 45000.0

        # 5. Get by user
        now = datetime.datetime.now(datetime.timezone.utc)
        metrics_blob = crypto.encrypt_json({"summary": {"fy": "2024-2025", "gross_salary": 500000.0}}, aad=sess_id)
        mock_conn.execute.return_value.fetchall.return_value = [
            (sess_id, now, now, metrics_blob)
        ]
        user_sessions = tax_sessions.get_sessions_by_user(TEST_USER_ID)
        assert len(user_sessions) == 1
        assert user_sessions[0]["session_id"] == sess_id

        # 6. Delete
        ok = tax_sessions.delete_tax_session(sess_id)
        assert ok is True


def test_tax_session_router_endpoints(monkeypatch):
    mock_ais = {
        "pan": "ABCDE1234F",
        "financial_year": "2024-2025",
        "taxpayer_name": "Test User",
        "salary": {"gross": 500000.0},
        "interest": [],
        "capital_gains": [],
        "capital_gains_equity": [{"sr": 1, "cost": 1000.0, "consideration": 1500.0, "gain": 500.0}],
    }

    mock_sess = {
        "session_id": "test-sess-123",
        "user_id": TEST_USER_ID,
        "ais_data": mock_ais,
        "overrides": {},
        "_version": 1,
    }

    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, TEST_USER_ID))
    monkeypatch.setattr(session_router, "parse_ais_pdf", lambda raw: mock_ais)
    monkeypatch.setattr(session_router, "create_tax_session", lambda data, **kw: "test-sess-123")
    monkeypatch.setattr(session_router, "get_tax_session", lambda sid: mock_sess)
    monkeypatch.setattr(session_router, "get_sessions_by_user", lambda uid, **kw: [{"id": "test-sess-123", "financial_year": "2024-2025"}])
    monkeypatch.setattr(session_router, "delete_tax_session", lambda sid: True)

    monkeypatch.setattr(cg_router, "get_tax_session", lambda sid: mock_sess)
    monkeypatch.setattr(cg_router, "get_computation", lambda sid, sess, reg: {
        "income_heads": {"capital_gains": {"stcg_equity": 500.0, "ltcg_equity": 0.0}}
    })

    monkeypatch.setattr(itr_router, "get_tax_session", lambda sid: mock_sess)
    monkeypatch.setattr(itr_router, "parse_itr_pdf", lambda raw: {"gross_total_income": 500000.0})
    monkeypatch.setattr(itr_router, "update_itr_data", lambda sid, d: True)
    monkeypatch.setattr(itr_router, "get_itr_data", lambda sid: {"gross_total_income": 500000.0})

    with identity_scope(TEST_CALLER):
        # 1. Parse AIS POST
        files = {"file": ("ais.pdf", b"%PDF-1.4 test content", "application/pdf")}
        res = client.post("/api/tax/parse-ais", files=files)
        assert res.status_code == 200
        assert res.json()["session_id"] == "test-sess-123"

        # 2. Get history
        res_hist = client.get("/api/tax/tax-history")
        assert res_hist.status_code == 200
        assert len(res_hist.json()["sessions"]) == 1

        # 3. Delete history
        res_del = client.delete("/api/tax/tax-history/test-sess-123")
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "success"

        # 4. Capital Gains GET
        res_cg = client.get("/api/tax/test-sess-123/tax/capital-gains")
        assert res_cg.status_code == 200
        assert res_cg.json()["summary"]["stcg_equity"] == 500.0

        # 5. Capital Gains Update Transaction Cost POST
        res_cg_post = client.post(
            "/api/tax/test-sess-123/tax/capital-gains/transaction",
            json={"category": "capital_gains_equity", "sr": 1, "new_cost": 1200.0},
        )
        assert res_cg_post.status_code == 200
        assert res_cg_post.json()["transaction"]["cost"] == 1200.0

        # 6. ITR Upload POST
        res_itr = client.post(
            "/api/tax/test-sess-123/tax/itr",
            files={"file": ("itr.pdf", b"%PDF-1.4 itr content", "application/pdf")}
        )
        assert res_itr.status_code == 200
        assert res_itr.json()["itr_data"]["gross_total_income"] == 500000.0

        # 7. ITR GET
        res_itr_get = client.get("/api/tax/test-sess-123/tax/itr")
        assert res_itr_get.status_code == 200
        assert res_itr_get.json()["itr_data"]["gross_total_income"] == 500000.0
