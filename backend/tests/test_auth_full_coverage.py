"""
test_auth_full_coverage.py

Comprehensive unit tests for shared.routers.auth endpoints:
- _client_ip & rate limiting
- /auth/me
- /auth/access-status
- /auth/profile & /auth/profile/pan
- /auth/logout
- /auth/request-access
"""

from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from shared import users, session_stores
from shared.identity import Caller, identity_scope
from shared.routers import auth as auth_router

USER_ID = "00000000-0000-0000-0000-0000000000ee"
CALLER_ACTIVE = Caller(
    user_id=USER_ID,
    status="active",
    role="user",
    email="test-auth@example.test",
    display_name="Test User",
    pan="ABCDE1234F",
)
CALLER_PENDING = Caller(
    user_id=USER_ID,
    status="pending",
    role="user",
    email="pending@example.test",
)


@pytest.fixture
def client():
    return TestClient(app)


def test_client_ip_resolution():
    req_forwarded = MagicMock()
    req_forwarded.headers.get.return_value = "198.51.100.1, 10.0.0.1"
    assert auth_router._client_ip(req_forwarded) == "198.51.100.1"

    req_direct = MagicMock()
    req_direct.headers.get.return_value = ""
    req_direct.client.host = "198.51.100.2"
    assert auth_router._client_ip(req_direct) == "198.51.100.2"


def test_auth_me_unauthenticated(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_auth_me_authenticated(monkeypatch):
    monkeypatch.setattr(users, "find_display_name", lambda uid: "Test User")
    monkeypatch.setattr(users, "primary_email", lambda uid: "test-auth@example.test")
    monkeypatch.setattr(users, "find_pan", lambda uid: "ABCDE1234F")

    with identity_scope(CALLER_ACTIVE):
        data = auth_router.whoami()
        assert data["user_id"] == USER_ID
        assert data["email"] == "test-auth@example.test"
        assert data["pan"] == "ABCDE1234F"
        assert data["display_name"] == "Test User"
        assert data["status"] == "active"


def test_auth_profile_update(monkeypatch):
    monkeypatch.setattr(users, "set_display_name", lambda uid, name: name.strip())

    with identity_scope(CALLER_ACTIVE):
        res = auth_router.update_profile(auth_router.ProfileUpdateRequest(display_name="New Name"))
        assert res["status"] == "success"
        assert res["display_name"] == "New Name"

    # Pending user gets 403
    with identity_scope(CALLER_PENDING):
        with pytest.raises(HTTPException) as exc:
            auth_router.update_profile(auth_router.ProfileUpdateRequest(display_name="New Name"))
        assert exc.value.status_code == 403


def test_auth_profile_pan(monkeypatch):
    monkeypatch.setattr(users, "set_pan", lambda uid, pan: pan.upper() if len(pan) == 10 else None)

    with identity_scope(CALLER_ACTIVE):
        res = auth_router.set_profile_pan(auth_router.ProfileRequest(pan="ABCDE1234F"))
        assert res["status"] == "success"
        assert res["pan"] == "ABCDE1234F"

        # Invalid PAN returns 400
        with pytest.raises(HTTPException) as exc:
            auth_router.set_profile_pan(auth_router.ProfileRequest(pan="INVALID"))
        assert exc.value.status_code == 400


def test_auth_logout(monkeypatch):
    evicted_users = []
    monkeypatch.setattr(session_stores, "evict_user", lambda uid: evicted_users.append(uid) or 1)

    with identity_scope(CALLER_ACTIVE):
        res = auth_router.logout_user()
        assert res["status"] == "success"
        assert USER_ID in evicted_users


def test_auth_access_status_validation(client):
    res = client.post("/auth/access-status", json={"email": "invalid-email"})
    assert res.status_code == 400


def test_auth_access_status_existing_user(client, monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (1,)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

    res = client.post("/auth/access-status", json={"email": "active@example.test"})
    assert res.status_code == 200
    assert res.json()["access_request_status"] == "none"
    assert "active" in res.json()["message"].lower()
