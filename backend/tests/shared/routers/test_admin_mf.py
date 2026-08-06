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


@requires_db
def test_admin_mf_sync_non_admin_forbidden(db_schema, fake_bearer_auth, monkeypatch):
    """Authenticated non-admin callers receive 403 Forbidden."""
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")
    users.resolve(TEST_ISSUER, "regular-user", email="user@example.test")

    client = TestClient(app)
    headers = fake_bearer_auth("regular-user", email="user@example.test")
    res = client.get("/admin/mf-sync/status", headers=headers)
    assert res.status_code == 403


@requires_db
def test_admin_mf_sync_authorized_admin(db_schema, fake_bearer_auth, monkeypatch):
    """Admin callers can check status, search schemes, and trigger sync."""
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@financebuddy.app")
    admin = users.resolve(TEST_ISSUER, "admin-sub", email="admin@financebuddy.app")
    assert admin.role == "admin"

    client = TestClient(app)
    headers = fake_bearer_auth("admin-sub", email="admin@financebuddy.app")

    # 1. Status endpoint
    status_res = client.get("/admin/mf-sync/status", headers=headers)
    assert status_res.status_code == 200
    status_body = status_res.json()
    assert "total_schemes" in status_body
    assert status_body["total_schemes"] >= 8

    # 2. Search schemes endpoint
    schemes_res = client.get("/admin/mf-sync/schemes?q=HDFC", headers=headers)
    assert schemes_res.status_code == 200
    schemes_body = schemes_res.json()
    assert schemes_body["total"] >= 1
    assert any("HDFC" in s["scheme_name"] for s in schemes_body["schemes"])

    # 3. Trigger sync endpoint
    trigger_res = client.post("/admin/mf-sync/trigger", headers=headers)
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

