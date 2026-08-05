"""
test_mf_sessions_full_coverage.py

Comprehensive unit tests for domains/mutual_funds/sessions.py:
- _compact_dtypes category conversion & thresholds
- _remember LRU bounding & eviction
- create_session dedup, category filling, concurrency handling
- purge_expired background cleanup
- get_session resident hit, unauthorized, disk rehydration, failure paths
- forget, evict_for_user, clear_all, session_stats
- df_to_records datetime formatting, inf/nan sanitization
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from fastapi import HTTPException
import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds import sessions
from domains.mutual_funds.models import Portfolio
from shared import identity, storage
from shared.identity import Caller, identity_scope

USER_ID = "00000000-0000-0000-0000-000000000001"
CALLER = Caller(user_id=USER_ID, status="active", role="user", email="user@test.com")


def test_mf_compact_dtypes():
    assert sessions._compact_dtypes(None) is None
    assert sessions._compact_dtypes(pd.DataFrame()).empty

    # Small df (< 16 rows) does not convert
    small_df = pd.DataFrame({"Fund": ["HDFC"] * 5})
    assert sessions._compact_dtypes(small_df)["Fund"].dtype.name != "category"

    # Big df (>= 16 rows) with repeating values converts to category
    big_df = pd.DataFrame({"Fund": ["HDFC", "SBI"] * 10, "Units": [100.0] * 20})
    res_df = sessions._compact_dtypes(big_df)
    assert res_df["Fund"].dtype.name == "category"
    assert res_df["Units"].dtype.name != "category"


def test_mf_sessions_create_and_dedup(monkeypatch):
    sessions.clear_all()

    df_h = pd.DataFrame([{"Fund": "HDFC Top 100", "Category": "", "Units": 10.0, "Invested": 1000.0, "Market Value": 1200.0}])
    df_t = pd.DataFrame([{"Date": "2024-01-01", "Fund": "HDFC Top 100", "Type": "PURCHASE", "Units": 10.0, "Amount": 1000.0}])
    df_s = pd.DataFrame()

    with identity_scope(CALLER):
        # 1. Deduplication match
        monkeypatch.setattr(storage, "check_duplicate_upload", lambda h, uid: "existing-session-id")
        sid_dup = sessions.create_session(df_h, df_t, df_s, is_partial=False)
        assert sid_dup == "existing-session-id"

        # 2. Normal creation with category classification
        monkeypatch.setattr(storage, "check_duplicate_upload", lambda h, uid: None)
        monkeypatch.setattr(storage, "save_session", lambda sid, h, t, s, part, per, uid, ut, ledger_hash: sid)
        monkeypatch.setattr(Portfolio, "update_live_navs", lambda self: None)

        sid_new = sessions.create_session(df_h, df_t, df_s, is_partial=False)
        assert sid_new is not None
        assert df_h["Category"].values[0] == "Equity"
        assert sid_new in sessions._SESSIONS

        # 3. Concurrent duplicate race in save_session
        monkeypatch.setattr(storage, "save_session", lambda sid, h, t, s, part, per, uid, ut, ledger_hash: "won-by-other-thread")
        sid_race = sessions.create_session(df_h, df_t, df_s, is_partial=False)
        assert sid_race == "won-by-other-thread"


def test_mf_sessions_remember_and_purge():
    sessions.clear_all()
    p = Portfolio(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    # LRU Cap eviction
    sessions._remember("s1", p, owner="u1")
    sessions._remember("s2", p, owner="u1")
    sessions._remember("s3", p, owner="u1")
    sessions._remember("s4", p, owner="u1")  # MAX_RESIDENT_SESSIONS is 3, s1 dropped

    assert "s1" not in sessions._SESSIONS
    assert "s4" in sessions._SESSIONS

    # Purge expired
    sessions._SESSIONS["s2"]["last_accessed"] = datetime.now() - timedelta(hours=5)
    expired_count = sessions.purge_expired()
    assert expired_count == 1
    assert "s2" not in sessions._SESSIONS


def test_mf_sessions_get_session_branches(monkeypatch):
    sessions.clear_all()
    p = Portfolio(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    sessions._remember("s-resident", p, owner=USER_ID)
    sessions._remember("s-other", p, owner="other-user")

    # 1. Resident hit authorized
    with identity_scope(CALLER):
        res_p = sessions.get_session("s-resident")
        assert res_p is p

        # 2. Resident hit unauthorized -> 404
        with pytest.raises(HTTPException) as exc:
            sessions.get_session("s-other")
        assert exc.value.status_code == 404

        # 3. Disk lookup error -> 503
        monkeypatch.setattr(storage, "get_session_owner", MagicMock(side_effect=storage.OwnerLookupFailed("DB Down")))
        with pytest.raises(HTTPException) as exc:
            sessions.get_session("s-disk")
        assert exc.value.status_code == 503

        # 4. Disk miss absent -> 404
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (False, None))
        with pytest.raises(HTTPException) as exc:
            sessions.get_session("s-missing")
        assert exc.value.status_code == 404

        # 5. Disk miss unowned/unauthorized -> 404
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, "other-user"))
        with pytest.raises(HTTPException) as exc:
            sessions.get_session("s-disk-other")
        assert exc.value.status_code == 404

        # 6. Disk miss load_session returns None -> 404
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, USER_ID))
        monkeypatch.setattr(storage, "load_session", lambda sid: None)
        with pytest.raises(HTTPException) as exc:
            sessions.get_session("s-disk-empty")
        assert exc.value.status_code == 404

        # 7. Disk miss successful rehydration with failing live navs
        df_h = pd.DataFrame([{"Fund": "HDFC", "Market Value": 1000.0, "Invested": 800.0}])
        df_t = pd.DataFrame([{"Date": "2024-01-01", "Fund": "HDFC", "Type": "PURCHASE", "Units": 10.0, "Amount": 1000.0}])
        df_s = pd.DataFrame()
        monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, USER_ID))
        monkeypatch.setattr(storage, "load_session", lambda sid: (df_h, df_t, df_s, False))
        monkeypatch.setattr(Portfolio, "update_live_navs", MagicMock(side_effect=RuntimeError("AMFI Down")))

        res_rehydrated = sessions.get_session("s-rehydrate-ok")
        assert res_rehydrated.total_value == 1000.0



def test_mf_sessions_management_and_records():
    sessions.clear_all()
    p = Portfolio(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    sessions._remember("s1", p, owner="u1")
    sessions._remember("s2", p, owner="u1")
    sessions._remember("s3", p, owner="u2")

    # session_stats
    stats = sessions.session_stats()
    assert stats["resident"] == 3

    # forget
    assert sessions.forget("s1") is True
    assert sessions.forget("s1") is False

    # evict_for_user
    evicted = sessions.evict_for_user("u1")
    assert evicted == 1  # s2 evicted, s1 was already forgotten
    assert "s2" not in sessions._SESSIONS
    assert "s3" in sessions._SESSIONS

    # clear_all
    assert sessions.clear_all() == 1
    assert len(sessions._SESSIONS) == 0

    # df_to_records
    assert sessions.df_to_records(None) == []
    assert sessions.df_to_records(pd.DataFrame()) == []

    df = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-01", None]),
        "Val": [np.inf, 25.5],
        "Text": ["A", None],
    })
    records = sessions.df_to_records(df)
    assert len(records) == 2
    assert records[0]["Date"] == "2024-01-01"
    assert records[1]["Date"] is None
    assert records[0]["Val"] is None  # inf converted to None
    assert records[1]["Val"] == 25.5
