"""
test_auth_admin_and_endpoints_full.py

Full unit test coverage for shared.routers.auth administrative endpoints and helpers:
- _supabase_admin_config & _supabase_admin_headers
- _find_supabase_auth_user_id (filtering & pagination)
- _provision_in_supabase & _ban_in_supabase
- _assert_admin gating
- /access-requests (GET, approve, reject)
- /invites (POST)
- /users (GET, PATCH, DELETE) and /users/suspend
"""

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




