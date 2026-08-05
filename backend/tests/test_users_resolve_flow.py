"""
test_users_resolve_flow.py

Unit tests for users.resolve() and related provisioning logic.
All DB I/O is intercepted via patching the sub-functions that use it,
so no live Postgres connection is required.
"""
import datetime
import time
import pytest

from shared import db, users
from shared.identity import Caller
from shared.users import NotAuthorizedError


# ---------------------------------------------------------------------------
# Minimal DB / cursor stubs (used where we need a raw conn)
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


class FakeConn:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._responses:
            return self._responses.pop(0)
        return FakeCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Cache hit path
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

    conn = FakeConn([
        FakeCursor(fetchone=(uid,)),     # SELECT user_id FROM identities
        FakeCursor(),                     # UPDATE last_seen_at
        FakeCursor(),                     # UPDATE identities email COALESCE
        FakeCursor(fetchone=None),        # SELECT pan_encrypted FROM profiles
    ])
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

    conn = FakeConn([FakeCursor(fetchone=None)])  # SELECT user_id → None
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

    conn = FakeConn([
        FakeCursor(fetchone=None),         # SELECT user_id → not found
        FakeCursor(fetchone=(new_uid,)),   # INSERT INTO users RETURNING id
        FakeCursor(),                       # INSERT INTO identities ON CONFLICT
        FakeCursor(fetchone=(new_uid,)),   # re-read winner
        FakeCursor(fetchone=None),          # profiles
    ])
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

    conn = FakeConn([
        FakeCursor(fetchone=None),         # SELECT user_id → not found
        FakeCursor(fetchone=(new_uid,)),   # INSERT INTO users RETURNING id
        FakeCursor(),                       # INSERT INTO identities
        FakeCursor(fetchone=(new_uid,)),   # re-read winner
        FakeCursor(fetchone=None),          # profiles
    ])
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

    conn = FakeConn([
        FakeCursor(fetchone=(uid,)),     # SELECT user_id
        FakeCursor(),                     # UPDATE last_seen_at
        FakeCursor(),                     # UPDATE identities email
        FakeCursor(fetchone=None),        # profiles
    ])
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
    executed = []

    class CapturingConn:
        def __init__(self):
            self._results = [
                FakeCursor(fetchall=[(uid,)]),
                FakeCursor(),
            ]

        def execute(self, sql, params=None):
            executed.append((sql, params))
            if self._results:
                return self._results.pop(0)
            return FakeCursor()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(db, "connect", CapturingConn)

    users.activate_by_email("approved@test.com")
    assert any("UPDATE users SET status" in q[0] for q in executed)


def test_activate_by_email_noop_for_empty():
    # Must not raise anything; there is no DB call for an empty email
    users.activate_by_email("   ")
    users.activate_by_email("")


# ---------------------------------------------------------------------------
# update_account input validation
# ---------------------------------------------------------------------------

def test_update_account_rejects_invalid_status(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeConn([]))
    result = users.update_account("u-1", status="banned")
    assert result is None


def test_update_account_rejects_invalid_role(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeConn([]))
    result = users.update_account("u-1", role="superuser")
    assert result is None


def test_update_account_rejects_no_fields(monkeypatch):
    monkeypatch.setattr(db, "connect", lambda **kw: FakeConn([]))
    result = users.update_account("u-1")
    assert result is None


def test_update_account_rejects_missing_user(monkeypatch):
    conn = FakeConn([FakeCursor(fetchone=None)])  # user not found
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    result = users.update_account("u-nonexistent", status="active")
    assert result is None
