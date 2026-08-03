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


def test_message_for_access_status_pending():
    msg = users.message_for_access_status("pending")
    assert "already submitted" in msg.lower()


def test_message_for_access_status_none():
    msg = users.message_for_access_status(None)
    assert "submit an access request" in msg.lower()


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
def test_pending_access_request_shows_pending_status(truncate_access_requests, deny_open_provision):
    """Google/email after requesting access should land as pending, not denied."""
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (email, name, status)
            VALUES ('waiting@example.test', 'Waiting User', 'pending')
            """
        )

    caller = users.resolve(TEST_ISSUER, "waiting-user", email="waiting@example.test")
    assert caller.status == "pending"
    assert caller.role == "user"


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
def test_access_status_endpoint(truncate_access_requests, client):
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (email, name, status)
            VALUES ('pending@example.test', 'Pending User', 'pending')
            """
        )

    res = client.post("/auth/access-status", json={"email": "pending@example.test"})
    assert res.status_code == 200
    body = res.json()
    assert body["access_request_status"] == "pending"
    assert "already submitted" in body["message"].lower()

    res2 = client.post("/auth/access-status", json={"email": "unknown@example.test"})
    assert res2.status_code == 200
    assert res2.json()["access_request_status"] == "none"


@requires_db
def test_list_and_update_app_users(
    truncate_access_requests, deny_open_provision, monkeypatch, fake_bearer_auth
):
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (email, name, status)
            VALUES ('target@example.test', 'Target User', 'pending')
            """
        )

    users.resolve(TEST_ISSUER, "admin-manager", email="admin@example.test")
    target = users.resolve(TEST_ISSUER, "target-user", email="target@example.test")
    assert target.status == "pending"

    client = TestClient(app)
    headers = fake_bearer_auth("admin-manager", email="admin@example.test")

    list_res = client.get("/auth/users", headers=headers)
    assert list_res.status_code == 200, list_res.text
    listed = {u["user_id"]: u for u in list_res.json()["users"]}
    assert target.user_id in listed
    assert listed[target.user_id]["email"] == "target@example.test"
    assert listed[target.user_id]["status"] == "pending"

    patch_res = client.patch(
        f"/auth/users/{target.user_id}",
        headers=headers,
        json={"status": "active", "role": "admin"},
    )
    assert patch_res.status_code == 200, patch_res.text
    body = patch_res.json()
    assert body["user"]["status"] == "active"
    assert body["user"]["role"] == "admin"

    users.invalidate(target.user_id)
    again = users.resolve(TEST_ISSUER, "target-user", email="target@example.test")
    assert again.status == "active"
    assert again.role == "admin"


@requires_db
def test_update_app_user_blocks_self_demotion(
    truncate_access_requests, deny_open_provision, monkeypatch, fake_bearer_auth
):
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")
    admin = users.resolve(TEST_ISSUER, "self-admin", email="admin@example.test")

    client = TestClient(app)
    headers = fake_bearer_auth("self-admin", email="admin@example.test")
    res = client.patch(
        f"/auth/users/{admin.user_id}",
        headers=headers,
        json={"role": "user"},
    )
    assert res.status_code == 400


@requires_db
def test_middleware_returns_not_authorized(
    truncate_access_requests, deny_open_provision, fake_bearer_auth
):
    client = TestClient(app)
    headers = fake_bearer_auth("cold-user", email="cold@example.test")
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 403
    assert res.json()["detail"] == "not_authorized"
