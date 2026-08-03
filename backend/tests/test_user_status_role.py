"""Tests for account status, role, allowlist provisioning, and admin gates."""

import pytest
from fastapi.testclient import TestClient

from main import app
from shared import db, users
from shared.identity import Caller
from shared.routers import auth as auth_router
from tests.conftest import requires_db, TEST_ISSUER


@pytest.fixture(autouse=True)
def clear_user_cache():
    users.invalidate()
    yield
    users.invalidate()


@pytest.fixture
def deny_open_provision(monkeypatch):
    """Exercise production allowlist behavior (conftest enables open provision by default)."""
    monkeypatch.setenv("FINANCEBUDDY_OPEN_PROVISION", "0")


@pytest.fixture
def truncate_access_requests(clean_db):
    with db.connect() as conn:
        conn.execute("TRUNCATE access_requests RESTART IDENTITY CASCADE")
    yield


def test_assert_admin_denies_when_env_empty(monkeypatch):
    monkeypatch.delenv("FINANCEBUDDY_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    with pytest.raises(Exception) as exc:
        auth_router._assert_admin(Caller(user_id="u1", status="active", role="user"))
    assert getattr(exc.value, "status_code", None) == 403


def test_assert_admin_allows_role_admin(monkeypatch):
    monkeypatch.delenv("FINANCEBUDDY_ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    auth_router._assert_admin(Caller(user_id="u1", status="active", role="admin"))


@requires_db
def test_unapproved_signup_is_denied(truncate_access_requests, deny_open_provision):
    with pytest.raises(users.NotAuthorizedError):
        users.resolve(TEST_ISSUER, "pending-user", email="new@example.test")

    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM identities WHERE subject = %s",
            ("pending-user",),
        ).fetchone()
    assert row[0] == 0


@requires_db
def test_approved_access_request_grants_active_status(truncate_access_requests, deny_open_provision):
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (email, name, status)
            VALUES ('approved@example.test', 'Approved User', 'approved')
            """
        )

    caller = users.resolve(TEST_ISSUER, "approved-user", email="approved@example.test")
    assert caller.status == "active"
    assert caller.role == "user"


@requires_db
def test_admin_email_gets_admin_role(truncate_access_requests, deny_open_provision, monkeypatch):
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")

    caller = users.resolve(TEST_ISSUER, "admin-user", email="admin@example.test")
    assert caller.status == "active"
    assert caller.role == "admin"


@requires_db
def test_activate_by_email_promotes_pending_account(truncate_access_requests):
    # Open provision (default in tests) still creates pending accounts for fixtures.
    caller = users.resolve(TEST_ISSUER, "later-approved", email="later@example.test")
    assert caller.status == "pending"

    users.activate_by_email("later@example.test")

    caller = users.resolve(TEST_ISSUER, "later-approved", email="later@example.test")
    assert caller.status == "active"


@requires_db
def test_suspend_by_email(truncate_access_requests):
    caller = users.resolve(TEST_ISSUER, "to-suspend", email="suspend@example.test")
    assert caller.status in ("pending", "active")

    user_id = users.suspend_by_email("suspend@example.test")
    assert user_id == caller.user_id

    users.invalidate(caller.user_id)
    again = users.resolve(TEST_ISSUER, "to-suspend", email="suspend@example.test")
    assert again.status == "suspended"


@requires_db
def test_invite_endpoint_allowlists_email(
    truncate_access_requests, deny_open_provision, monkeypatch, fake_bearer_auth
):
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")
    monkeypatch.setattr(
        auth_router,
        "_provision_in_supabase",
        lambda **kwargs: (True, "provisioned"),
    )

    admin = users.resolve(TEST_ISSUER, "admin-inviter", email="admin@example.test")
    assert admin.role == "admin"

    client = TestClient(app)
    headers = fake_bearer_auth("admin-inviter", email="admin@example.test")
    res = client.post(
        "/auth/invites",
        headers=headers,
        json={"email": "invitee@example.test", "name": "Invitee", "method": "invite"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["supabase_provisioned"] is True
    assert body["email"] == "invitee@example.test"

    with db.connect() as conn:
        row = conn.execute(
            "SELECT status FROM access_requests WHERE LOWER(email) = %s",
            ("invitee@example.test",),
        ).fetchone()
    assert row is not None
    assert row[0] == "approved"

    invitee = users.resolve(TEST_ISSUER, "invitee-sub", email="invitee@example.test")
    assert invitee.status == "active"


@requires_db
def test_middleware_returns_not_authorized(
    truncate_access_requests, deny_open_provision, fake_bearer_auth
):
    client = TestClient(app)
    headers = fake_bearer_auth("cold-user", email="cold@example.test")
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 403
    assert res.json()["detail"] == "not_authorized"
