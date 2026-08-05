"""
tests/test_admin_mf_auth.py
Authorization tests for /admin/mf-sync routes.
Verifies anonymous (401), non-admin (403), and admin (200) access patterns.
"""

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
