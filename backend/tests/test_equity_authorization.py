"""
Ownership enforcement for equity sessions.

These are the mutual-fund cases in test_authorization.py, ported to the equity domain.
They are here because the equity module shipped without any of them: get_session()
looked its session up by primary key and returned it, so any caller holding an id -
including an unauthenticated one - read another user's holdings, P&L and capital-gains
estimates across six endpoints. `test_get_session_denies_another_users_session` below
is the direct analogue of the MF test of the same name, and the equity implementation
failed it.

Treat a failure here as a data-leak regression, not a flaky test.
"""

import uuid

import pandas as pd
import pytest
from fastapi import HTTPException

from shared import identity, storage, users
from shared.identity import Caller

from tests.conftest import requires_db, TEST_ISSUER

pytestmark = requires_db


ISSUER = TEST_ISSUER


@pytest.fixture
def user_a(clean_db):
    return users.resolve(ISSUER, "equity-subject-a", email="eq-a@example.test")


@pytest.fixture
def user_b(clean_db):
    return users.resolve(ISSUER, "equity-subject-b", email="eq-b@example.test")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """
    Neutralise the quotes provider.

    equity_quotes owns the only network seam, so stubbing `_download_closes` keeps the
    whole suite offline - and pins that the domain no longer talks to a provider SDK
    directly, because if it did, this stub would not be enough.
    """
    import domains.equity.quotes as eq

    monkeypatch.setattr(eq, "_download_closes", lambda tickers: pd.DataFrame())
    monkeypatch.setattr(eq, "_download_history", lambda tickers, days: pd.DataFrame())
    yield


@pytest.fixture(autouse=True)
def clear_resident_state():
    from domains.equity import sessions as eq_sessions

    eq_sessions.clear_all()
    users.invalidate()
    yield
    eq_sessions.clear_all()
    users.invalidate()


def _holdings(symbol: str = "RELIANCE", qty: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": symbol, "isin": "INE002A01018", "name": symbol, "exchange": "NSE",
        "quantity": qty, "avg_price": 1000.0, "ltp": 1200.0,
        "current_value": qty * 1200.0, "invested": qty * 1000.0,
        "unrealized_pnl": qty * 200.0, "pnl_pct": 20.0,
        "day_change": 5.0, "day_change_pct": 0.4, "broker": "zerodha",
    }])


def _as(caller: Caller):
    return identity.identity_scope(caller)


def _create(owner: Caller, symbol: str = "RELIANCE") -> str:
    from domains.equity import sessions as eq_sessions

    with _as(owner):
        return eq_sessions.create_session(_holdings(symbol), pd.DataFrame(), source="zerodha")


# ── ownership enforcement ─────────────────────────────────────────────────────

def test_get_session_denies_another_users_session(user_a, user_b):
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    eq_sessions.clear_all()  # force the disk path

    with _as(user_b), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    # 404, not 403: a 403 confirms the session exists.
    assert exc.value.status_code == 404

    with _as(user_a):
        assert eq_sessions.get_session(sid) is not None


def test_resident_session_denies_another_user_without_touching_the_database(user_a, user_b):
    """
    The cache-hit path is the one that mattered most: it returned before any database
    round trip, so a check added only to the miss path would not have closed the hole.
    """
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)

    def boom(_sid):
        raise AssertionError("resident hit must not consult the registry")

    original = storage.get_session_owner
    storage.get_session_owner = boom
    try:
        with _as(user_b), pytest.raises(HTTPException) as exc:
            eq_sessions.get_session(sid)
        assert exc.value.status_code == 404
        with _as(user_a):
            assert eq_sessions.get_session(sid) is not None
    finally:
        storage.get_session_owner = original


def test_anonymous_caller_cannot_read_an_owned_session(user_a):
    """
    IdentityMiddleware lets unauthenticated requests through as caller=None, on the
    documented understanding that an anonymous caller "must NOT reach an owned record".
    Equity was the path that let it.
    """
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    eq_sessions.clear_all()

    with identity.identity_scope(None), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_ownership_check_fails_closed_when_the_lookup_errors(user_a, user_b):
    """A storage error must deny with 503, not fall through to allowing access."""
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    eq_sessions.clear_all()

    def boom(_sid):
        raise storage.OwnerLookupFailed("connection lost")

    original = storage.get_session_owner
    storage.get_session_owner = boom
    try:
        with _as(user_b), pytest.raises(HTTPException) as exc:
            eq_sessions.get_session(sid)
        assert exc.value.status_code == 503, (
            "an unverifiable authorization check must not grant access"
        )
    finally:
        storage.get_session_owner = original


def test_resident_session_is_not_readable_after_its_registry_row_is_deleted(user_a, user_b):
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    with _as(user_a):
        assert eq_sessions.get_session(sid) is not None  # resident

    storage.delete_session(sid)

    with _as(user_b), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_unknown_session_raises_404_not_a_bare_valueerror(user_a):
    """
    A missing session used to raise ValueError, which no handler caught - so every
    expired or unknown equity id became a 500 rather than a 404.
    """
    from domains.equity import sessions as eq_sessions

    with _as(user_a), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(str(uuid.uuid4()))
    assert exc.value.status_code == 404


# ── eviction ──────────────────────────────────────────────────────────────────

def test_forget_is_wired_into_history_delete(user_a, client, fake_bearer_auth):
    """
    forget() existed but had no call sites, so DELETE /history/{sid} removed the rows
    and left the portfolio resident - readable by anyone holding the id.
    """
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    with _as(user_a):
        assert eq_sessions.get_session(sid) is not None

    with fake_bearer_auth(user_a):
        res = client.delete(f"/history/{sid}")
    assert res.status_code == 200

    assert eq_sessions.session_stats()["resident"] == 0, (
        "the deleted session is still in memory"
    )


def test_purge_evicts_resident_equity_sessions(user_a):
    from domains.equity import sessions as eq_sessions

    _create(user_a)
    assert eq_sessions.session_stats()["resident"] == 1

    evicted = eq_sessions.evict_for_user(user_a.user_id)
    assert evicted == 1
    assert eq_sessions.session_stats()["resident"] == 0


def test_evict_for_user_does_not_touch_another_user(user_a, user_b):
    from domains.equity import sessions as eq_sessions

    _create(user_a, "RELIANCE")
    _create(user_b, "TCS")
    assert eq_sessions.session_stats()["resident"] == 2

    assert eq_sessions.evict_for_user(user_a.user_id) == 1
    assert eq_sessions.session_stats()["resident"] == 1


# ── session identity ──────────────────────────────────────────────────────────

def test_create_session_returns_an_id_that_actually_exists(user_a):
    """
    create_session used to discard save_session's return value and hand back its own
    uuid. On a duplicate upload that id had no registry row: it worked from cache and
    then 404'd a portfolio the user had just uploaded.
    """
    from domains.equity import sessions as eq_sessions

    sid = _create(user_a)
    exists, owner = storage.get_session_owner(sid)
    assert exists, "create_session returned an id with no registry row"
    assert owner == user_a.user_id


def test_reuploading_the_same_holdings_reuses_the_session(user_a):
    from domains.equity import sessions as eq_sessions

    first = _create(user_a)
    eq_sessions.clear_all()
    second = _create(user_a)
    assert first == second, "an identical holdings upload should dedup, not fork"


def test_identical_holdings_from_two_users_do_not_collide(user_a, user_b):
    sid_a = _create(user_a)
    sid_b = _create(user_b)
    assert sid_a != sid_b, "dedup must be scoped to the owner"


def test_rehydrated_session_keeps_its_broker(user_a):
    """
    load_session returns (holdings, transactions, sips, is_partial). The fourth element
    was unpacked as `meta` and read with `meta.get("source")` behind an
    isinstance(dict) guard that is always False for a bool - so `source` was
    permanently "csv" and a Kite portfolio silently relabelled itself on eviction.
    """
    from domains.equity import sessions as eq_sessions

    with _as(user_a):
        df = _holdings("INFY")
        df["broker"] = "zerodha_kite"
        sid = eq_sessions.create_session(df, pd.DataFrame(), source="zerodha_kite")

    eq_sessions.clear_all()  # force rehydration

    with _as(user_a):
        portfolio = eq_sessions.get_session(sid)
    assert portfolio.source == "zerodha_kite", (
        f"rehydrated as {portfolio.source!r}; the broker did not survive the round trip"
    )
