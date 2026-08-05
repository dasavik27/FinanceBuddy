"""
test_users_module_full_coverage.py

Complete unit test coverage for shared/users.py:
- Profile helpers (set_display_name, set_pan, find_pan, find_display_name, primary_email, _decrypt_pan)
- Supabase admin email lookup (_email_from_supabase cache and error handling)
- Access provisioning decisions (_provision_deny_reason, _initial_account_flags, _sync_account_flags)
- Account lifecycle (activate_by_email, get_account, delete_access_requests_for_email, suspend_by_email)
- Resolve edge cases (profile update on existing user, DB exception fallback)
"""

import json
import time
from unittest.mock import MagicMock
import urllib.error
import pytest

from shared import crypto, identity, users
from tests.test_accounts_and_storage_full import FakeDbConn


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

