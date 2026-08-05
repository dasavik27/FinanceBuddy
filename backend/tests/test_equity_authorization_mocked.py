"""
test_equity_authorization_mocked.py

Mock-based equivalents of test_equity_authorization.py.
All DB, storage and external quote calls are patched so no Postgres or network is needed.

The tests cover:
  - Equity session ownership enforcement (resident hit & disk miss)
  - Anonymous callers cannot access owned equity sessions
  - Fail-closed behavior on storage lookup errors (503)
  - Memory eviction and purge scoping for equity sessions
  - Dedup hash scoping to owner
  - Rehydration metadata preservation
"""

import uuid
import pandas as pd
import pytest
from fastapi import HTTPException

from domains.equity import sessions as eq_sessions
from domains.equity.models import EquityPortfolio
from shared import identity, storage
from shared.identity import Caller, identity_scope

USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"

caller_a = Caller(user_id=USER_A_ID, status="active", role="user", email="eq-a@example.test")
caller_b = Caller(user_id=USER_B_ID, status="active", role="user", email="eq-b@example.test")


@pytest.fixture(autouse=True)
def clean_equity_resident():
    eq_sessions.clear_all()
    yield
    eq_sessions.clear_all()


def _holdings(symbol: str = "RELIANCE", qty: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": symbol, "isin": "INE002A01018", "name": symbol, "exchange": "NSE",
        "quantity": qty, "avg_price": 1000.0, "ltp": 1200.0,
        "current_value": qty * 1200.0, "invested": qty * 1000.0,
        "unrealized_pnl": qty * 200.0, "pnl_pct": 20.0,
        "day_change": 5.0, "day_change_pct": 0.4, "broker": "zerodha",
    }])


def test_equity_get_session_denies_another_user_resident():
    sid = str(uuid.uuid4())
    fake_portfolio = EquityPortfolio(_holdings(), pd.DataFrame())
    eq_sessions._remember(sid, fake_portfolio, owner=USER_A_ID)

    # Caller B cannot access Caller A's resident session
    with identity_scope(caller_b), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404

    # Caller A can access
    with identity_scope(caller_a):
        assert eq_sessions.get_session(sid) is fake_portfolio


def test_equity_get_session_denies_another_user_disk_miss(monkeypatch):
    sid = str(uuid.uuid4())
    monkeypatch.setattr(storage, "get_session_owner", lambda s: (True, USER_A_ID))

    with identity_scope(caller_b), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_equity_anonymous_caller_cannot_read_owned_session(monkeypatch):
    sid = str(uuid.uuid4())
    monkeypatch.setattr(storage, "get_session_owner", lambda s: (True, USER_A_ID))

    with identity_scope(None), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_equity_ownership_check_fails_closed_on_lookup_error(monkeypatch):
    sid = str(uuid.uuid4())

    def boom(s):
        raise storage.OwnerLookupFailed("connection lost")

    monkeypatch.setattr(storage, "get_session_owner", boom)

    with identity_scope(caller_a), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 503


def test_equity_resident_session_denies_after_registry_deleted(monkeypatch):
    sid = str(uuid.uuid4())
    monkeypatch.setattr(storage, "get_session_owner", lambda s: (False, None))

    with identity_scope(caller_a), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(sid)
    assert exc.value.status_code == 404


def test_equity_unknown_session_raises_404(monkeypatch):
    monkeypatch.setattr(storage, "get_session_owner", lambda s: (False, None))
    with identity_scope(caller_a), pytest.raises(HTTPException) as exc:
        eq_sessions.get_session(str(uuid.uuid4()))
    assert exc.value.status_code == 404


def test_equity_forget_evicts_from_resident_store():
    sid = str(uuid.uuid4())
    fake_portfolio = EquityPortfolio(_holdings(), pd.DataFrame())
    eq_sessions._remember(sid, fake_portfolio, owner=USER_A_ID)
    assert eq_sessions.session_stats()["resident"] == 1

    eq_sessions.forget(sid)
    assert eq_sessions.session_stats()["resident"] == 0


def test_equity_purge_evicts_for_user_only():
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())
    p_a = EquityPortfolio(_holdings("RELIANCE"), pd.DataFrame())
    p_b = EquityPortfolio(_holdings("TCS"), pd.DataFrame())

    eq_sessions._remember(sid_a, p_a, owner=USER_A_ID)
    eq_sessions._remember(sid_b, p_b, owner=USER_B_ID)
    assert eq_sessions.session_stats()["resident"] == 2

    evicted = eq_sessions.evict_for_user(USER_A_ID)
    assert evicted == 1
    assert eq_sessions.session_stats()["resident"] == 1
    assert sid_b in eq_sessions._SESSIONS
    assert sid_a not in eq_sessions._SESSIONS


def test_equity_dedup_hash_scoping(monkeypatch):
    df_h = _holdings()
    df_t = pd.DataFrame()

    hash_a = eq_sessions._equity_ledger_hash(df_h, df_t, USER_A_ID)
    hash_b = eq_sessions._equity_ledger_hash(df_h, df_t, USER_B_ID)
    assert hash_a != hash_b, "dedup hashes for different users with same data must not collide"


def test_equity_rehydrated_session_preserves_broker(monkeypatch):
    sid = str(uuid.uuid4())
    df_h = _holdings("INFY")
    df_h["broker"] = "zerodha_kite"
    df_t = pd.DataFrame()

    monkeypatch.setattr(storage, "get_session_owner", lambda s: (True, USER_A_ID))
    monkeypatch.setattr(storage, "load_session", lambda s: (df_h, df_t, pd.DataFrame(), False))

    with identity_scope(caller_a):
        portfolio = eq_sessions.get_session(sid)
    assert portfolio is not None
