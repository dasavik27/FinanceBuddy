"""
Ownership enforcement for budget sessions, without a database.

The budget domain shipped with `SELECT ... FROM budget_payloads WHERE session_id = %s`
and no owner predicate, reachable from three analytics routes with a caller-supplied
id - the same cross-user read that bb5ab023 had just fixed in equity. The
`identity.owns_record(user_id)` calls in the routers passed the caller's own id, so
they compared the caller to themselves and always returned True.

This file pins the decision itself, stubbing the database so it runs on a default
checkout rather than skipping without TEST_DATABASE_URL. It is the budget counterpart
of test_equity_session_authz_unit.py and deliberately asserts the same properties.
"""

import zlib

import pandas as pd
import pytest
from fastapi import HTTPException

from shared import identity
from shared.identity import Caller

from domains.budget import sessions as budget_sessions

USER_A = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
USER_B = Caller(user_id="bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")

SID = "budget-session-under-test"


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"txn_id": "t1", "date": "2025-04-01", "description": "SWIGGY",
         "amount": 250.0, "type": "debit", "source_bank": "HDFC",
         "account_type": "Savings Account", "category": "Food & Dining", "notes": ""},
    ])


class _FakeConn:
    """
    Stands in for a psycopg connection.

    `owner` is what the sessions registry reports; `payload` is the encrypted blob.
    `queries` records what was asked, so a test can assert the payload was never even
    fetched for a denied caller.
    """

    def __init__(self, owner, payload=b"", exists=True, raise_on_owner=False):
        self.owner = owner
        self.payload = payload
        self.exists = exists
        self.raise_on_owner = raise_on_owner
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(sql.split()))
        if "FROM sessions" in sql and "user_id" in sql:
            if self.raise_on_owner:
                raise RuntimeError("connection reset")
            self._result = None if not self.exists else (self.owner,)
        elif "FROM budget_payloads" in sql:
            self._result = (self.payload, {}) if self.payload else None
        else:
            self._result = None
        return self

    def fetchone(self):
        return self._result

    def fetchall(self):
        return []


@pytest.fixture
def fake_db(monkeypatch):
    """Install a _FakeConn as db.connect()'s yield, returning a setter for the test."""
    from contextlib import contextmanager

    holder = {}

    @contextmanager
    def _connect(row_factory=None):
        yield holder["conn"]

    monkeypatch.setattr(budget_sessions.db, "connect", _connect)

    def install(**kwargs):
        holder["conn"] = _FakeConn(**kwargs)
        return holder["conn"]

    return install


def _encrypted(session_id: str) -> bytes:
    from shared import crypto

    body = zlib.compress(_frame().to_json(orient="records").encode("utf-8"))
    return crypto.encrypt(body, aad=session_id)


# ── the cross-user read ───────────────────────────────────────────────────────

def test_another_users_session_is_denied(fake_db):
    conn = fake_db(owner=USER_A.user_id, payload=_encrypted(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 404


def test_denial_does_not_fetch_the_payload(fake_db):
    """
    A denied caller must not cause the ciphertext to be read, let alone decrypted.

    Checking the status code alone would pass even if the row were loaded and then
    discarded, which is a different and worse bug.
    """
    conn = fake_db(owner=USER_A.user_id, payload=_encrypted(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException):
            budget_sessions.get_budget_session(SID)

    assert not any("budget_payloads" in q for q in conn.queries)


def test_the_owner_is_served(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted(SID))

    with identity.identity_scope(USER_A):
        df, _ = budget_sessions.get_budget_session(SID)

    assert len(df) == 1
    assert df.iloc[0]["description"] == "SWIGGY"


def test_anonymous_caller_cannot_read_an_owned_session(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted(SID))

    with identity.identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 404


def test_absent_and_denied_are_indistinguishable(fake_db):
    """
    A 403 on someone else's session confirms it exists, which is the signal an
    id-guessing caller wants. Status *and* detail must match the not-found case.
    """
    fake_db(owner=None, exists=False)
    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as absent:
            budget_sessions.get_budget_session(SID)

    fake_db(owner=USER_A.user_id, payload=_encrypted(SID))
    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as denied:
            budget_sessions.get_budget_session(SID)

    assert absent.value.status_code == denied.value.status_code == 404
    assert absent.value.detail == denied.value.detail


def test_ownership_check_fails_closed_when_the_lookup_errors(fake_db):
    """An authorization check that cannot run must not default to allowing access."""
    fake_db(owner=USER_A.user_id, raise_on_owner=True)

    with identity.identity_scope(USER_A):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 503


# ── the cross-user delete ─────────────────────────────────────────────────────

def test_delete_denies_another_users_session(fake_db):
    """
    The payload delete used to run `WHERE session_id = %s` with the owner check only on
    the *second* statement, so a cross-user call destroyed the victim's transactions.
    """
    conn = fake_db(owner=USER_A.user_id)

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.delete_budget_session(USER_B.user_id, SID)

    assert exc.value.status_code == 404
    assert not any("DELETE" in q for q in conn.queries)


def test_delete_removes_the_owners_session(fake_db):
    conn = fake_db(owner=USER_A.user_id)

    with identity.identity_scope(USER_A):
        assert budget_sessions.delete_budget_session(USER_A.user_id, SID) is True

    deletes = [q for q in conn.queries if q.startswith("DELETE")]
    assert len(deletes) == 1
    # Scoped by user_id as well as session_id, so the statement is safe even if the
    # ownership check above were ever removed.
    assert "user_id = %s" in deletes[0]


def test_update_denies_another_users_session(fake_db):
    conn = fake_db(owner=USER_A.user_id, payload=_encrypted(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.update_budget_transactions(
                USER_B.user_id, SID, [{"txn_id": "t1", "category": "Hijacked"}]
            )

    assert exc.value.status_code == 404


# ── the helper that was being misused ─────────────────────────────────────────

def test_owns_record_with_the_callers_own_id_is_a_no_op():
    """
    Pins why the original guard enforced nothing, so nobody reintroduces it.

    Six routers called `identity.owns_record(user_id)` where user_id was the caller's.
    That is caller == caller: always True, for every caller, for every session.
    """
    with identity.identity_scope(USER_B):
        caller = identity.current_user_id()
        assert identity.owns_record(caller) is True          # the no-op
        assert identity.owns_record(USER_A.user_id) is False  # what it should have been
