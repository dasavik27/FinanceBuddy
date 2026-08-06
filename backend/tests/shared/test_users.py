"""Unit tests for shared/users.py."""

import json
import time
from unittest.mock import MagicMock
import urllib.error
import pytest

from shared import crypto, identity, users
from tests.helpers import FakeDbConn


def test_users_decrypt_pan_and_profile_lookups(monkeypatch):
    # 1. _decrypt_pan with None
    assert users._decrypt_pan(None, "u1") is None

    # 2. _decrypt_pan with DecryptionFailed
    assert users._decrypt_pan(b"corrupt-data", "u1") is None

    # 3. _decrypt_pan success
    enc = crypto.encrypt_text("ABCDE1234F", aad="u1")
    assert users._decrypt_pan(enc, "u1") == "ABCDE1234F"

    # 4. find_pan with DB mock
    conn1 = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn1)
    conn1.queue_result(fetchone=(enc,))
    assert users.find_pan("u1") == "ABCDE1234F"

    # Exception in find_pan
    monkeypatch.setattr(users.db, "connect", MagicMock(side_effect=RuntimeError("DB Down")))
    assert users.find_pan("u1") is None

    # 5. find_display_name
    conn2 = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn2)
    conn2.queue_result(fetchone=("  Avik Das  ",))
    assert users.find_display_name("u1") == "Avik Das"

    conn2.queue_result(fetchone=(None,))
    assert users.find_display_name("u1") is None

    monkeypatch.setattr(users.db, "connect", MagicMock(side_effect=RuntimeError("DB Down")))
    assert users.find_display_name("u1") is None

    # 6. primary_email
    conn3 = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn3)
    conn3.queue_result(fetchone=(" User@Example.COM ",))
    assert users.primary_email("u1") == "user@example.com"

    conn3.queue_result(fetchone=None)
    assert users.primary_email("u1") is None

    monkeypatch.setattr(users.db, "connect", MagicMock(side_effect=RuntimeError("DB Down")))
    assert users.primary_email("u1") is None



def test_users_set_display_name_and_pan(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn)

    # 1. set_display_name None
    assert users.set_display_name("u1", None) is None

    # 2. set_display_name empty string
    assert users.set_display_name("u1", "   ") is None

    # 3. set_display_name long string (>64 chars)
    long_name = "A" * 80
    assert users.set_display_name("u1", long_name) == "A" * 64

    # 4. set_pan invalid
    assert users.set_pan("u1", "invalid-pan") is None

    # 5. set_pan unchanged
    enc = crypto.encrypt_text("ABCDE1234F", aad="u1")
    conn.queue_result(fetchone=(enc,))
    assert users.set_pan("u1", "ABCDE1234F") == "ABCDE1234F"

    # 6. set_pan changed
    conn.queue_result(fetchone=None)
    assert users.set_pan("u1", "ABCDE1234F") == "ABCDE1234F"


def test_users_email_from_supabase(monkeypatch):
    # 1. Empty subject
    assert users._email_from_supabase("") is None

    # 2. Cache hit
    users._supabase_email_cache["cached-subj"] = (time.time() + 300, "cached@test.com")
    assert users._email_from_supabase("cached-subj") == "cached@test.com"

    # 3. Missing env
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    assert users._email_from_supabase("uncached-subj") is None

    # 4. Success from Supabase API (nested user object)
    monkeypatch.setenv("SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret-key")

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"user": {"email": "api@test.com"}}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: mock_resp)

    assert users._email_from_supabase("subj-nested") == "api@test.com"

    # 5. Success from Supabase API (flat email)
    mock_resp.read.return_value = json.dumps({"email": "flat@test.com"}).encode("utf-8")
    assert users._email_from_supabase("subj-flat") == "flat@test.com"

    # 6. Error handling
    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(side_effect=RuntimeError("Timeout")))
    assert users._email_from_supabase("subj-err") is None


def test_users_provisioning_and_flags(monkeypatch, enforce_allowlist):
    conn = FakeDbConn()


    # 1. _provision_deny_reason
    monkeypatch.setattr(users, "_admin_emails", lambda: {"admin@test.com"})
    assert users._provision_deny_reason(conn, "") == "no_email_on_token_or_supabase"
    assert users._provision_deny_reason(conn, "admin@test.com") == "is_admin_email"

    # Access request approved
    conn.queue_result(fetchone=("approved",))
    assert users._provision_deny_reason(conn, "user@test.com") == "has_approved_access"

    # Access request pending
    conn.queue_result(fetchone=("pending",))
    assert users._provision_deny_reason(conn, "user@test.com") == "has_pending_access"

    # Access request other status (e.g. rejected)
    conn.queue_result(fetchone=("rejected",))
    assert "access_request_status=rejected" in users._provision_deny_reason(conn, "user@test.com")

    # No access request
    conn.queue_result(fetchone=None)
    assert "no_access_request" in users._provision_deny_reason(conn, "user@test.com")

    # 2. _initial_account_flags
    assert users._initial_account_flags(conn, None) == ("pending", "user")
    assert users._initial_account_flags(conn, "admin@test.com") == ("active", "admin")

    conn.queue_result(fetchone=(1,)) # _has_approved_access
    assert users._initial_account_flags(conn, "approved@test.com") == ("active", "user")

    conn.queue_result(fetchone=None) # _has_approved_access -> False
    conn.queue_result(fetchone=(1,)) # _has_pending_access -> True
    assert users._initial_account_flags(conn, "pending@test.com") == ("pending", "user")

    # 3. _sync_account_flags
    conn.queue_result(fetchone=None) # User missing
    assert users._sync_account_flags(conn, "u-missing", "any@test.com") == ("pending", "user")

    conn.queue_result(fetchone=("suspended", "user")) # Suspended user
    assert users._sync_account_flags(conn, "u-susp", "any@test.com") == ("suspended", "user")

    conn.queue_result(fetchone=("pending", "user")) # Promote admin
    assert users._sync_account_flags(conn, "u-admin", "admin@test.com") == ("active", "admin")

    conn.queue_result(fetchone=("pending", "user")) # Promote approved
    conn.queue_result(fetchone=(1,)) # _has_approved_access
    assert users._sync_account_flags(conn, "u-appr", "appr@test.com") == ("active", "user")


def test_users_lifecycle_helpers(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn)

    # 1. activate_by_email
    users.activate_by_email("")  # empty noop
    conn.queue_result(fetchall=[("u1",), ("u2",)])
    users.activate_by_email("user@test.com")

    # 2. get_account
    assert users.get_account("") is None

    conn.queue_result(fetchone=None)
    assert users.get_account("u-none") is None

    import datetime
    now = datetime.datetime.now()
    conn.queue_result(fetchone=("u1", "active", "user", now, now, "u1@test.com"))
    acc = users.get_account("u1")
    assert acc["user_id"] == "u1"
    assert acc["email"] == "u1@test.com"

    # 3. delete_access_requests_for_email
    assert users.delete_access_requests_for_email("") == 0
    conn.queue_result(fetchone=(3,))
    assert users.delete_access_requests_for_email("del@test.com") == 3

    # 4. suspend_by_email
    assert users.suspend_by_email("") is None
    conn.queue_result(fetchall=[("u1",), ("u2",)])
    assert users.suspend_by_email("susp@test.com") == "u1"

    conn.queue_result(fetchall=[])
    assert users.suspend_by_email("notfound@test.com") is None


def test_users_resolve_existing_user_updates_and_cache_expiry(monkeypatch):
    # 1. Test cache expiry
    users.invalidate()
    test_key = ("iss-test", "sub-test")
    caller_obj = identity.Caller(user_id="u-cached", status="active", role="user")
    # Put expired entry
    with users._cache_lock:
        users._cache[test_key] = (time.time() - 10, caller_obj)
    assert users._cache_get(test_key) is None


    # 2. Test resolve existing user with name and pan updates
    conn = FakeDbConn()
    monkeypatch.setattr(users.db, "connect", lambda: conn)
    monkeypatch.setattr(users, "_admin_emails", lambda: {"admin@test.com"})

    # Existing identity lookup -> found user_id "u-exist-1"
    conn.queue_result(fetchone=("u-exist-1",))
    # _sync_account_flags -> status 'active', role 'user'
    conn.queue_result(fetchone=("active", "user"))
    # Profile lookup -> empty profile
    conn.queue_result(fetchone=(None, None))

    caller = users.resolve(
        issuer="iss-test",
        subject="sub-exist-1",
        email=None,
        pan="ABCDE1234F",
        name="Existing User Name",
    )
    assert caller is not None
    assert caller.user_id == "u-exist-1"
    assert caller.pan == "ABCDE1234F"
    assert caller.display_name == "Existing User Name"



from shared import db
from shared.identity import Caller
from shared.users import NotAuthorizedError


# ---------------------------------------------------------------------------
# resolve() flow tests (from test_users_resolve_flow.py)
# ---------------------------------------------------------------------------

def test_resolve_returns_cached_caller():
    users.invalidate()
    cached = Caller(user_id="u-cached", email="cached@example.com", status="active", role="user")
    key = ("https://cached.issuer", "sub-cached")
    users._cache_put(key, cached)
    result = users.resolve("https://cached.issuer", "sub-cached")
    assert result is cached
    users.invalidate()


# ---------------------------------------------------------------------------
# Missing issuer or subject
# ---------------------------------------------------------------------------

def test_resolve_none_on_empty_issuer():
    assert users.resolve("", "some-subject") is None


def test_resolve_none_on_empty_subject():
    assert users.resolve("https://issuer.test", "") is None


# ---------------------------------------------------------------------------
# Existing identity (happy path) — patch all sub-functions
# ---------------------------------------------------------------------------

def test_resolve_existing_identity(monkeypatch):
    users.invalidate()
    uid = "00000000-0000-0000-0000-cccccccccccc"
    issuer = "https://existing.issuer"
    subject = "sub-existing"

    # Capture existing account flow: identity row exists, no provisioning needed
    monkeypatch.setattr(users, "_resolve_email", lambda conn, iss, sub, em: "email@test.com")
    monkeypatch.setattr(users, "_sync_account_flags", lambda conn, uid_, em: ("active", "user"))
    monkeypatch.setattr(users, "invalidate", lambda user_id=None: None)

    conn = FakeDbConn()
    conn.queue_result(fetchone=(uid,))
    conn.queue_result()
    conn.queue_result()
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    result = users.resolve(issuer, subject, email="email@test.com")
    assert result is not None
    assert result.user_id == uid
    assert result.status == "active"
    users.invalidate()


# ---------------------------------------------------------------------------
# New identity — provisioning DENIED
# ---------------------------------------------------------------------------

def test_resolve_raises_not_authorized_for_unknown_email(monkeypatch):
    users.invalidate()

    monkeypatch.setattr(users, "_resolve_email", lambda conn, iss, sub, em: "stranger@noaccess.com")
    monkeypatch.setattr(users, "_may_provision", lambda conn, em: False)
    monkeypatch.setattr(users, "_provision_deny_reason", lambda conn, em: "no_access_request;not_in_FINANCEBUDDY_ADMIN_EMAILS")
    monkeypatch.setattr(users, "lookup_access_request_status", lambda conn, em: None)

    conn = FakeDbConn()
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    with pytest.raises(NotAuthorizedError):
        users.resolve("https://issuer.test", "sub-denied", email="stranger@noaccess.com")
    users.invalidate()


# ---------------------------------------------------------------------------
# New identity — provisioning ALLOWED (admin email)
# ---------------------------------------------------------------------------

def test_resolve_provisions_new_admin_account(monkeypatch):
    users.invalidate()
    new_uid = "00000000-0000-0000-0000-aaaaaaaaaaaa"

    monkeypatch.setattr(users, "_resolve_email", lambda conn, iss, sub, em: "admin@test.com")
    monkeypatch.setattr(users, "_may_provision", lambda conn, em: True)
    monkeypatch.setattr(users, "_initial_account_flags", lambda conn, em: ("active", "admin"))
    monkeypatch.setattr(users, "_provision_deny_reason", lambda conn, em: "is_admin_email")
    monkeypatch.setattr(users, "_sync_account_flags", lambda conn, uid_, em: ("active", "admin"))

    conn = FakeDbConn()
    conn.queue_result(fetchone=None)
    conn.queue_result(fetchone=(new_uid,))
    conn.queue_result()
    conn.queue_result(fetchone=(new_uid,))
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    result = users.resolve("https://issuer.test", "sub-admin-new", email="admin@test.com")
    assert result is not None
    assert result.user_id == new_uid
    assert result.role == "admin"
    users.invalidate()


# ---------------------------------------------------------------------------
# New identity — provisioning ALLOWED (approved access request)
# ---------------------------------------------------------------------------

def test_resolve_provisions_new_approved_user(monkeypatch):
    users.invalidate()
    new_uid = "00000000-0000-0000-0000-bbbbbbbbbbbb"

    monkeypatch.setattr(users, "_resolve_email", lambda conn, iss, sub, em: "approved@test.com")
    monkeypatch.setattr(users, "_may_provision", lambda conn, em: True)
    monkeypatch.setattr(users, "_initial_account_flags", lambda conn, em: ("active", "user"))
    monkeypatch.setattr(users, "_provision_deny_reason", lambda conn, em: "has_approved_access")
    monkeypatch.setattr(users, "_sync_account_flags", lambda conn, uid_, em: ("active", "user"))

    conn = FakeDbConn()
    conn.queue_result(fetchone=None)
    conn.queue_result(fetchone=(new_uid,))
    conn.queue_result()
    conn.queue_result(fetchone=(new_uid,))
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    result = users.resolve("https://issuer.test", "sub-approved", email="approved@test.com")
    assert result is not None
    assert result.status == "active"
    assert result.role == "user"
    users.invalidate()


# ---------------------------------------------------------------------------
# resolve() stores caller in cache on success
# ---------------------------------------------------------------------------

def test_resolve_populates_cache(monkeypatch):
    users.invalidate()
    uid = "00000000-0000-0000-0000-eeeeeeeeeeee"
    issuer = "https://cache.issuer"
    subject = "sub-cache-test"

    monkeypatch.setattr(users, "_resolve_email", lambda conn, iss, sub, em: "cache@test.com")
    monkeypatch.setattr(users, "_sync_account_flags", lambda conn, uid_, em: ("active", "user"))

    conn = FakeDbConn()
    conn.queue_result(fetchone=(uid,))
    conn.queue_result()
    conn.queue_result()
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    result = users.resolve(issuer, subject, email="cache@test.com")
    assert result is not None
    cached = users._cache_get((issuer, subject))
    assert cached is not None
    assert cached.user_id == uid
    users.invalidate()


# ---------------------------------------------------------------------------
# resolve() degrades gracefully on unexpected DB error
# ---------------------------------------------------------------------------

def test_resolve_returns_none_on_db_error(monkeypatch):
    users.invalidate()

    def _fail(**kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(db, "connect", _fail)

    result = users.resolve("https://issuer.test", "sub-dberr", email="dberr@test.com")
    assert result is None
    users.invalidate()


# ---------------------------------------------------------------------------
# _email_from_supabase: cache hit (valid TTL)
# ---------------------------------------------------------------------------

def test_email_from_supabase_cache_hit():
    users._supabase_email_cache.clear()
    future = time.time() + 300
    users._supabase_email_cache["sub-cached-supabase"] = (future, "fromcache@test.com")
    result = users._email_from_supabase("sub-cached-supabase")
    assert result == "fromcache@test.com"
    users._supabase_email_cache.clear()


def test_email_from_supabase_no_credentials(monkeypatch):
    users._supabase_email_cache.clear()
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    result = users._email_from_supabase("sub-no-creds")
    assert result is None
    users._supabase_email_cache.clear()


def test_email_from_supabase_empty_subject():
    assert users._email_from_supabase("") is None
    assert users._email_from_supabase(None) is None


# ---------------------------------------------------------------------------
# activate_by_email
# ---------------------------------------------------------------------------

def test_activate_by_email_updates_pending_accounts(monkeypatch):
    uid = "00000000-0000-0000-0000-ffffffffffff"
    conn = FakeDbConn()
    conn.queue_result(fetchall=[(uid,)])
    conn.queue_result()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)

    users.activate_by_email("approved@test.com")
    assert any("UPDATE users SET status" in q[0] for q in conn.executed)


def test_activate_by_email_noop_for_empty():
    # Must not raise anything; there is no DB call for an empty email
    users.activate_by_email("   ")
    users.activate_by_email("")


# ---------------------------------------------------------------------------
# update_account input validation
# ---------------------------------------------------------------------------

def test_update_account_rejects_invalid_status(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeDbConn())
    result = users.update_account("u-1", status="banned")
    assert result is None


def test_update_account_rejects_invalid_role(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeDbConn())
    result = users.update_account("u-1", role="superuser")
    assert result is None


def test_update_account_rejects_no_fields(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeDbConn())
    result = users.update_account("u-1")
    assert result is None


def test_update_account_rejects_missing_user(monkeypatch):
    conn = FakeDbConn()
    conn.queue_result(fetchone=None)
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    result = users.update_account("u-nonexistent", status="active")
    assert result is None

def test_users_helpers_extended(monkeypatch):
    from shared import users

    conn = FakeDbConn()
    conn.queue_result(fetchone=("User@Example.com",))
    assert users._identity_email(conn, "iss", "sub") == "user@example.com"

    users._supabase_email_cache.clear()
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

    class FakeResp:
        def read(self):
            return json.dumps({"email": "resolved@test.com"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=10: FakeResp())
    assert users._email_from_supabase("sub-123") == "resolved@test.com"

    assert "approved" in users.message_for_access_status("approved")
    monkeypatch.setattr(users, "_admin_emails", lambda: {"admin@test.com"})
    assert users._initial_account_flags(conn, "admin@test.com") == ("active", "admin")

def test_users_resolve_and_provision_branches(monkeypatch):
    from shared import users

    conn = FakeDbConn()
    conn.queue_result(fetchone=(None,))
    assert users._identity_email(conn, "iss", "sub") is None

    users._supabase_email_cache.clear()
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")

    class NoEmailResp:
        def read(self):
            return json.dumps({"user": {}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=5: NoEmailResp())
    assert users._email_from_supabase("sub-no-email") is None

    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=(None,))
    assert users._resolve_email(conn2, "iss", "sub", "  User@Test.com  ") == "user@test.com"
    assert users.lookup_access_request_status(conn2, None) is None

