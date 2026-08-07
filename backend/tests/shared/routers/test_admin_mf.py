"""
tests/test_admin_mf_auth.py
Authorization tests for /admin/mf-sync routes.
Verifies anonymous (401), non-admin (403), and admin (200) access patterns.
"""
from tests.helpers import FakeDbConn
from shared.identity import Caller, identity_scope
from fastapi import HTTPException

import pytest
from fastapi.testclient import TestClient
from main import app
from shared import users
from tests.conftest import requires_db, TEST_ISSUER


def test_admin_mf_sync_anonymous_rejected():
    """Anonymous callers cannot access admin sync status."""
    client = TestClient(app)
    res = client.get("/admin/mf-sync/status")
    assert res.status_code == 401


def test_admin_mf_sync_non_admin_forbidden(signed_in, monkeypatch):
    """Authenticated non-admin callers receive 403 Forbidden."""
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")
    conn = FakeDbConn()
    conn.queue_result(fetchone=("user@example.test",))
    monkeypatch.setattr("shared.routers.admin_mf.db", type("DB", (), {"connect": staticmethod(lambda: conn)})())

    client = TestClient(app)
    res = client.get("/admin/mf-sync/status", headers=signed_in)
    assert res.status_code == 403


def test_admin_mf_sync_authorized_admin(signed_in, monkeypatch):
    """Admin callers can check status, search schemes, and trigger sync."""
    admin_caller = Caller(
        user_id="admin-sub",
        role="admin",
        email="admin@financebuddy.app",
        status="active",
    )
    monkeypatch.setattr("shared.identity.current_caller", lambda: admin_caller)
    conn = FakeDbConn()
    conn.queue_result(fetchone=("admin@financebuddy.app",))
    conn.queue_result(fetchone=("admin@financebuddy.app",))
    conn.queue_result(fetchone=("admin@financebuddy.app",))
    monkeypatch.setattr("shared.routers.admin_mf.db", type("DB", (), {"connect": staticmethod(lambda: conn)})())

    client = TestClient(app)

    # 1. Status endpoint
    monkeypatch.setattr(
        "shared.services.amfi_ingest.get_sync_status",
        lambda: {"total_schemes": 10, "latest_portfolio_month": "2026-03"},
    )
    status_res = client.get("/admin/mf-sync/status", headers=signed_in)
    assert status_res.status_code == 200
    status_body = status_res.json()
    assert "total_schemes" in status_body
    assert status_body["total_schemes"] >= 8

    # 2. Search schemes endpoint
    monkeypatch.setattr(
        "shared.services.amfi_ingest.search_synced_schemes",
        lambda **k: {"total": 1, "schemes": [{"scheme_name": "HDFC Top 100", "amc": "HDFC"}]},
    )
    schemes_res = client.get("/admin/mf-sync/schemes?q=HDFC", headers=headers if "headers" in locals() else signed_in)
    assert schemes_res.status_code == 200
    schemes_body = schemes_res.json()
    assert schemes_body["total"] >= 1
    assert any("HDFC" in s["scheme_name"] for s in schemes_body["schemes"])

    # 3. Trigger sync endpoint
    monkeypatch.setattr(
        "shared.services.amfi_ingest.trigger_amfi_sync",
        lambda *a, **k: {"status": "completed", "schemes_updated": 10, "duration_seconds": 1.2},
    )
    trigger_res = client.post("/admin/mf-sync/trigger", headers=signed_in)
    assert trigger_res.status_code == 200
    trigger_body = trigger_res.json()
    assert trigger_body["status"] == "completed"
    assert trigger_body["schemes_updated"] >= 8

def test_admin_mf_email_allowlist(monkeypatch):
    from shared.routers import admin_mf
    from shared import users

    user = Caller(user_id="u2", status="active", role="user", email="ops@test.com")
    conn = FakeDbConn()
    conn.queue_result(fetchone=("ops@test.com",))
    monkeypatch.setattr("shared.routers.admin_mf.db", type("DB", (), {"connect": staticmethod(lambda: conn)})())
    monkeypatch.setattr(users, "_admin_emails", lambda: {"ops@test.com"})
    with identity_scope(user):
        assert admin_mf.get_mf_sync_status() is not None

    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=("notadmin@test.com",))
    monkeypatch.setattr("shared.routers.admin_mf.db", type("DB", (), {"connect": staticmethod(lambda: conn2)})())
    with identity_scope(user):
        with pytest.raises(HTTPException) as exc:
            admin_mf.get_mf_sync_status()
        assert exc.value.status_code == 403

    monkeypatch.setattr(users, "_admin_emails", lambda: set())
    with identity_scope(user):
        with pytest.raises(HTTPException) as exc2:
            admin_mf.get_mf_sync_status()
        assert exc2.value.status_code == 403

def test_admin_mf_sync_status_and_trigger_failure(monkeypatch):
    from shared.routers import admin_mf
    from shared.identity import Caller, identity_scope
    from fastapi import HTTPException
    from tests.helpers import FakeDbConn

    admin = Caller(user_id="admin-u", status="active", role="admin", email="admin@test.com")
    conn = FakeDbConn()
    conn.queue_result(fetchone=("admin@test.com",))
    monkeypatch.setattr(
        "shared.routers.admin_mf.db",
        type("DB", (), {"connect": staticmethod(lambda: conn)})(),
    )
    with identity_scope(admin):
        assert admin_mf.get_mf_sync_status() is not None

    monkeypatch.setattr(
        admin_mf.amfi_ingest,
        "trigger_amfi_sync",
        lambda *a, **k: {"status": "failed", "error": "boom"},
    )
    with identity_scope(admin):
        with pytest.raises(HTTPException):
            admin_mf.trigger_mf_sync(admin_mf.SyncTriggerRequest(preset="top5"))

