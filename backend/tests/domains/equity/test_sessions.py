
"""Equity session storage, encoding, and ownership."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException

from domains.equity import sessions as eq_sessions
from domains.equity.models import EquityPortfolio
from shared.identity import Caller, identity_scope
from shared.services.cache import DERIVED_CACHE, MARKET_CACHE

CALLER = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")


@pytest.fixture(autouse=True)
def _clear_state():
    MARKET_CACHE.clear()
    DERIVED_CACHE.clear()
    eq_sessions.clear_all()
    yield
    MARKET_CACHE.clear()
    DERIVED_CACHE.clear()
    eq_sessions.clear_all()


def _holdings_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "symbol": "RELIANCE", "quantity": 10.0, "avg_price": 1000.0, "ltp": 1200.0,
            "current_value": 12000.0, "invested": 10000.0, "unrealized_pnl": 2000.0,
            "pnl_pct": 20.0, "day_change": 50.0, "day_change_pct": 0.5,
            "exchange": "NSE", "name": "Reliance", "isin": "INE002A01018", "broker": "zerodha",
            "sector": "Energy", "industry": "Oil & Gas",
        },
    ])


def test_equity_sessions_create_and_get(monkeypatch):
    mock_storage = MagicMock()
    mock_storage.check_duplicate_upload.return_value = None
    mock_storage.save_session.return_value = "sess-new"
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)

    with identity_scope(CALLER):
        sid = eq_sessions.create_session(_holdings_df(), pd.DataFrame(), source="csv")
    assert sid == "sess-new"

    portfolio = EquityPortfolio(_holdings_df())
    eq_sessions._remember("sess-1", portfolio, owner=CALLER.user_id)

    with identity_scope(CALLER):
        got = eq_sessions.get_session("sess-1")
    assert got.df_holdings.iloc[0]["symbol"] == "RELIANCE"

    with identity_scope(Caller(user_id="bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")):
        with pytest.raises(HTTPException) as exc:
            eq_sessions.get_session("sess-1")
        assert exc.value.status_code == 404

def test_equity_sessions_expiry(monkeypatch):
    portfolio = EquityPortfolio(_holdings_df())
    eq_sessions._remember("expired", portfolio, owner=CALLER.user_id)
    with eq_sessions._SESSIONS_LOCK:
        eq_sessions._SESSIONS["expired"]["last_accessed"] = datetime.now() - timedelta(hours=5)

    mock_storage = MagicMock()
    mock_storage.get_session_owner.return_value = (False, None)
    mock_storage.load_session.return_value = None
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)

    with identity_scope(CALLER):
        with pytest.raises(HTTPException):
            eq_sessions.get_session("expired")

def test_equity_sessions_lifecycle(monkeypatch):
    mock_storage = MagicMock()
    mock_storage.check_duplicate_upload.return_value = "dup-sid"
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)

    with identity_scope(CALLER):
        sid = eq_sessions.create_session(_holdings_df(), pd.DataFrame(), source="csv")
    assert sid == "dup-sid"

    mock_storage.check_duplicate_upload.return_value = None
    mock_storage.save_session.return_value = "saved-sid"
    mock_storage.get_session_owner.return_value = (True, CALLER.user_id)
    mock_storage.load_session.return_value = (_holdings_df(), pd.DataFrame(), pd.DataFrame(), False)

    with identity_scope(CALLER):
        sid2 = eq_sessions.create_session(_holdings_df(), pd.DataFrame(), source="csv")
    assert sid2 == "saved-sid"

    with identity_scope(CALLER):
        got = eq_sessions.get_session(sid2)
    assert got.df_holdings.iloc[0]["symbol"] == "RELIANCE"

    mock_storage.get_session_owner.return_value = (True, CALLER.user_id)
    mock_storage.load_session.return_value = None
    with identity_scope(CALLER):
        with pytest.raises(HTTPException):
            eq_sessions.get_session("missing-on-disk")

def test_equity_sessions_owner_lookup_failed(monkeypatch):
    from shared.storage import OwnerLookupFailed

    mock_storage = MagicMock()
    mock_storage.OwnerLookupFailed = OwnerLookupFailed
    mock_storage.get_session_owner.side_effect = OwnerLookupFailed
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)
    eq_sessions.clear_all()

    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            eq_sessions.get_session("disk-only")
        assert exc.value.status_code == 503

def test_equity_sessions_compact_evict_and_stats(monkeypatch):
    eq_sessions.clear_all()
    df = pd.DataFrame([{
        "symbol": "A", "sector": "Energy", "industry": "Oil", "exchange": "NSE",
        "broker": "csv", "quantity": 1, "avg_price": 1.0,
    }] * 20)
    eq_sessions._compact_dtypes(df)
    assert "sector" in df.columns

    numeric = pd.DataFrame({"sector": [1, 2, 3]})
    eq_sessions._compact_dtypes(numeric)

    bad = pd.DataFrame({"sector": [object(), object()]})
    eq_sessions._compact_dtypes(bad)

    real_hash = pd.util.hash_pandas_object

    def flaky(df, **kwargs):
        raise RuntimeError("unhashable")

    monkeypatch.setattr(pd.util, "hash_pandas_object", flaky)
    h = eq_sessions._equity_ledger_hash(df, pd.DataFrame(), CALLER.user_id)
    assert len(h) == 64
    monkeypatch.setattr(pd.util, "hash_pandas_object", real_hash)

    portfolio = EquityPortfolio(_holdings_df())
    eq_sessions._remember("s1", portfolio, owner=CALLER.user_id)
    eq_sessions._remember("s2", portfolio, owner=CALLER.user_id)

    assert eq_sessions.forget("s1") is True
    assert eq_sessions.forget("missing") is False
    eq_sessions._remember("s3", portfolio, owner=CALLER.user_id)
    assert eq_sessions.evict_for_user(CALLER.user_id) >= 1
    eq_sessions._remember("s5", portfolio, owner=CALLER.user_id)
    with eq_sessions._SESSIONS_LOCK:
        eq_sessions._SESSIONS["s5"]["last_accessed"] = datetime.now() - timedelta(hours=5)
    assert eq_sessions.purge_expired() >= 1
    stats = eq_sessions.session_stats()
    assert "resident" in stats
    assert eq_sessions.clear_all() >= 0

    entry = {"created_at": datetime.now()}
    assert eq_sessions._expired(entry) is False

def test_equity_sessions_disk_rehydrate_and_create_errors(monkeypatch):
    from shared.storage import OwnerLookupFailed

    mock_storage = MagicMock()
    mock_storage.OwnerLookupFailed = OwnerLookupFailed
    mock_storage.check_duplicate_upload.return_value = None
    mock_storage.save_session.return_value = "disk-sid"
    mock_storage.get_session_owner.return_value = (True, CALLER.user_id)
    mock_storage.load_session.return_value = (_holdings_df(), pd.DataFrame(), pd.DataFrame(), False)
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)
    eq_sessions.clear_all()

    def boom_prices():
        raise RuntimeError("quotes down")

    with identity_scope(CALLER):
        monkeypatch.setattr(
            "domains.equity.models.EquityPortfolio.update_live_prices", boom_prices
        )
        sid = eq_sessions.create_session(_holdings_df(), pd.DataFrame(), source="csv")
    assert sid == "disk-sid"

    eq_sessions.clear_all()
    with identity_scope(CALLER):
        got = eq_sessions.get_session("disk-sid")
    assert got.df_holdings.iloc[0]["symbol"] == "RELIANCE"

    mock_storage.get_session_owner.return_value = (False, None)
    eq_sessions.clear_all()
    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            eq_sessions.get_session("gone")
        assert exc.value.status_code == 404

def test_equity_sessions_category_and_denial(monkeypatch):
    from shared.storage import OwnerLookupFailed

    cat_df = pd.DataFrame({"sector": pd.Series(["Energy", "Energy"], dtype="category")})
    eq_sessions._compact_dtypes(cat_df)

    df = pd.DataFrame([{
        "symbol": "A", "sector": "Energy", "industry": "Oil", "exchange": "NSE",
        "broker": "csv", "quantity": 1, "avg_price": 1.0,
    }] * 20)
    eq_sessions._compact_dtypes(df)

    mock_storage = MagicMock()
    mock_storage.OwnerLookupFailed = OwnerLookupFailed
    mock_storage.get_session_owner.return_value = (True, "other-user")
    monkeypatch.setattr(eq_sessions, "storage", mock_storage)
    eq_sessions.clear_all()

    with identity_scope(CALLER):
        with pytest.raises(HTTPException) as exc:
            eq_sessions.get_session("foreign")
        assert exc.value.status_code == 404

    old_cap = eq_sessions.MAX_RESIDENT_SESSIONS
    monkeypatch.setattr(eq_sessions, "MAX_RESIDENT_SESSIONS", 1)
    eq_sessions.clear_all()
    portfolio = EquityPortfolio(_holdings_df())
    eq_sessions._remember("a", portfolio, owner=CALLER.user_id)
    eq_sessions._remember("b", portfolio, owner=CALLER.user_id)
    monkeypatch.setattr(eq_sessions, "MAX_RESIDENT_SESSIONS", old_cap)

    assert eq_sessions._expired({}) is False

    class BadSeries(pd.Series):
        def astype(self, *args, **kwargs):
            raise TypeError("cannot convert")

    bad_df = pd.DataFrame({"sector": list(BadSeries(["Energy"] * 20))})
    eq_sessions._compact_dtypes(bad_df)


"""
Ownership enforcement for equity sessions, without a database.

test_equity_authorization.py covers the same ground end-to-end, but it skips unless
TEST_DATABASE_URL is set - which meant the single most important property in the module
had no coverage at all on a default checkout. This file stubs the storage layer so the
authorization *decision* is exercised everywhere, infrastructure or not.

What is pinned here is narrow and deliberate: given an owner, does get_session grant or
deny, on both the resident and the rehydration path, and does it fail closed when it
cannot tell.
"""

import pandas as pd
import pytest

from fastapi import HTTPException

from shared import identity, storage
from shared.identity import Caller

# Hex letters on purpose: an all-digit uuid makes `.upper()` a no-op, which would make
# test_evict_for_user_matches_the_owner_exactly pass without testing anything.
USER_A = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
USER_B = Caller(user_id="bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")

SID = "session-under-test"


@pytest.fixture(autouse=True)
def clean_store():
    from domains.equity import sessions as eq_sessions

    eq_sessions.clear_all()
    yield
    eq_sessions.clear_all()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import domains.equity.quotes as eq

    monkeypatch.setattr(eq, "_download_closes", lambda tickers: pd.DataFrame())


def _holdings() -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": "RELIANCE", "quantity": 10.0, "avg_price": 1000.0, "ltp": 1200.0,
        "current_value": 12000.0, "invested": 10000.0, "unrealized_pnl": 2000.0,
        "pnl_pct": 20.0, "day_change": 0.0, "day_change_pct": 0.0,
        "exchange": "NSE", "name": "Reliance", "isin": "INE002A01018", "broker": "zerodha",
    }])


def _make_resident(owner: Caller):
    """Put a portfolio in the resident store owned by `owner`, without touching storage."""
    from domains.equity import sessions as eq_sessions
    from domains.equity.models import EquityPortfolio

    portfolio = EquityPortfolio(_holdings(), pd.DataFrame(), source="zerodha")
    eq_sessions._remember(SID, portfolio, owner=owner.user_id)
    return portfolio


def _stub_disk(monkeypatch, owner: str | None, exists: bool = True):
    """Make the rehydration path resolve to `owner` without a database."""
    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (exists, owner))
    monkeypatch.setattr(
        storage, "load_session",
        lambda sid: (_holdings(), pd.DataFrame(), pd.DataFrame(), False),
    )


# ── resident path ─────────────────────────────────────────────────────────────

def test_resident_hit_serves_the_owner():
    from domains.equity import sessions as eq_sessions

    portfolio = _make_resident(USER_A)
    with identity.identity_scope(USER_A):
        assert eq_sessions.get_session(SID) is portfolio


def test_resident_hit_denies_a_different_user():
    from domains.equity import sessions as eq_sessions

    _make_resident(USER_A)
    with identity.identity_scope(USER_B), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 404


def test_resident_hit_denies_an_anonymous_caller():
    from domains.equity import sessions as eq_sessions

    _make_resident(USER_A)
    with identity.identity_scope(None), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 404


def test_resident_denial_does_not_consult_storage(monkeypatch):
    """
    The cache path returned before any database round trip, so a check added only to
    the miss path would have left the hole wide open. This pins that the resident path
    authorizes on its own.
    """
    from domains.equity import sessions as eq_sessions

    def boom(_sid):
        raise AssertionError("resident path must not need the registry")

    monkeypatch.setattr(storage, "get_session_owner", boom)
    _make_resident(USER_A)

    with identity.identity_scope(USER_B), pytest.raises(HTTPException):
        eq_sessions.get_session(SID)


# ── rehydration path ──────────────────────────────────────────────────────────

def test_rehydration_serves_the_owner(monkeypatch):
    from domains.equity import sessions as eq_sessions

    _stub_disk(monkeypatch, owner=USER_A.user_id)
    with identity.identity_scope(USER_A):
        assert eq_sessions.get_session(SID) is not None


def test_rehydration_denies_a_different_user(monkeypatch):
    from domains.equity import sessions as eq_sessions

    _stub_disk(monkeypatch, owner=USER_A.user_id)
    with identity.identity_scope(USER_B), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 404


def test_rehydration_denies_an_anonymous_caller(monkeypatch):
    from domains.equity import sessions as eq_sessions

    _stub_disk(monkeypatch, owner=USER_A.user_id)
    with identity.identity_scope(None), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 404


def test_missing_session_is_404(monkeypatch):
    from domains.equity import sessions as eq_sessions

    _stub_disk(monkeypatch, owner=None, exists=False)
    with identity.identity_scope(USER_A), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 404


def test_owner_lookup_failure_denies_with_503(monkeypatch):
    """An authorization check that cannot run must not default to allowing access."""
    from domains.equity import sessions as eq_sessions

    def boom(_sid):
        raise storage.OwnerLookupFailed("connection lost")

    monkeypatch.setattr(storage, "get_session_owner", boom)
    with identity.identity_scope(USER_B), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(SID)
    assert exc.value.status_code == 503


def test_denial_does_not_reveal_whether_the_session_exists(monkeypatch):
    """
    404 and not 403, with the same body either way: a 403 confirms the id is real,
    which is precisely the signal an id-guessing caller wants.
    """
    from domains.equity import sessions as eq_sessions

    _stub_disk(monkeypatch, owner=USER_A.user_id)
    with identity.identity_scope(USER_B), pytest.raises(HTTPException) as denied:
        eq_sessions.get_session(SID)

    _stub_disk(monkeypatch, owner=None, exists=False)
    with identity.identity_scope(USER_B), pytest.raises(HTTPException) as absent:
        eq_sessions.get_session("no-such-session")

    assert denied.value.status_code == absent.value.status_code == 404
    assert denied.value.detail == absent.value.detail


# ── eviction ──────────────────────────────────────────────────────────────────

def test_forget_removes_the_resident_copy():
    from domains.equity import sessions as eq_sessions

    _make_resident(USER_A)
    assert eq_sessions.forget(SID) is True
    assert eq_sessions.session_stats()["resident"] == 0
    assert eq_sessions.forget(SID) is False  # idempotent


def test_evict_for_user_is_scoped_to_that_user():
    from domains.equity import sessions as eq_sessions
    from domains.equity.models import EquityPortfolio

    eq_sessions._remember("a", EquityPortfolio(_holdings(), pd.DataFrame()), owner=USER_A.user_id)
    eq_sessions._remember("b", EquityPortfolio(_holdings(), pd.DataFrame()), owner=USER_B.user_id)

    assert eq_sessions.evict_for_user(USER_A.user_id) == 1
    assert eq_sessions.session_stats()["resident"] == 1


def test_evict_for_user_matches_the_owner_exactly():
    """
    The MF equivalent of this once upper-cased before comparing, a leftover from when
    the owner was a PAN. Against a lower-case uuid that never matched, so eviction
    became a no-op that still reported success.
    """
    from domains.equity import sessions as eq_sessions

    _make_resident(USER_A)
    assert eq_sessions.evict_for_user(USER_A.user_id.upper()) == 0
    assert eq_sessions.evict_for_user(USER_A.user_id) == 1


def test_resident_cap_is_enforced(monkeypatch):
    from domains.equity import sessions as eq_sessions
    from domains.equity.models import EquityPortfolio

    monkeypatch.setattr(eq_sessions, "MAX_RESIDENT_SESSIONS", 2)
    for i in range(5):
        eq_sessions._remember(f"s{i}", EquityPortfolio(_holdings(), pd.DataFrame()), owner="o")

    assert eq_sessions.session_stats()["resident"] == 2, (
        "the cap must converge, not shed a single entry per insert"
    )


def test_expired_sessions_are_not_served():
    from datetime import datetime, timedelta
    from domains.equity import sessions as eq_sessions

    _make_resident(USER_A)
    stale = datetime.now() - timedelta(hours=eq_sessions.SESSION_TTL_HOURS + 1)
    eq_sessions._SESSIONS[SID]["last_accessed"] = stale

    assert eq_sessions.purge_expired() == 1
    assert eq_sessions.session_stats()["resident"] == 0

def test_equity_sessions_categorize():
    from domains.equity import sessions as eq_sessions

    df = pd.DataFrame({"sector": ["Tech"] * 20, "industry": ["Software"] * 20})
    out = eq_sessions._compact_dtypes(df)
    assert str(out["sector"].dtype) == "category"
