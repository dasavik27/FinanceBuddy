"""Unit tests for shared/routers/auth.py."""

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



def test_client_ip_resolution():
    req_forwarded = MagicMock()
    req_forwarded.headers.get.return_value = "198.51.100.1, 10.0.0.1"
    assert auth_router._client_ip(req_forwarded) == "198.51.100.1"

    req_direct = MagicMock()
    req_direct.headers.get.return_value = ""
    req_direct.client.host = "198.51.100.2"
    assert auth_router._client_ip(req_direct) == "198.51.100.2"

    req_unknown = MagicMock()
    req_unknown.headers.get.return_value = ""
    req_unknown.client = None
    assert auth_router._client_ip(req_unknown) == "unknown"


def test_public_rate_limit_enforcement(monkeypatch):
    from fastapi import Request

    auth_router._public_auth_limiter.reset()
    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"
    mock_req.headers.get.return_value = ""

    for _ in range(21):
        try:
            auth_router._enforce_public_rate_limit(mock_req, "test-bucket", "a@test.com")
        except HTTPException:
            break
    else:
        pytest.fail("expected rate limit to trigger")

    with pytest.raises(HTTPException) as exc:
        auth_router._enforce_public_rate_limit(mock_req, "test-bucket", "a@test.com")
    assert exc.value.status_code == 429


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


import json
from unittest.mock import MagicMock, patch
import urllib.error
import pytest
from fastapi import HTTPException

from shared import users
from shared.identity import Caller, identity_scope
from shared.routers import auth as auth_router

ADMIN_CALLER = Caller(user_id="admin-0000-0000-0000-000000000001", status="active", role="admin", email="admin@example.test")
USER_CALLER = Caller(user_id="user-0000-0000-0000-000000000002", status="active", role="user", email="user@example.test")


def test_supabase_admin_helpers(monkeypatch):
    auth_router._supabase_admin_cached = None
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret-service-key")

    url, key = auth_router._supabase_admin_config()
    assert url == "https://xyz.supabase.co"
    assert key == "secret-service-key"

    headers = auth_router._supabase_admin_headers(key)
    assert headers["Authorization"] == "Bearer secret-service-key"
    assert headers["apikey"] == "secret-service-key"

    assert auth_router._already_registered_message("User already registered") is True
    assert auth_router._already_registered_message("Something else") is False


def test_find_supabase_auth_user_id(monkeypatch):
    headers = {"apikey": "test"}

    # 1. Filter match
    mock_filter_resp = MagicMock()
    mock_filter_resp.read.return_value = json.dumps({"users": [{"id": "sb-user-1", "email": "found@example.test"}]}).encode("utf-8")
    mock_filter_resp.__enter__.return_value = mock_filter_resp

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_filter_resp)

    uid = auth_router._find_supabase_auth_user_id("found@example.test", "https://xyz.supabase.co", headers)
    assert uid == "sb-user-1"

    # 2. Empty email
    assert auth_router._find_supabase_auth_user_id("", "https://xyz.supabase.co", headers) is None

    # 3. Filter throws HTTPError 404, fallback to pagination
    import io
    def mock_urlopen_filter_fail(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if "page=1&per_page=200" in url:
            # Page 1 returns users list containing the match
            resp = MagicMock()
            resp.read.return_value = json.dumps({"users": [{"id": "sb-page-1", "email": "page@example.test"}]}).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_filter_fail)
    uid_p = auth_router._find_supabase_auth_user_id("page@example.test", "https://xyz.supabase.co", headers)
    assert uid_p == "sb-page-1"



def test_provision_in_supabase(monkeypatch):
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"id": "new-user"}'
    mock_resp.__enter__.return_value = mock_resp

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_resp)

    ok, msg = auth_router._provision_in_supabase("invitee@example.test", "Invitee Name", method="invite")
    assert ok is True
    assert "invite email sent" in msg.lower()


def test_assert_admin_gating(monkeypatch):
    # Admin caller passes without touching DB
    auth_router._assert_admin(ADMIN_CALLER)

    # Unauthenticated caller raises 401
    with pytest.raises(HTTPException) as exc:
        auth_router._assert_admin(None)
    assert exc.value.status_code == 401

    # Regular user without admin email raises 403
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = ("user@example.test",)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

    monkeypatch.setattr(users, "_admin_emails", lambda: {"admin@example.test"})
    with pytest.raises(HTTPException) as exc:
        auth_router._assert_admin(USER_CALLER)
    assert exc.value.status_code == 403


def test_access_requests_admin_flow(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [
        (1, "req@example.test", "Req Name", "individual", "notes", "pending", None, None)
    ]
    # For approve (3 columns) then for reject (2 columns)
    mock_conn.execute.return_value.fetchone.side_effect = [
        (1, "req@example.test", "Req Name"),
        (1, "req@example.test"),
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)
    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **kw: (True, "Invited"))
    monkeypatch.setattr(users, "activate_by_email", lambda email: "user-123")

    with identity_scope(ADMIN_CALLER):
        # List
        res_list = auth_router.list_access_requests()
        assert len(res_list["requests"]) == 1

        # Approve
        res_appr = auth_router.approve_access_request("1", auth_router.ApproveAccessRequestPayload(method="invite"))
        assert res_appr["status"] == "success"

        # Reject
        res_rej = auth_router.reject_access_request("1")
        assert res_rej["status"] == "success"


def test_invite_user_endpoint(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (10,)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)
    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **kw: (True, "Invited"))
    monkeypatch.setattr(users, "activate_by_email", lambda email: "user-123")

    with identity_scope(ADMIN_CALLER):
        payload = auth_router.InviteUserPayload(email="newuser@example.test", name="New User")
        res = auth_router.invite_user(payload)
        assert res["status"] == "success"
        assert res["email"] == "newuser@example.test"


def test_user_management_endpoints(monkeypatch):
    monkeypatch.setattr(users, "list_accounts", lambda: [{"user_id": "u1", "email": "u1@example.test", "status": "active", "role": "user"}])
    monkeypatch.setattr(users, "update_account", lambda uid, status, role: {"user_id": uid, "status": status or "active", "role": role or "user"})
    monkeypatch.setattr(users, "suspend_by_email", lambda email: "u1")
    monkeypatch.setattr(auth_router, "_ban_in_supabase", lambda email: (True, "Banned"))

    with identity_scope(ADMIN_CALLER):
        # List users
        res_users = auth_router.list_app_users()
        assert len(res_users["users"]) == 1

        # Patch user
        res_patch = auth_router.update_app_user("u1", auth_router.UpdateUserPayload(role="admin"))
        assert res_patch["user"]["role"] == "admin"

        # Suspend user
        res_susp = auth_router.suspend_user(auth_router.SuspendUserPayload(email="u1@example.test"))
        assert res_susp["status"] == "success"
        assert res_susp["supabase_banned"] is True

        # Prevent self-demotion
        with pytest.raises(HTTPException) as exc:
            auth_router.update_app_user(ADMIN_CALLER.user_id, auth_router.UpdateUserPayload(role="user"))
        assert exc.value.status_code == 400

        # Update empty payload
        with pytest.raises(HTTPException) as exc:
            auth_router.update_app_user("u1", auth_router.UpdateUserPayload())
        assert exc.value.status_code == 400

        # Update non-existent
        monkeypatch.setattr(users, "update_account", lambda uid, status, role: None)
        with pytest.raises(HTTPException) as exc:
            auth_router.update_app_user("u-none", auth_router.UpdateUserPayload(role="admin"))
        assert exc.value.status_code == 404


def test_delete_app_user_and_supabase(monkeypatch):
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: "sb-u1")

    # Mock delete HTTP call
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"{}"
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_resp)

    ok, msg = auth_router._delete_in_supabase("user@example.test")
    assert ok is True

    # Test delete_app_user endpoint
    monkeypatch.setattr(users, "get_account", lambda uid: {"user_id": uid, "email": "del@example.test"})
    from shared import session_stores, storage
    monkeypatch.setattr(session_stores, "evict_user", lambda uid: None)
    monkeypatch.setattr(storage, "delete_all_for_user", lambda uid: 2)
    monkeypatch.setattr(users, "invalidate", lambda uid: None)
    monkeypatch.setattr(users, "delete_access_requests_for_email", lambda email: 1)
    monkeypatch.setattr(auth_router, "_delete_in_supabase", lambda email: (True, "Deleted"))

    with identity_scope(ADMIN_CALLER):
        res = auth_router.delete_app_user("u-del-1")
        assert res["status"] == "success"
        assert res["deleted_sessions"] == 2
        assert res["deleted_access_requests"] == 1
        assert res["supabase_deleted"] is True

        # Prevent self deletion
        with pytest.raises(HTTPException) as exc:
            auth_router.delete_app_user(ADMIN_CALLER.user_id)
        assert exc.value.status_code == 400

        # User not found
        monkeypatch.setattr(users, "get_account", lambda uid: None)
        with pytest.raises(HTTPException) as exc:
            auth_router.delete_app_user("u-nonexistent")
        assert exc.value.status_code == 404


def test_access_request_public_and_admin_errors(monkeypatch):
    from fastapi import Request
    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"

    # Validation errors
    with pytest.raises(HTTPException) as exc:
        auth_router.submit_access_request(auth_router.AccessRequestPayload(email="invalid", name=""), mock_req)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        auth_router.submit_access_request(auth_router.AccessRequestPayload(email="valid@test.com", name=""), mock_req)
    assert exc.value.status_code == 400

    # Rate limiter bypass
    monkeypatch.setattr(auth_router, "_enforce_public_rate_limit", lambda r, act, key: None)

    # Already submitted
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (1, "pending")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

    res = auth_router.submit_access_request(auth_router.AccessRequestPayload(email="existing@test.com", name="Existing"), mock_req)
    assert res["status"] == "already_submitted"

    # Approve error paths
    with identity_scope(ADMIN_CALLER):
        # Create method rejected
        with pytest.raises(HTTPException) as exc:
            auth_router.approve_access_request("1", auth_router.ApproveAccessRequestPayload(method="create"))
        assert exc.value.status_code == 400

        # Request not found
        mock_conn.execute.return_value.fetchone.return_value = None
        with pytest.raises(HTTPException) as exc:
            auth_router.approve_access_request("999", auth_router.ApproveAccessRequestPayload(method="invite"))
        assert exc.value.status_code == 404

        # Reject not found
        with pytest.raises(HTTPException) as exc:
            auth_router.reject_access_request("999")
        assert exc.value.status_code == 404


def test_profile_endpoints_coverage(monkeypatch):
    # Unauthenticated
    with pytest.raises(HTTPException) as exc:
        auth_router.update_profile(auth_router.ProfileUpdateRequest(display_name="Test"))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        auth_router.set_profile_pan(auth_router.ProfileRequest(pan="ABCDE1234F"))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        auth_router.logout_user()
    assert exc.value.status_code == 401

    # Inactive caller
    inactive_caller = Caller(user_id="inact-1", status="pending", role="user")
    with identity_scope(inactive_caller):
        with pytest.raises(HTTPException) as exc:
            auth_router.update_profile(auth_router.ProfileUpdateRequest(display_name="Test"))
        assert exc.value.status_code == 403

    # Active caller
    active_caller = Caller(user_id="act-1", status="active", role="user")
    with identity_scope(active_caller):
        monkeypatch.setattr(users, "set_display_name", lambda uid, name: name)
        res = auth_router.update_profile(auth_router.ProfileUpdateRequest(display_name="New Name"))
        assert res["display_name"] == "New Name"

        # Invalid PAN format
        monkeypatch.setattr(users, "set_pan", lambda uid, pan: None)
        with pytest.raises(HTTPException) as exc:
            auth_router.set_profile_pan(auth_router.ProfileRequest(pan="INVALID"))
        assert exc.value.status_code == 400

        # Valid PAN
        monkeypatch.setattr(users, "set_pan", lambda uid, pan: "ABCDE1234F")
        res_pan = auth_router.set_profile_pan(auth_router.ProfileRequest(pan="ABCDE1234F"))
        assert res_pan["pan"] == "ABCDE1234F"

        # Logout
        from shared import session_stores
        monkeypatch.setattr(session_stores, "evict_user", lambda uid: 2)
        res_out = auth_router.logout_user()
        assert res_out["status"] == "success"


def test_auth_me_status_endpoint(monkeypatch):
    # Unauthenticated raises 401
    with pytest.raises(HTTPException) as exc:
        auth_router.whoami()
    assert exc.value.status_code == 401

    # Authenticated active user
    active_caller = Caller(user_id="act-1", status="active", role="user", email="user@test.com", pan="ABCDE1234F", display_name="User Name")
    with identity_scope(active_caller):
        res = auth_router.whoami()
        assert res["user_id"] == "act-1"
        assert res["pan"] == "ABCDE1234F"
        assert res["display_name"] == "User Name"



def test_supabase_ban_delete_edge_cases(monkeypatch):
    # 1. Ban missing config
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: (None, None))
    ok, msg = auth_router._ban_in_supabase("user@test.com")
    assert ok is False and "not configured" in msg

    # 2. Ban user not found
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: None)
    ok, msg = auth_router._ban_in_supabase("notfound@test.com")
    assert ok is False and "No Supabase Auth user found" in msg

    # 3. Ban HTTPError
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: "sb-1")
    def mock_urlopen_err(req, timeout=10):
        raise urllib.error.HTTPError("http://err", 500, "Server Error", {}, io.BytesIO(b'{"message": "error"}'))
    import io
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_err)
    ok, msg = auth_router._ban_in_supabase("err@test.com")
    assert ok is False and "failed" in msg

    # 4. Ban Generic Exception
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(side_effect=RuntimeError("Network drop")))
    ok, msg = auth_router._ban_in_supabase("drop@test.com")
    assert ok is False

    # 5. Delete missing config
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: (None, None))
    ok_d, msg_d = auth_router._delete_in_supabase("user@test.com")
    assert ok_d is False and "not configured" in msg_d

    # 6. Delete user not found
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: None)
    ok_d, msg_d = auth_router._delete_in_supabase("notfound@test.com")
    assert ok_d is False and "No Supabase Auth user found" in msg_d

    # 7. Delete HTTPError
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: "sb-1")
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_err)
    ok_d, msg_d = auth_router._delete_in_supabase("err@test.com")
    assert ok_d is False

    # 8. Delete Generic Exception
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(side_effect=RuntimeError("Conn refused")))
    ok_d, msg_d = auth_router._delete_in_supabase("drop@test.com")
    assert ok_d is False


def test_provision_error_branches(monkeypatch):
    import io
    # 1. Missing config
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: (None, None))
    ok, msg = auth_router._provision_in_supabase("test@test.com", "Test")
    assert ok is False and "missing" in msg

    # 2. Method == create with password
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"id": "user-created"}'
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_resp)
    ok_c, msg_c = auth_router._provision_in_supabase("test@test.com", "Test", method="create", password="pwd")
    assert ok_c is True

    # 3. HTTPError with user already registered
    def mock_urlopen_already(req, timeout=10):
        raise urllib.error.HTTPError("http://err", 422, "Unprocessable", {}, io.BytesIO(b'{"msg": "User already registered"}'))
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_already)
    ok_a, msg_a = auth_router._provision_in_supabase("exists@test.com", "Exists")
    assert ok_a is True and "already has a Supabase" in msg_a

    # 4. HTTPError with generic error
    def mock_urlopen_http_err(req, timeout=10):
        raise urllib.error.HTTPError("http://err", 400, "Bad Request", {}, io.BytesIO(b'{"msg": "Invalid phone"}'))
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_http_err)
    ok_e, msg_e = auth_router._provision_in_supabase("bad@test.com", "Bad")
    assert ok_e is False and "Invalid phone" in msg_e

    # 5. Generic Exception
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(side_effect=RuntimeError("Socket error")))
    ok_ex, msg_ex = auth_router._provision_in_supabase("ex@test.com", "Ex")
    assert ok_ex is False and "Failed to connect" in msg_ex


def test_invite_and_suspend_validation_errors(monkeypatch):
    with identity_scope(ADMIN_CALLER):
        # 1. Invalid email in invite
        with pytest.raises(HTTPException) as exc:
            auth_router.invite_user(auth_router.InviteUserPayload(email="invalid", name="Name"))
        assert exc.value.status_code == 400

        # 2. Empty name in invite
        with pytest.raises(HTTPException) as exc:
            auth_router.invite_user(auth_router.InviteUserPayload(email="valid@test.com", name=""))
        assert exc.value.status_code == 400

        # 3. Create method in invite
        with pytest.raises(HTTPException) as exc:
            auth_router.invite_user(auth_router.InviteUserPayload(email="valid@test.com", name="Name", method="create"))
        assert exc.value.status_code == 400

        # 4. Provision failure in invite
        monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **kw: (False, "Invite failed"))
        with pytest.raises(HTTPException) as exc:
            auth_router.invite_user(auth_router.InviteUserPayload(email="valid@test.com", name="Name"))
        assert exc.value.status_code == 502

        # 5. Suspend invalid email
        with pytest.raises(HTTPException) as exc:
            auth_router.suspend_user(auth_router.SuspendUserPayload(email="invalid"))
        assert exc.value.status_code == 400

        # 6. Suspend not found
        monkeypatch.setattr(users, "suspend_by_email", lambda email: None)
        with pytest.raises(HTTPException) as exc:
            auth_router.suspend_user(auth_router.SuspendUserPayload(email="notfound@test.com"))
        assert exc.value.status_code == 404


def test_check_access_status_endpoint(monkeypatch):
    from fastapi import Request
    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"
    monkeypatch.setattr(auth_router, "_enforce_public_rate_limit", lambda r, act, key: None)

    # 1. Validation error
    with pytest.raises(HTTPException) as exc:
        auth_router.check_access_status(auth_router.AccessStatusPayload(email="invalid"), mock_req)
    assert exc.value.status_code == 400

    # 2. Existing active user
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (1,)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

    res_active = auth_router.check_access_status(auth_router.AccessStatusPayload(email="active@test.com"), mock_req)
    assert res_active["access_request_status"] == "none"
    assert "active" in res_active["message"].lower()

    # 3. Not existing user, lookup status
    mock_conn.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr(users, "_admin_emails", lambda: set())
    monkeypatch.setattr(users, "lookup_access_request_status", lambda conn, email: "pending")
    monkeypatch.setattr(users, "message_for_access_status", lambda status: "Your request is pending.")

    res_pending = auth_router.check_access_status(auth_router.AccessStatusPayload(email="pending@test.com"), mock_req)
    assert res_pending["access_request_status"] == "pending"


def test_submit_access_request_db_failure(monkeypatch):
    from fastapi import Request

    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"
    monkeypatch.setattr(auth_router, "_enforce_public_rate_limit", lambda r, act, key: None)

    mock_conn = MagicMock()
    mock_conn.execute.side_effect = RuntimeError("db write failed")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)

    with pytest.raises(HTTPException) as exc:
        auth_router.submit_access_request(
            auth_router.AccessRequestPayload(email="new@test.com", name="New User"),
            mock_req,
        )
    assert exc.value.status_code == 500


def test_supabase_admin_config_cached_and_missing(monkeypatch):
    auth_router._supabase_admin_cached = None
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    url, key = auth_router._supabase_admin_config()
    assert url is None and key is None
    # second call uses cache
    assert auth_router._supabase_admin_config() == (None, None)
    auth_router._supabase_admin_cached = None


def test_find_supabase_filter_root_object_and_pagination(monkeypatch):
    import io
    headers = {"apikey": "test"}

    # Root object match (empty users list, email on payload root)
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        {"users": [], "id": "root-id", "email": "root@example.test"}
    ).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_resp)
    assert auth_router._find_supabase_auth_user_id(
        "root@example.test", "https://xyz.supabase.co", headers
    ) == "root-id"

    # Generic filter exception then empty pagination
    def mock_urlopen_fail(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
        if "email=" in url:
            raise RuntimeError("filter broken")
        resp = MagicMock()
        resp.read.return_value = json.dumps({"users": []}).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_fail)
    assert auth_router._find_supabase_auth_user_id(
        "missing@example.test", "https://xyz.supabase.co", headers
    ) is None

    # Pagination exhausts without match
    def mock_urlopen_pages(req, timeout=10):
        if "email=" in (req.full_url if hasattr(req, "full_url") else req.get_full_url()):
            raise urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b"{}"))
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"users": [{"id": "other", "email": "other@example.test"}] * 200}
        ).encode("utf-8")
        resp.__enter__.return_value = resp
        return resp

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_pages)
    assert auth_router._find_supabase_auth_user_id(
        "nobody@example.test", "https://xyz.supabase.co", headers
    ) is None


def test_approve_access_request_provision_failure(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (1, "fail@example.test", "Fail User")
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)
    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **kw: (False, "SMTP down"))

    with identity_scope(ADMIN_CALLER):
        with pytest.raises(HTTPException) as exc:
            auth_router.approve_access_request("1", auth_router.ApproveAccessRequestPayload(method="invite"))
        assert exc.value.status_code == 502


def test_invite_user_updates_existing_request(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.side_effect = [
        (5, "existing@example.test"),  # existing request
    ]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(auth_router.db, "connect", lambda: mock_ctx)
    monkeypatch.setattr(auth_router, "_provision_in_supabase", lambda **kw: (True, "Invited"))
    monkeypatch.setattr(users, "activate_by_email", lambda email: "u-5")

    with identity_scope(ADMIN_CALLER):
        res = auth_router.invite_user(
            auth_router.InviteUserPayload(email="existing@example.test", name="Existing User")
        )
        assert res["request_id"] == "5"


def test_ban_in_supabase_success(monkeypatch):
    monkeypatch.setattr(auth_router, "_supabase_admin_config", lambda: ("https://xyz.supabase.co", "secret"))
    monkeypatch.setattr(auth_router, "_find_supabase_auth_user_id", lambda email, url, headers: "sb-ok")
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"{}"
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: mock_resp)

    ok, msg = auth_router._ban_in_supabase("ok@example.test")
    assert ok is True
    assert "banned" in msg.lower()

def test_auth_supabase_user_lookup_pagination(monkeypatch):
    from shared.routers import auth

    pages = [
        {"users": [{"email": "other@test.com", "id": "1"}] * 50},
        {"users": []},
    ]

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    calls = {"n": 0}

    def fake_urlopen(req, timeout=10):
        idx = min(calls["n"], len(pages) - 1)
        calls["n"] += 1
        return FakeResp(pages[idx])

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert auth._find_supabase_auth_user_id(
        "missing@test.com", "https://example.supabase.co", {"Authorization": "Bearer key"},
    ) is None

