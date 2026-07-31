"""
Regression tests for the cross-user data-exposure defects found in the
pre-production review.

Each test here corresponds to a specific way one user's financial data could reach
another. They are written to fail loudly on the original bug, so if any of them
starts failing, treat it as a data-leak regression rather than a flaky test.
"""

import sqlite3
import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app
from shared import db, identity, storage

from tests.conftest import requires_db

# Postgres replaced SQLite, so these need a real server. Skipped with a reason rather
# than failing with a connection error when TEST_DATABASE_URL is unset - see
# tests/conftest.py.
pytestmark = requires_db


USER_A = "AAAAA1111A"
USER_B = "BBBBB2222B"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Point storage at a throwaway database.

    These tests write sessions and users, and must not touch the developer's real
    backend/data/metadata.sqlite3 - nor depend on whatever column set its implicit
    mf_* schema happens to be frozen at. Every storage function reads the module
    global at call time, so rebinding it is sufficient.

    One patch covers every store, including the tax one: shared/db.py is the only
    module that names the database. It used to take two, because tax_sessions had its
    own DB_PATH constant pointing at the same file - so patching storage's alone left
    the tax tests writing to the developer's real database.
    """
    from domains.tax_expert import tax_sessions

    path = tmp_path / "test_metadata.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    storage._init_db()
    tax_sessions._init_db()
    tax_sessions.clear_all()
    yield path
    tax_sessions.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_resident_sessions():
    """The in-memory store is process-global; don't let it leak between tests."""
    from domains.mutual_funds import sessions as mf_sessions
    mf_sessions.clear_all()
    yield
    mf_sessions.clear_all()


def _holdings_frame(fund: str = "Test Fund", value: float = 100000.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "Fund": fund, "ISIN": "INF000000001", "Units": 1000.0,
        "NAV": 100.0, "Market Value": value, "Invested": 90000.0,
        "AMC": "Test AMC", "Category": "Flexi Cap", "Type": "Equity",
    }])


def _save(pan: str, df_t: pd.DataFrame, fund: str = "Test Fund") -> str:
    """Persist a session directly through storage, bypassing PDF parsing."""
    sid = str(uuid.uuid4())
    ledger_hash = storage.compute_ledger_hash(df_t, pan)
    return storage.save_session(
        sid, _holdings_frame(fund), df_t, pd.DataFrame(),
        is_partial=False, pan_id=pan, ledger_hash=ledger_hash,
    )


# ── B1: the shared "empty_ledger" hash ────────────────────────────────────────

def test_empty_ledgers_from_different_users_do_not_collide():
    """
    The original bug: a transaction-less CAS hashed to the constant "empty_ledger",
    so the dedup lookup handed the second uploader the first uploader's session.
    """
    empty = pd.DataFrame()

    sid_a = _save(USER_A, empty, fund="A's Fund")
    sid_b = _save(USER_B, empty, fund="B's Fund")

    assert sid_a != sid_b, "two users' empty-ledger uploads collapsed onto one session"


def test_empty_ledger_hash_is_never_a_shared_constant():
    empty = pd.DataFrame()
    first = storage.compute_ledger_hash(empty, USER_A)
    second = storage.compute_ledger_hash(empty, USER_B)
    third = storage.compute_ledger_hash(empty, USER_A)

    assert first != second
    assert first != third, "same-user empty ledgers must not dedup either"
    assert "empty_ledger" not in {first, second, third}


def test_dedup_lookup_is_scoped_to_the_owner():
    """An identical ledger under two PANs must not resolve across them."""
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-01-15"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 100.0, "Amount": 10000.0, "NAV": 100.0,
    }])

    sid_a = _save(USER_A, df_t)

    hash_b = storage.compute_ledger_hash(df_t, USER_B)
    assert storage.check_duplicate_upload(hash_b, USER_B) is None

    hash_a = storage.compute_ledger_hash(df_t, USER_A)
    assert storage.check_duplicate_upload(hash_a, USER_A) == sid_a


def test_same_user_reupload_still_dedups():
    """The optimisation must survive the fix, or every re-upload reprocesses."""
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-02-20"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 50.0, "Amount": 5000.0, "NAV": 100.0,
    }])

    first = _save(USER_A, df_t)
    ledger_hash = storage.compute_ledger_hash(df_t, USER_A)
    assert storage.check_duplicate_upload(ledger_hash, USER_A) == first


# ── B2: ownership enforcement ─────────────────────────────────────────────────

def test_get_session_denies_another_pans_session():
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-03-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 10.0, "Amount": 1000.0, "NAV": 100.0,
    }])
    sid = _save(USER_A, df_t)
    mf_sessions.clear_all()  # force the disk path

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            mf_sessions.get_session(sid)
    # 404, not 403: a 403 would confirm the session exists.
    assert exc.value.status_code == 404

    with identity.identity_scope(USER_A):
        assert mf_sessions.get_session(sid) is not None


def test_ownership_check_fails_closed_when_the_lookup_errors():
    """
    A storage error must DENY, not allow.

    `get_session_owner` used to swallow every exception into `(False, None)`, which the
    caller read as "no registry row, nothing to authorize" and then served the resident
    portfolio. So any SQLite failure disabled authorization entirely — and "database is
    locked" is exactly the condition WAL and busy_timeout were added to handle, making
    the path reachable rather than theoretical.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-04-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 10.0, "Amount": 1000.0, "NAV": 100.0,
    }])
    sid = _save(USER_A, df_t)
    mf_sessions.clear_all()  # force the disk path, where the lookup happens

    def boom(_sid):
        raise storage.OwnerLookupFailed("database is locked")

    original = storage.get_session_owner
    storage.get_session_owner = boom
    try:
        with identity.identity_scope(USER_B):
            with pytest.raises(HTTPException) as exc:
                mf_sessions.get_session(sid)
        assert exc.value.status_code == 503, (
            f"expected 503 (cannot verify), got {exc.value.status_code} — "
            "an unverifiable authorization check must not grant access"
        )
    finally:
        storage.get_session_owner = original


def test_resident_session_is_not_readable_after_its_registry_row_is_deleted():
    """
    Deleting the registry row must not make a resident session world-readable.

    Ownership used to be resolved only from SQLite, and a missing row was treated as
    "nothing to authorize". So after DELETE /history/{sid} or an account purge, the
    portfolio stayed in memory with no row left to name its owner — readable by anyone
    holding the id, including data the user was told had been permanently deleted.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-05-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 5.0, "Amount": 500.0, "NAV": 100.0,
    }])
    sid = _save(USER_A, df_t)

    # Make it resident as its owner, then remove the registry row behind its back.
    with identity.identity_scope(USER_A):
        assert mf_sessions.get_session(sid) is not None
    storage.delete_session(sid)

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            mf_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_purge_evicts_resident_sessions():
    """A purge that leaves the portfolio in memory has not deleted anything."""
    from domains.mutual_funds import sessions as mf_sessions

    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-06-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 7.0, "Amount": 700.0, "NAV": 100.0,
    }])
    sid = _save(USER_A, df_t)
    with identity.identity_scope(USER_A):
        assert mf_sessions.get_session(sid) is not None

    assert mf_sessions.evict_for_pan(USER_A) == 1
    storage.delete_all_for_pan(USER_A)

    from fastapi import HTTPException
    with identity.identity_scope(USER_A):
        with pytest.raises(HTTPException):
            mf_sessions.get_session(sid)


def test_owner_can_read_its_own_session_when_the_header_case_differs():
    """
    The write path must normalize the PAN the same way reads do.

    It stored the raw X-User-PAN header while identity.normalize_pan() upper-cases, so
    a lowercase header produced a session its own owner could not read — and because
    both sides mask to the same string in logs, it would have been undiagnosable.
    """
    from domains.mutual_funds import sessions as mf_sessions

    df_h = _holdings_frame()
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-07-01"), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 3.0, "Amount": 300.0, "NAV": 100.0,
    }])
    # Uploaded with a lowercase header, as a browser could legitimately send it.
    sid = mf_sessions.create_session(
        df_h, df_t, pd.DataFrame(), is_partial=False, pan_id=USER_A.lower()
    )

    exists, owner = storage.get_session_owner(sid)
    assert exists and owner == USER_A, f"owner stored un-normalized: {owner!r}"

    with identity.identity_scope(USER_A):
        assert mf_sessions.get_session(sid) is not None


def test_accounts_summary_only_returns_the_callers_sessions(client):
    empty = pd.DataFrame()
    _save(USER_A, empty, fund="A's Fund")
    _save(USER_B, empty, fund="B's Fund")

    resp = client.get("/accounts/summary", headers={"X-User-PAN": USER_A})
    assert resp.status_code == 200
    pans = {acct["pan"] for acct in resp.json()["accounts"]}
    assert pans <= {USER_A}, f"leaked other PANs: {pans - {USER_A}}"


def test_accounts_summary_requires_identity(client):
    assert client.get("/accounts/summary").status_code == 401


def test_purge_rejects_another_pan(client):
    resp = client.delete(f"/accounts/{USER_B}", headers={"X-User-PAN": USER_A})
    assert resp.status_code == 403


def test_purge_removes_the_user_row_too():
    """A purge that leaves the PAN behind has not deleted "all data"."""
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO users (pan_id) VALUES (?)", (USER_A,))
        conn.commit()

    _save(USER_A, pd.DataFrame())
    storage.delete_all_for_pan(USER_A)

    with sqlite3.connect(db.DB_PATH) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE pan_id = ?", (USER_A,)
        ).fetchone()[0] == 0


# ── identity primitive ────────────────────────────────────────────────────────

def test_owns_record_denies_owned_records_to_anonymous_requests():
    with identity.identity_scope(None):
        assert identity.owns_record(None) is True      # unowned: nobody to protect
        assert identity.owns_record("") is True        # ditto, empty owner
        assert identity.owns_record(USER_A) is False   # owned: must not be readable


def test_owns_record_requires_exact_match():
    with identity.identity_scope(USER_A):
        assert identity.owns_record(USER_A) is True
        assert identity.owns_record(USER_B) is False


def test_owns_record_trusts_in_process_callers_outside_a_request():
    """The GC daemon, migrations and tests are not HTTP callers."""
    assert identity.in_request() is False
    assert identity.owns_record(USER_A) is True


def test_every_http_request_enters_an_identity_scope(client):
    """
    owns_record() grants access to any record when not in a request. That is only
    safe because IdentityMiddleware wraps every HTTP request - so if the middleware
    is ever removed, this test fails rather than the app silently becoming open.
    """
    from main import IdentityMiddleware

    installed = [m.cls for m in app.user_middleware]
    assert IdentityMiddleware in installed, "IdentityMiddleware is not installed"

    # And it must bind a scope even when no header is sent.
    probe = {}

    @app.get("/__identity_probe__")
    def _probe():
        probe["in_request"] = identity.in_request()
        probe["pan"] = identity.current_pan()
        return {"ok": True}

    try:
        assert client.get("/__identity_probe__").status_code == 200
        assert probe["in_request"] is True
        assert probe["pan"] is None

        client.get("/__identity_probe__", headers={"X-User-PAN": USER_A})
        assert probe["pan"] == USER_A
    finally:
        app.router.routes = [
            r for r in app.router.routes
            if getattr(r, "path", None) != "/__identity_probe__"
        ]


def test_identity_scope_does_not_leak():
    with identity.identity_scope(USER_A):
        assert identity.current_pan() == USER_A
    assert identity.current_pan() is None
    assert identity.in_request() is False


def test_malformed_pan_header_is_treated_as_anonymous():
    assert identity.normalize_pan("not-a-pan") is None
    assert identity.normalize_pan("") is None
    assert identity.normalize_pan("  aaaaa1111a  ") == USER_A


def test_mask_pan_keeps_only_the_tail():
    masked = identity.mask_pan(USER_A)
    assert USER_A not in masked
    assert masked.endswith(USER_A[-4:])


# ── B3: endpoints that took a PAN from the request instead of from identity ───
#
# Both of these read a caller-supplied PAN directly - one from the request body, one
# from the raw header - rather than from the identity scope. They are grouped because
# they are the same defect twice: the value deciding *whose* data is touched came from
# somewhere a caller controls, with no check that it is theirs.

def _make_tax_session(pan: str, name: str = "Test User") -> str:
    from domains.tax_expert import tax_sessions
    return tax_sessions.create_tax_session(
        {"personal": {"pan": pan, "name": name}, "fy": "2025-26",
         "salary": {"gross": 1200000}},
        pan_id=pan,
    )


def test_logout_cannot_delete_another_users_tax_sessions(client):
    """
    The original bug: POST /auth/logout took the PAN from the request body and
    delete_tax_session performs no ownership check, so any caller could name a
    victim's PAN and destroy their tax sessions from memory *and* disk.
    """
    from domains.tax_expert import tax_sessions

    victim_sid = _make_tax_session(USER_B, name="Victim")

    resp = client.post(
        "/auth/logout",
        json={"pan": USER_B},                 # attacker names the victim
        headers={"X-User-PAN": USER_A},       # but authenticates as themselves
    )
    assert resp.status_code == 200

    assert tax_sessions.get_tax_session(victim_sid) is not None, \
        "logout honoured a body-supplied PAN and deleted another user's session"


def test_logout_requires_identity(client):
    assert client.post("/auth/logout", json={"pan": USER_A}).status_code == 401


def test_logout_still_clears_the_callers_own_sessions(client):
    """The fix must not turn logout into a no-op."""
    from domains.tax_expert import tax_sessions

    own_sid = _make_tax_session(USER_A)

    resp = client.post("/auth/logout", json={"pan": USER_A}, headers={"X-User-PAN": USER_A})
    assert resp.status_code == 200

    with identity.identity_scope(USER_A):
        assert tax_sessions.get_tax_session(own_sid) is None


def test_tax_history_requires_identity(client):
    """
    Previously returned {"sessions": []} with no header, which a client cannot
    distinguish from "you have no saved sessions".
    """
    assert client.get("/tax-expert/tax-history").status_code == 401


def test_tax_history_does_not_leak_another_users_sessions(client):
    _make_tax_session(USER_A, name="A")
    _make_tax_session(USER_B, name="B")

    resp = client.get("/tax-expert/tax-history", headers={"X-User-PAN": USER_A})
    assert resp.status_code == 200

    pans = {s["pan"].upper() for s in resp.json()["sessions"]}
    assert pans <= {USER_A}, f"leaked other PANs: {pans - {USER_A}}"


def test_tax_history_normalizes_the_header_like_every_other_route(client):
    """
    The endpoint used the raw header, so a lower-case PAN matched nothing while the
    same header authenticated fine everywhere else.
    """
    _make_tax_session(USER_A, name="A")

    resp = client.get("/tax-expert/tax-history", headers={"X-User-PAN": USER_A.lower()})
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) == 1
