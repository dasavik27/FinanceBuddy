"""
Regression tests for the cross-user data-exposure defects found in review, ported to
the user_id ownership model.

Each test corresponds to a specific way one user's financial data could reach another.
They are written to fail loudly on the original bug, so if any starts failing, treat
it as a data-leak regression rather than a flaky test.

Two properties are new here and matter more than anything else in the file:

  - Ownership is a uuid this application issues, not a PAN. A PAN is printed on
    financial documents, so while it was the owner column, knowing one was enough to
    read that user's data. `test_pan_is_not_identity` pins that it no longer is.
  - Provider identity is (issuer, subject) mapped through `identities`, so the same
    person arriving via a second provider can be linked without re-keying anything,
    and two providers' subjects cannot collide.
"""

import uuid

import pandas as pd
import pytest

from main import app
from shared import db, identity, storage, users
from shared.identity import Caller

from tests.conftest import requires_db, TEST_ISSUER

pytestmark = requires_db


PAN_A = "AAAAA1111A"
PAN_B = "BBBBB2222B"

ISSUER = TEST_ISSUER
SUBJECT_A = "subject-a"
SUBJECT_B = "subject-b"


@pytest.fixture
def user_a(clean_db):
    return users.resolve(ISSUER, SUBJECT_A, email="a@example.test", pan=PAN_A)


@pytest.fixture
def user_b(clean_db):
    return users.resolve(ISSUER, SUBJECT_B, email="b@example.test", pan=PAN_B)


@pytest.fixture(autouse=True)
def clear_resident_state():
    """Process-global stores must not leak between tests."""
    from domains.mutual_funds import sessions as mf_sessions
    from domains.tax_expert import tax_sessions

    mf_sessions.clear_all()
    tax_sessions.clear_all()
    users.invalidate()
    yield
    mf_sessions.clear_all()
    tax_sessions.clear_all()
    users.invalidate()


def _holdings_frame(fund: str = "Test Fund", value: float = 100000.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "Fund": fund, "ISIN": "INF000000001", "Units": 1000.0,
        "NAV": 100.0, "Market Value": value, "Invested": 90000.0,
        "AMC": "Test AMC", "Category": "Flexi Cap", "Type": "Equity",
    }])


def _ledger(day: str = "2024-01-15") -> pd.DataFrame:
    return pd.DataFrame([{
        "Date": pd.Timestamp(day), "Fund": "Test Fund",
        "Type": "Purchase", "Units": 100.0, "Amount": 10000.0, "NAV": 100.0,
    }])


def _save(owner_id, df_t: pd.DataFrame, fund: str = "Test Fund") -> str:
    """Persist a session directly through storage, bypassing PDF parsing."""
    sid = str(uuid.uuid4())
    ledger_hash = storage.compute_ledger_hash(df_t, owner_id)
    return storage.save_session(
        sid, _holdings_frame(fund), df_t, pd.DataFrame(),
        is_partial=False, user_id=owner_id, ledger_hash=ledger_hash,
    )


def _as(caller: Caller):
    return identity.identity_scope(caller)


# ── the identity model itself ─────────────────────────────────────────────────

def test_pan_is_not_identity(clean_db):
    """
    Two accounts carrying the *same* PAN must not see each other's data.

    This is the defect the whole re-key exists to close. While PAN was the owner
    column, presenting one was sufficient to read everything filed under it - and a
    PAN is printed on documents rather than being a secret. It is now profile data,
    so a collision (a shared family PAN, a typo, a guess) carries no authority.
    """
    one = users.resolve(ISSUER, "subject-one", pan=PAN_A)
    two = users.resolve(ISSUER, "subject-two", pan=PAN_A)

    assert one.user_id != two.user_id, "one PAN collapsed two accounts into one"
    assert one.pan == two.pan == PAN_A

    sid = _save(one.user_id, _ledger())
    with _as(two):
        assert identity.owns_record(one.user_id) is False
    assert storage.get_session_owner(sid)[1] == one.user_id


def test_the_same_subject_always_resolves_to_the_same_account(clean_db):
    """Provisioning is idempotent, or every login would create a new account."""
    assert users.resolve(ISSUER, "stable").user_id == users.resolve(ISSUER, "stable").user_id


def test_subjects_from_different_issuers_do_not_collide(clean_db):
    """
    identities is keyed on (issuer, subject), not subject alone.

    Providers pick their own subject format and two can legitimately issue the same
    string. Keyed on subject alone, adding a second provider would silently merge
    unrelated people's accounts.
    """
    google = users.resolve("https://accounts.google.com", "12345")
    other = users.resolve("https://other-idp.test", "12345")
    assert google.user_id != other.user_id


def test_a_second_provider_can_be_linked_without_re_keying(clean_db):
    """
    The point of the indirection: one account, reachable through two providers.

    Switching or adding a provider must be an INSERT into identities, never a
    migration of every table carrying an owner column.
    """
    original = users.resolve(ISSUER, "person-1")
    sid = _save(original.user_id, _ledger())

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO identities (issuer, subject, user_id) VALUES (%s, %s, %s)",
            ("https://accounts.google.com", "google-person-1", original.user_id),
        )
    users.invalidate()

    via_google = users.resolve("https://accounts.google.com", "google-person-1")
    assert via_google.user_id == original.user_id

    with _as(via_google):
        assert identity.owns_record(storage.get_session_owner(sid)[1]) is True


# ── dedup is scoped to the owner ──────────────────────────────────────────────

def test_empty_ledgers_from_different_users_do_not_collide(user_a, user_b):
    """
    A transaction-less CAS hashed to the constant "empty_ledger", so every one of
    them collided and the dedup lookup handed the second uploader the first
    uploader's session.
    """
    empty = pd.DataFrame()
    assert _save(user_a.user_id, empty, "A's Fund") != _save(user_b.user_id, empty, "B's Fund")


def test_empty_ledger_hash_is_never_a_shared_constant(user_a, user_b):
    empty = pd.DataFrame()
    first = storage.compute_ledger_hash(empty, user_a.user_id)
    second = storage.compute_ledger_hash(empty, user_b.user_id)
    third = storage.compute_ledger_hash(empty, user_a.user_id)

    assert first != second
    assert first != third, "same-user empty ledgers must not dedup either"
    assert "empty_ledger" not in {first, second, third}


def test_dedup_lookup_is_scoped_to_the_owner(user_a, user_b):
    """An identical ledger under two accounts must not resolve across them."""
    df_t = _ledger()
    sid_a = _save(user_a.user_id, df_t)

    hash_b = storage.compute_ledger_hash(df_t, user_b.user_id)
    assert storage.check_duplicate_upload(hash_b, user_b.user_id) is None

    hash_a = storage.compute_ledger_hash(df_t, user_a.user_id)
    assert storage.check_duplicate_upload(hash_a, user_a.user_id) == sid_a


def test_same_user_reupload_still_dedups(user_a):
    """The optimisation must survive the fix, or every re-upload reprocesses."""
    df_t = _ledger("2024-02-20")
    first = _save(user_a.user_id, df_t)
    assert storage.check_duplicate_upload(
        storage.compute_ledger_hash(df_t, user_a.user_id), user_a.user_id
    ) == first


# ── ownership enforcement ─────────────────────────────────────────────────────

def test_get_session_denies_another_users_session(user_a, user_b):
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    sid = _save(user_a.user_id, _ledger("2024-03-01"))
    mf_sessions.clear_all()  # force the disk path

    with _as(user_b), pytest.raises(HTTPException) as exc:
        mf_sessions.get_session(sid)
    # 404, not 403: a 403 would confirm the session exists.
    assert exc.value.status_code == 404

    with _as(user_a):
        assert mf_sessions.get_session(sid) is not None


def test_ownership_check_fails_closed_when_the_lookup_errors(user_a, user_b):
    """
    A storage error must DENY, not allow.

    get_session_owner used to swallow every exception into (False, None), which the
    caller read as "no registry row, nothing to authorize" and then served the
    resident portfolio - so any database failure disabled authorization entirely.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    sid = _save(user_a.user_id, _ledger("2024-04-01"))
    mf_sessions.clear_all()

    def boom(_sid):
        raise storage.OwnerLookupFailed("connection lost")

    original = storage.get_session_owner
    storage.get_session_owner = boom
    try:
        with _as(user_b), pytest.raises(HTTPException) as exc:
            mf_sessions.get_session(sid)
        assert exc.value.status_code == 503, (
            f"expected 503 (cannot verify), got {exc.value.status_code} - "
            "an unverifiable authorization check must not grant access"
        )
    finally:
        storage.get_session_owner = original


def test_resident_session_is_not_readable_after_its_registry_row_is_deleted(user_a, user_b):
    """
    Ownership used to resolve only from the registry, and a missing row was treated
    as unowned - so deleting the row made the still-resident portfolio readable by
    anyone holding its id.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    sid = _save(user_a.user_id, _ledger("2024-05-01"))
    with _as(user_a):
        assert mf_sessions.get_session(sid) is not None  # now resident

    storage.delete_session(sid)

    with _as(user_b), pytest.raises(HTTPException) as exc:
        mf_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_purge_evicts_resident_sessions(user_a):
    """
    Dropping only the rows left portfolios resident, so data the user was told had
    been permanently deleted stayed readable for up to the session TTL.
    """
    from domains.mutual_funds import sessions as mf_sessions
    from fastapi import HTTPException

    sid = _save(user_a.user_id, _ledger("2024-06-01"))
    with _as(user_a):
        assert mf_sessions.get_session(sid) is not None

    mf_sessions.evict_for_user(user_a.user_id)
    storage.delete_all_for_user(user_a.user_id)

    with _as(user_a), pytest.raises(HTTPException):
        mf_sessions.get_session(sid)


def test_purge_removes_the_account_row_too(user_a):
    """A purge that leaves the account behind has not deleted "all data"."""
    _save(user_a.user_id, pd.DataFrame())
    storage.delete_all_for_user(user_a.user_id)

    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE id = %s", (user_a.user_id,)
        ).fetchone()[0] == 0
        # identities and profiles cascade; nothing identifying may survive.
        assert conn.execute(
            "SELECT COUNT(*) FROM identities WHERE user_id = %s", (user_a.user_id,)
        ).fetchone()[0] == 0


# ── routes ────────────────────────────────────────────────────────────────────

def test_accounts_summary_only_returns_the_callers_sessions(user_a, user_b, client, fake_bearer_auth):
    _save(user_a.user_id, _ledger("2024-07-01"), "A's Fund")
    _save(user_b.user_id, _ledger("2024-07-02"), "B's Fund")

    resp = client.get("/accounts/summary", headers=fake_bearer_auth(SUBJECT_A))
    assert resp.status_code == 200

    ids = {account["user_id"] for account in resp.json()["accounts"]}
    assert ids <= {user_a.user_id}, f"leaked other accounts: {ids - {user_a.user_id}}"


def test_accounts_summary_requires_identity(client, clean_db):
    assert client.get("/accounts/summary").status_code == 401


def test_purge_only_ever_targets_the_caller(user_a, user_b, client, fake_bearer_auth):
    """
    The endpoint is /accounts/me and takes no target.

    It used to be /accounts/{pan}, whose correctness depended on remembering to
    compare the path against the caller. There is now no way to name someone else.
    """
    _save(user_b.user_id, _ledger("2024-08-01"))

    assert client.delete("/accounts/me", headers=fake_bearer_auth(SUBJECT_A)).status_code == 200

    with db.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user_b.user_id,)
        ).fetchone()[0] == 1, "purging one account destroyed another's data"


def test_purge_requires_identity(client, clean_db):
    assert client.delete("/accounts/me").status_code == 401


# ── logout and tax history ────────────────────────────────────────────────────

def _make_tax_session(caller: Caller, name: str = "Test User") -> str:
    from domains.tax_expert import tax_sessions
    with _as(caller):
        return tax_sessions.create_tax_session({
            "personal": {"pan": caller.pan, "name": name},
            "fy": "2025-26",
            "salary": {"gross": 1200000},
        })


def test_logout_only_ever_affects_the_caller(user_a, user_b, client, fake_bearer_auth):
    """
    Logout takes the account from the request identity, full stop - there is no
    field anywhere in the request that could name a different account. It used to
    take a PAN from the request body with no ownership check on the delete, so any
    caller could name a victim and destroy their tax sessions.
    """
    from domains.tax_expert import tax_sessions

    victim_sid = _make_tax_session(user_b, name="Victim")

    resp = client.post("/auth/logout", headers=fake_bearer_auth(SUBJECT_A))
    assert resp.status_code == 200

    with _as(user_b):
        assert tax_sessions.get_tax_session(victim_sid) is not None, \
            "logging out as one account touched another account's data"


def test_logout_does_not_destroy_the_callers_stored_history(user_a, client, fake_bearer_auth):
    """
    Signing out evicts from memory only.

    It used to delete from disk as well - survivable when the filesystem was wiped on
    every deploy, straightforward data loss now that storage is durable.
    """
    from domains.tax_expert import tax_sessions

    sid = _make_tax_session(user_a)
    assert client.post("/auth/logout", headers=fake_bearer_auth(SUBJECT_A)).status_code == 200

    with _as(user_a):
        assert tax_sessions.get_tax_session(sid) is not None, \
            "logout deleted stored history instead of evicting the cache"


def test_logout_requires_identity(client, clean_db):
    assert client.post("/auth/logout").status_code == 401


def test_tax_history_requires_identity(client, clean_db):
    """Previously returned {"sessions": []}, indistinguishable from "you have none"."""
    assert client.get("/tax-expert/tax-history").status_code == 401


def test_tax_history_does_not_leak_another_users_sessions(user_a, user_b, client, fake_bearer_auth):
    _make_tax_session(user_a, name="A")
    _make_tax_session(user_b, name="B")

    resp = client.get("/tax-expert/tax-history", headers=fake_bearer_auth(SUBJECT_A))
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) == 1


def test_tax_history_finds_sessions_that_are_not_resident(user_a, client, fake_bearer_auth):
    """
    The listing is a database query, not a scan of the in-memory store.

    It used to read the resident dict - capped at 8, and populated at cold start from
    the newest rows across *all* users - so a user's own older sessions sat on disk
    and were invisible to their history.
    """
    from domains.tax_expert import tax_sessions

    sid = _make_tax_session(user_a)
    tax_sessions.clear_all()  # nothing resident

    resp = client.get("/tax-expert/tax-history", headers=fake_bearer_auth(SUBJECT_A))
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert [s["session_id"] for s in sessions] == [sid]
    assert sessions[0]["created_at"], "history rows must carry a timestamp to sort by"


# ── identity primitive ────────────────────────────────────────────────────────

def test_owns_record_denies_owned_records_to_anonymous_requests():
    with identity.identity_scope(None):
        assert identity.owns_record(None) is True      # unowned: nobody to protect
        assert identity.owns_record("") is True        # ditto
        assert identity.owns_record("some-user-id") is False


def test_owns_record_requires_exact_match():
    a = Caller(user_id="11111111-1111-1111-1111-111111111111")
    with identity.identity_scope(a):
        assert identity.owns_record(a.user_id) is True
        assert identity.owns_record("22222222-2222-2222-2222-222222222222") is False


def test_owns_record_trusts_in_process_callers_outside_a_request():
    """The GC daemon, migrations and tests are not HTTP callers."""
    assert identity.in_request() is False
    assert identity.owns_record("anything") is True


def test_every_http_request_enters_an_identity_scope(client, clean_db, fake_bearer_auth):
    """
    owns_record() grants access to any record when not in a request. That is only
    safe because IdentityMiddleware wraps every HTTP request - so if the middleware
    is ever removed, this fails rather than the app silently becoming open.
    """
    from main import IdentityMiddleware

    assert IdentityMiddleware in [m.cls for m in app.user_middleware], \
        "IdentityMiddleware is not installed"

    probe = {}

    @app.get("/__identity_probe__")
    def _probe():
        probe["in_request"] = identity.in_request()
        probe["user_id"] = identity.current_user_id()
        return {"ok": True}

    try:
        assert client.get("/__identity_probe__").status_code == 200
        assert probe["in_request"] is True
        assert probe["user_id"] is None, "an unauthenticated request must be anonymous"

        client.get("/__identity_probe__", headers=fake_bearer_auth("probe-subject"))
        assert probe["user_id"] is not None, "a verified bearer token must resolve to an account"
    finally:
        app.router.routes = [
            r for r in app.router.routes
            if getattr(r, "path", None) != "/__identity_probe__"
        ]


def test_identity_scope_does_not_leak():
    with identity.identity_scope(Caller(user_id="abc")):
        assert identity.current_user_id() == "abc"
    assert identity.current_user_id() is None
    assert identity.in_request() is False


def test_malformed_pan_is_rejected():
    assert identity.normalize_pan("not-a-pan") is None
    assert identity.normalize_pan("") is None
    assert identity.normalize_pan("  aaaaa1111a  ") == PAN_A


def test_mask_pan_keeps_only_the_tail():
    masked = identity.mask_pan(PAN_A)
    assert PAN_A not in masked
    assert masked.endswith(PAN_A[-4:])
