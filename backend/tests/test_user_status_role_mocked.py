"""
test_user_status_role_mocked.py

Mock-based equivalents of test_user_status_role.py.
Tests user status transitions, admin gating, invites, access requests,
and self-demotion checks without requiring live Postgres.
"""

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from shared import users
from shared.identity import Caller, identity_scope
from shared.routers import auth as auth_router


@pytest.fixture(autouse=True)
def clear_user_cache():
    users.invalidate()
    yield
    users.invalidate()


@pytest.fixture
def client():
    return TestClient(app)


def test_assert_admin_denies_regular_user(monkeypatch):
    monkeypatch.delenv("FINANCEBUDDY_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    with pytest.raises(Exception) as exc:
        auth_router._assert_admin(Caller(user_id="u1", status="active", role="user"))
    assert getattr(exc.value, "status_code", None) == 403


def test_assert_admin_allows_role_admin(monkeypatch):
    monkeypatch.delenv("FINANCEBUDDY_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    auth_router._assert_admin(Caller(user_id="u1", status="active", role="admin"))


def test_message_for_access_status_all_variants():
    msg_pending = users.message_for_access_status("pending")
    assert "pending" in msg_pending.lower()
    assert "admin" in msg_pending.lower()

    msg_approved = users.message_for_access_status("approved")
    assert "approved" in msg_approved.lower()

    msg_none = users.message_for_access_status(None)
    assert "access required" in msg_none.lower()


def test_public_auth_rate_limit_enforced_mocked():
    auth_router._public_auth_limiter.reset()
    req = MagicMock()
    req.headers.get.return_value = ""
    req.client.host = "203.0.113.10"
    for _ in range(20):
        auth_router._enforce_public_rate_limit(req, "access-status", "rate@example.test")
    with pytest.raises(HTTPException) as exc:
        auth_router._enforce_public_rate_limit(req, "access-status", "rate@example.test")
    assert exc.value.status_code == 429
    auth_router._public_auth_limiter.reset()


def test_already_registered_message_parsing():
    assert auth_router._already_registered_message(
        "A user with this email address has already been registered"
    )
    assert not auth_router._already_registered_message("rate limit exceeded")


def test_update_app_user_blocks_self_demotion_mocked():
    """An admin cannot demote themselves to a regular user."""
    admin_id = "admin-uuid-1111"
    admin_caller = Caller(user_id=admin_id, status="active", role="admin", email="admin@example.test")

    with identity_scope(admin_caller):
        with pytest.raises(HTTPException) as exc:
            auth_router.update_app_user(
                user_id=admin_id,
                req=auth_router.UpdateUserPayload(role="user"),
            )
        assert exc.value.status_code == 400
        assert "cannot remove your own admin role" in exc.value.detail.lower()


def test_admin_invites_endpoint_mocked(monkeypatch):
    """Admin invite flow provisions user in Supabase and records approved request."""
    admin_id = "admin-uuid-1111"
    admin_caller = Caller(user_id=admin_id, status="active", role="admin", email="admin@example.test")

    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **k: (True, "Invited user"))
    monkeypatch.setattr(auth_router.db, "connect", MagicMock())
    monkeypatch.setattr(users, "activate_by_email", lambda email: True)

    with identity_scope(admin_caller):
        # Mocking the inner SQL execution for invite_user
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = ["req-123"]
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_conn
        monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

        res = auth_router.invite_user(
            req=auth_router.InviteUserPayload(email="invitee@example.test", name="Invitee", method="invite")
        )
        assert res["supabase_provisioned"] is True
        assert res["email"] == "invitee@example.test"


def test_admin_invites_failure_does_not_provision(monkeypatch):
    admin_id = "admin-uuid-1111"
    admin_caller = Caller(user_id=admin_id, status="active", role="admin", email="admin@example.test")

    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **k: (False, "SMTP error"))

    with identity_scope(admin_caller):
        with pytest.raises(HTTPException) as exc:
            auth_router.invite_user(
                req=auth_router.InviteUserPayload(email="fail@example.test", name="Fail", method="invite")
            )
        assert exc.value.status_code == 502
