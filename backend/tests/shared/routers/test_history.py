"""Router tests for shared/routers/history.py."""

import pandas as pd
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from shared import storage
from shared.identity import Caller, identity_scope


@pytest.fixture
def auth_client():
    return TestClient(app)


def test_history_router_endpoints(auth_client, signed_in, monkeypatch):
    # 1. GET /history/
    monkeypatch.setattr(storage, "get_history", lambda user_id, upload_type="mutual_funds": [
        {"session_id": "s-1", "upload_type": upload_type, "created_at": "2026-08-01", "total_value": 50000.0}
    ])
    
    resp_hist = auth_client.get("/history/", headers=signed_in)
    assert resp_hist.status_code == 200
    assert resp_hist.json()["status"] == "success"
    assert len(resp_hist.json()["history"]) == 1

    # 2. DELETE /history/{session_id}
    caller_uid = "00000000-0000-0000-0000-0000000000ff"
    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, caller_uid))
    monkeypatch.setattr(storage, "delete_session", lambda sid: True)
    
    resp_del = auth_client.delete("/history/s-1", headers=signed_in)
    assert resp_del.status_code == 200
    assert resp_del.json()["deleted_session_id"] == "s-1"

    # Non-existent session returns 404
    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (False, None))
    resp_del_404 = auth_client.delete("/history/s-nonexistent", headers=signed_in)
    assert resp_del_404.status_code == 404

    # Other user's session returns 404 (prevent probe)
    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, "other-user-uuid"))
    resp_del_other = auth_client.delete("/history/s-other", headers=signed_in)
    assert resp_del_other.status_code == 404

def test_history_compare_reconciliation(auth_client, signed_in, monkeypatch):
    caller_uid = "00000000-0000-0000-0000-0000000000ff"
    
    df_h1 = pd.DataFrame({"Fund": ["Fund A"], "Market Value": [10000.0], "Invested": [9000.0]})
    df_t1 = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-10"]),
        "Fund": ["Fund A"],
        "Amount": [9000.0],
        "Units": [100.0],
        "Type": ["Purchase"],
    })
    df_s1 = pd.DataFrame()

    df_h2 = pd.DataFrame({"Fund": ["Fund A"], "Market Value": [15000.0], "Invested": [12000.0]})
    df_t2 = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-10", "2024-02-10"]),
        "Fund": ["Fund A", "Fund A"],
        "Amount": [9000.0, 3000.0],
        "Units": [100.0, 30.0],
        "Type": ["Purchase", "SIP Purchase"],
    })
    df_s2 = pd.DataFrame()

    meta_hist = [
        {"session_id": "sess-a", "created_at": "2024-01-15T00:00:00Z"},
        {"session_id": "sess-b", "created_at": "2024-02-15T00:00:00Z"},
    ]
    monkeypatch.setattr(storage, "get_history", lambda user_id: meta_hist)
    
    def mock_load_session(sid):
        if sid == "sess-a":
            return (df_h1, df_t1, df_s1, {})
        if sid == "sess-b":
            return (df_h2, df_t2, df_s2, {})
        return None

    monkeypatch.setattr(storage, "load_session", mock_load_session)

    resp_comp = auth_client.get("/history/compare/sess-a/vs/sess-b", headers=signed_in)
    assert resp_comp.status_code == 200
    res = resp_comp.json()
    assert res["status"] == "success"
    assert res["deltas"]["portfolio_value_change"] == 5000.0
    assert res["deltas"]["capital_invested_change"] == 3000.0
    assert res["new_transactions_count"] == 1

def test_history_delete_failure_and_compare_branches(monkeypatch):
    from shared.routers import history
    from shared import storage, identity

    caller = Caller(user_id="u1", status="active", role="user", email="u@test.com")
    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (True, "u1"))
    monkeypatch.setattr("shared.session_stores.forget_session", lambda sid: None)
    monkeypatch.setattr(storage, "delete_session", lambda sid: False)
    with identity_scope(caller):
        with pytest.raises(HTTPException) as exc:
            history.delete_session("sess-del")
        assert exc.value.status_code == 500

    with pytest.raises(HTTPException):
        history.compare_sessions("a", "b")

    hist = [
        {"session_id": "sa", "created_at": "2024-01-01"},
        {"session_id": "sb", "created_at": "2024-06-01"},
    ]
    df_h = pd.DataFrame({"Fund": ["F1"], "Market Value": [1000.0], "Invested": [900.0]})
    df_t_new = pd.DataFrame([
        {"Date": pd.Timestamp("2024-05-01"), "Fund": "F1", "Units": 1.0, "Amount": 100.0, "Type": "Purchase"},
        {"Date": pd.Timestamp("2024-06-15"), "Fund": "F1", "Units": 2.0, "Amount": 200.0, "Type": "Opening Balance"},
    ])
    df_t_old = pd.DataFrame([
        {"Date": pd.Timestamp("2024-01-01"), "Fund": "F1", "Units": 1.0, "Amount": 100.0, "Type": "Purchase"},
    ])
    df_s = pd.DataFrame()
    monkeypatch.setattr(storage, "get_history", lambda user_id, upload_type="mutual_funds": hist)
    monkeypatch.setattr(storage, "load_session", lambda sid: {
        "sa": (df_h, df_t_old, df_s, {}),
        "sb": (df_h, df_t_new, df_s, {}),
    }[sid])
    with identity_scope(caller):
        out = history.compare_sessions("sa", "sb")
    assert out["status"] == "success"

    # Force chronological swap: sb is older baseline, sa is newer
    df_t_old2 = pd.DataFrame([
        {"Date": pd.Timestamp("2024-01-01"), "Fund": "F1", "Units": 1.0, "Amount": 100.0, "Type": "Purchase"},
    ])
    df_t_new2 = pd.DataFrame([
        {"Date": pd.Timestamp("2024-08-01"), "Fund": "F1", "Units": 1.0, "Amount": 100.0, "Type": "Purchase"},
    ])
    monkeypatch.setattr(storage, "load_session", lambda sid: {
        "sa": (df_h, df_t_new2, df_s, {}),
        "sb": (df_h, df_t_old2, df_s, {}),
    }[sid])
    with identity_scope(caller):
        swapped = history.compare_sessions("sa", "sb")
    assert swapped["baseline_session"] == "sb"

    empty_t = pd.DataFrame(columns=["Date", "Fund", "Units", "Amount", "Type"])
    monkeypatch.setattr(storage, "load_session", lambda sid: (df_h, empty_t, df_s, {}))
    with identity_scope(caller):
        out2 = history.compare_sessions("sa", "sb")
    assert out2["new_transactions_count"] == 0

def test_history_upload_auth_and_delete_missing(monkeypatch):
    from shared.routers import history
    from shared import storage
    from shared.identity import Caller, identity_scope
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        history.get_upload_history()

    caller = Caller(user_id="u1", status="active", role="user", email="u@test.com")
    monkeypatch.setattr(storage, "get_history", lambda user_id, upload_type="mutual_funds": [])
    with identity_scope(caller):
        assert history.get_upload_history()["status"] == "success"

    monkeypatch.setattr(storage, "get_session_owner", lambda sid: (False, None))
    with pytest.raises(HTTPException):
        history.delete_session("missing")

