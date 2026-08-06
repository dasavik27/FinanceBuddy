import datetime
import uuid
import pytest
from fastapi.testclient import TestClient

from main import app
from shared import crypto, identity, users
from shared.identity import Caller


class FakeDbCursor:
    def __init__(self, fetch_val=None, fetchall_val=None, rowcount=1):
        self._fetch_val = fetch_val
        self._fetchall_val = fetchall_val or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._fetch_val

    def fetchall(self):
        return self._fetchall_val


class FakeDbConn:
    def __init__(self):
        self.executed = []
        self._cursor_queue = []

    def queue_result(self, fetchone=None, fetchall=None, rowcount=1):
        self._cursor_queue.append(FakeDbCursor(fetchone, fetchall, rowcount))

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._cursor_queue:
            return self._cursor_queue.pop(0)
        return FakeDbCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def auth_client():
    return TestClient(app)


def test_caller_and_pan_helpers():
    c = Caller(user_id="u-123", pan="ABCDE1234F", status="active", role="admin", email="admin@test.com", display_name="Admin")
    assert c.user_id == "u-123"
    assert c.pan == "ABCDE1234F"
    assert c.role == "admin"
    assert c.status == "active"

    # PAN helpers
    assert identity.normalize_pan("abcde1234f") == "ABCDE1234F"
    assert identity.normalize_pan("invalid_pan") is None
    assert identity.normalize_pan(None) is None

    assert identity.mask_pan("ABCDE1234F") == "******234F"
    assert identity.mask_pan(None) == "<none>"

    # Ownership checks
    assert identity.owns_record(None) is True
    with identity.identity_scope(c):
        assert identity.owns_record("u-123") is True
        assert identity.owns_record("u-999") is False

    with identity.identity_scope(None):
        assert identity.owns_record("u-123") is False


def test_resolution_cache_lifecycle():
    users.invalidate()
    caller = Caller(user_id="u-cache", email="cache@test.com", display_name="Cache", role="user", status="active")
    key = ("https://issuer.test", "sub-123")
    
    assert users._cache_get(key) is None
    users._cache_put(key, caller)
    assert users._cache_get(key) == caller

    # Invalidate by user_id
    users.invalidate(user_id="u-cache")
    assert users._cache_get(key) is None

    # Test cache capacity eviction
    for i in range(520):
        users._cache_put((f"iss-{i}", f"sub-{i}"), caller)
    assert len(users._cache) <= 512

    # Global clear
    users.invalidate()
    assert len(users._cache) == 0


def test_access_request_lookup_and_messages(monkeypatch):
    conn = FakeDbConn()
    
    # 1. Lookup pending
    conn.queue_result(fetchone=("pending",))
    st = users.lookup_access_request_status(conn, "alice@example.com")
    assert st == "pending"

    # 2. Lookup None
    conn.queue_result(fetchone=None)
    st_none = users.lookup_access_request_status(conn, "nobody@example.com")
    assert st_none is None

    # 3. Message formatting
    msg_none = users.message_for_access_status(None)
    assert "access" in msg_none.lower() or "raise a request" in msg_none.lower()

    msg_pend = users.message_for_access_status("pending")
    assert "under review" in msg_pend.lower() or "pending" in msg_pend.lower()

    msg_rej = users.message_for_access_status("rejected")
    assert "access" in msg_rej.lower() or "raise a request" in msg_rej.lower()

    # 4. Deny reason
    conn.queue_result(fetchone=("pending",))
    reason = users._provision_deny_reason(conn, "alice@example.com")
    assert "under review" in reason.lower() or "pending" in reason.lower()


def test_account_flags_and_provisioning(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(users, "_admin_emails", lambda: {"superadmin@test.com"})

    # Admin email initial flags
    status, role = users._initial_account_flags(conn, "superadmin@test.com")
    assert status == "active"
    assert role == "admin"

    # Approved access request initial flags
    conn.queue_result(fetchone=(1,)) # has approved access
    status2, role2 = users._initial_account_flags(conn, "user@test.com")
    assert status2 == "active"
    assert role2 == "user"

    # Sync flags for existing user
    conn.queue_result(fetchone=("pending", "user"))
    conn.queue_result(fetchone=(1,)) # has approved request
    st_sync, role_sync = users._sync_account_flags(conn, "u-100", "user@test.com")
    assert st_sync == "active"
    assert role_sync == "user"


def test_user_profile_and_pan_operations(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr("shared.db.connect", lambda: conn)

    # 1. Set PAN with valid format
    res_pan = users.set_pan("u-123", "ABCDE1234F")
    assert res_pan == "ABCDE1234F"
    assert any("pan_encrypted" in q[0] for q in conn.executed)

    # 2. Set PAN with invalid format returns None
    assert users.set_pan("u-123", "invalid_pan") is None

    # 3. Decrypt PAN
    uid = str(uuid.uuid4())
    encrypted = crypto.encrypt_text("XYZAB5678C", aad=uid)
    decrypted = users._decrypt_pan(encrypted, uid)
    assert decrypted == "XYZAB5678C"

    # Decrypt corrupted or mismatched AAD
    assert users._decrypt_pan(b"not-valid-cipher", uid) is None
    assert users._decrypt_pan(None, uid) is None

    # 4. Display Name operations
    users.set_display_name("u-123", "  Test Display Name  ")
    assert any("display_name" in q[0] for q in conn.executed)

    # Display name too long or empty
    assert users.set_display_name("u-123", "") is None
    assert len(users.set_display_name("u-123", "x" * 150)) == 64


def test_account_crud_operations(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr("shared.db.connect", lambda: conn)

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Get account
    conn.queue_result(fetchone=("u-1", "active", "user", now, None, "u1@test.com"))
    acc = users.get_account("u-1")
    assert acc is not None
    assert acc["email"] == "u1@test.com"

    # 2. List accounts
    conn.queue_result(fetchall=[("u-1", "active", "user", now, None, "User 1", "u1@test.com")])
    accs = users.list_accounts(limit=10)
    assert len(accs) == 1

    # 3. Update account
    conn.queue_result(fetchone=("u-1", "suspended", "admin", "Admin U1", now))
    updated = users.update_account("u-1", status="suspended", role="admin")
    assert updated["status"] == "suspended"
    assert updated["role"] == "admin"

    # 4. Delete access requests for email
    conn.queue_result(fetchone=(2,)) # count before
    conn.queue_result(rowcount=2)
    deleted_reqs = users.delete_access_requests_for_email("test@test.com")
    assert deleted_reqs == 2

    # 5. Suspend by email
    conn.queue_result(fetchall=[("u-target",)])
    suspended_id = users.suspend_by_email("target@test.com")
    assert suspended_id == "u-target"


def test_auth_router_endpoints(auth_client, signed_in, monkeypatch):
    # 1. POST /auth/access-status
    conn = FakeDbConn()
    monkeypatch.setattr("shared.db.connect", lambda: conn)
    conn.queue_result(fetchone=None) # is_existing_user = False
    conn.queue_result(fetchone=("pending",)) # status = 'pending'
    
    resp = auth_client.post("/auth/access-status", json={"email": "status@test.com"})
    assert resp.status_code == 200
    assert resp.json()["access_request_status"] == "pending"

    # 2. POST /auth/request-access
    conn.queue_result(fetchone=None) # no existing request
    conn.queue_result(fetchone=("req-99",))
    resp_req = auth_client.post("/auth/request-access", json={"email": "newuser@test.com", "name": "New User", "notes": "Access please"})
    assert resp_req.status_code == 200
    assert resp_req.json()["status"] == "success"

    # 3. POST /auth/logout
    resp_logout = auth_client.post("/auth/logout", headers=signed_in)
    assert resp_logout.status_code == 200
    assert resp_logout.json()["status"] == "success"

    # 4. Admin routes with unauthenticated / non-admin caller -> 403 Forbidden
    resp_adm_err = auth_client.get("/auth/access-requests", headers=signed_in)
    assert resp_adm_err.status_code == 403

    # 5. PUT /auth/profile
    monkeypatch.setattr(users, "set_display_name", lambda uid, name: name.strip())
    resp_prof = auth_client.put("/auth/profile", json={"display_name": "Updated Name"}, headers=signed_in)
    assert resp_prof.status_code == 200
    assert resp_prof.json()["display_name"] == "Updated Name"

    # 6. PUT /auth/profile/pan
    monkeypatch.setattr(users, "set_pan", lambda uid, pan: pan.upper())
    resp_pan = auth_client.put("/auth/profile/pan", json={"pan": "ABCDE1234F"}, headers=signed_in)
    assert resp_pan.status_code == 200
    assert resp_pan.json()["pan"] == "ABCDE1234F"
