import datetime
import uuid
import pandas as pd
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from shared import crypto, identity, session_stores, storage, users
from shared.identity import Caller


class FakeDbCursor:
    def __init__(self, fetch_val=None, fetchall_val=None, rowcount=1):
        self._fetch_val = fetch_val
        self._fetchall_val = fetchall_val or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._fetch_val

    def fetchall(self):
        return self._fetchall_val


class FakeDbConn:
    def __init__(self):
        self.executed = []
        self._cursor_queue = []

    def queue_result(self, fetchone=None, fetchall=None, rowcount=1):
        self._cursor_queue.append(FakeDbCursor(fetchone, fetchall, rowcount))

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self._cursor_queue:
            return self._cursor_queue.pop(0)
        return FakeDbCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def auth_client():
    return TestClient(app)


def test_storage_codec_round_trip():
    # 1. Test datetime resolutions (s, ms, us, ns)
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    for unit in ["s", "ms", "us", "ns"]:
        df = pd.DataFrame({
            "Fund": ["Fund A", "Fund B", "Fund C", "Fund D", "Fund E"],
            "Date": dates.astype(f"datetime64[{unit}]"),
            "Amount": [1000.0, 2000.5, 3000.0, 4000.0, 5000.0],
            "Units": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        blob, meta = storage._encode_frame(df)
        restored = storage._decode_frame(blob, meta)
        assert len(restored) == 5
        assert list(restored.columns) == list(df.columns)
        assert pd.api.types.is_datetime64_any_dtype(restored["Date"].dtype)

    # 2. Test empty dataframe
    empty_df = pd.DataFrame(columns=["ColA", "ColB", "Date"])
    blob_e, meta_e = storage._encode_frame(empty_df)
    restored_e = storage._decode_frame(blob_e, meta_e)
    assert len(restored_e) == 0
    assert "ColA" in restored_e.columns

    # 3. Test multi-frame payload encode / decode
    df_h = pd.DataFrame({"Fund": ["Fund 1"], "Market Value": [50000.0], "Invested": [40000.0]})
    df_t = pd.DataFrame({"Fund": ["Fund 1"], "Date": pd.to_datetime(["2024-01-15"]), "Amount": [40000.0], "Units": [400.0], "Type": ["Purchase"]})
    df_s = pd.DataFrame({"Fund": ["Fund 1"], "SIP Amount": [5000.0]})
    
    payload = storage.encode_payload(df_h, df_t, df_s)
    h_out, t_out, s_out = storage.decode_payload(payload)
    assert len(h_out) == 1
    assert len(t_out) == 1
    assert len(s_out) == 1
    assert h_out.iloc[0]["Fund"] == "Fund 1"


def test_storage_data_hash_and_dedup():
    df_t1 = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        "Fund": ["Fund A", "Fund B"],
        "Units": [10.0, 20.0],
        "Amount": [1000.0, 2000.0],
        "Type": ["Purchase", "Purchase"],
    })
    df_t2 = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
        "Fund": ["Fund A", "Fund B"],
        "Units": [10.0, 20.0],
        "Amount": [1000.0, 2000.0],
        "Type": ["Purchase", "Purchase"],
    })
    
    h1 = storage.compute_ledger_hash(df_t1)
    h2 = storage.compute_ledger_hash(df_t2)
    assert h1 == h2
    assert len(h1) == 64


def test_storage_crud_with_mocks(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(storage, "_connect", lambda **kw: conn)
    monkeypatch.setattr("shared.db.connect", lambda **kw: conn)

    # 1. get_session_owner
    conn.queue_result(fetchone=("u-owner",))
    exists, owner = storage.get_session_owner("sess-1")
    assert exists is True
    assert owner == "u-owner"

    # Non-existent session
    conn.queue_result(fetchone=None)
    exists_none, owner_none = storage.get_session_owner("sess-ghost")
    assert exists_none is False
    assert owner_none is None

    # 2. delete_session
    conn.queue_result(rowcount=1)
    res_del = storage.delete_session("sess-1")
    assert res_del is True

    # 3. delete_all_for_user
    conn.queue_result(fetchone=(3,)) # count query
    conn.queue_result(rowcount=3)    # delete query
    del_count = storage.delete_all_for_user("u-owner")
    assert del_count == 3

    # 4. get_history with decrypted metrics
    session_id = "sess-hist-1"
    raw_metrics = {"total_value": 1250000.0, "total_invested": 1000000.0, "num_funds": 4}
    enc_metrics = crypto.encrypt_json(raw_metrics, aad=session_id)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    conn.queue_result(fetchall=[{
        "session_id": session_id,
        "upload_type": "mutual_funds",
        "created_at": now,
        "statement_period": "2023-2024",
        "metrics": enc_metrics,
        "user_id": "u-owner",
    }])

    history = storage.get_history("u-owner")
    assert len(history) == 1
    assert history[0]["total_invested"] == 1000000.0
    assert history[0]["total_value"] == 1250000.0


def test_accounts_router_endpoints(auth_client, signed_in, monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(storage, "_connect", lambda **kw: conn)
    monkeypatch.setattr("shared.db.connect", lambda **kw: conn)

    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. GET /accounts/summary
    conn.queue_result(fetchall=[{
        "session_id": "sess-summary-1",
        "upload_type": "mutual_funds",
        "created_at": now,
    }])
    
    resp_sum = auth_client.get("/accounts/summary", headers=signed_in)
    assert resp_sum.status_code == 200
    data = resp_sum.json()
    assert data["status"] == "ok"
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["sessions"][0]["session_id"] == "sess-summary-1"

    # 2. GET /accounts/me/export
    uid = "00000000-0000-0000-0000-0000000000ff"
    conn.queue_result(fetchone={
        "id": uid,
        "created_at": now,
        "last_seen_at": now,
        "pan_encrypted": None,
        "display_name": "Test Exporter",
    })
    conn.queue_result(fetchall=[{
        "issuer": "https://example-test-issuer.invalid/auth/v1",
        "email": "exporter@test.com",
        "created_at": now,
    }])
    
    # Encrypted mock blobs
    enc_metrics = crypto.encrypt_json({"total_value": 100000.0}, aad="s-tax")
    enc_tax = crypto.encrypt_json({"gross_salary": 500000.0}, aad="s-tax")
    
    enc_budget_metrics = crypto.encrypt_json({"net_spend": 25000.0}, aad="s-budget")
    from domains.budget.sessions import _compress_frame
    df_budget_tx = pd.DataFrame({"Amount": [100.0], "Date": pd.to_datetime(["2024-01-01"])})
    b_txns = crypto.encrypt(_compress_frame(df_budget_tx), aad="s-budget")
    b_accs = {"acc1": {}}

    enc_mf_metrics = crypto.encrypt_json({"total_value": 200000.0}, aad="s-mf")
    mf_payload = storage.encode_payload(
        pd.DataFrame({"Fund": ["F1"], "Market Value": [200000.0], "Invested": [150000.0]}),
        pd.DataFrame({"Fund": ["F1"], "Amount": [150000.0], "Date": pd.to_datetime(["2024-01-01"]), "Units": [100.0], "Type": ["Purchase"]}),
        pd.DataFrame({"Fund": ["F1"], "SIP Amount": [5000.0]})
    )
    enc_h = crypto.encrypt(mf_payload["holdings"], aad="s-mf")
    enc_t = crypto.encrypt(mf_payload["transactions"], aad="s-mf")
    enc_s = crypto.encrypt(mf_payload["sips"], aad="s-mf")

    conn.queue_result(fetchall=[
        {
            "session_id": "s-tax", "upload_type": "tax_expert", "created_at": now, "statement_period": "2024-25",
            "metrics": enc_metrics, "holdings": None, "transactions": None, "sips": None, "meta": None,
            "tax_data": enc_tax, "budget_txns": None, "budget_accounts": None,
        },
        {
            "session_id": "s-budget", "upload_type": "budget", "created_at": now, "statement_period": "2024-01",
            "metrics": enc_budget_metrics, "holdings": None, "transactions": None, "sips": None, "meta": None,
            "tax_data": None, "budget_txns": b_txns, "budget_accounts": b_accs,
        },
        {
            "session_id": "s-mf", "upload_type": "mutual_funds", "created_at": now, "statement_period": "2024-01",
            "metrics": enc_mf_metrics, "holdings": enc_h, "transactions": enc_t, "sips": enc_s, "meta": mf_payload["meta"],
            "tax_data": None, "budget_txns": None, "budget_accounts": None,
        },
        {
            "session_id": "s-corrupt", "upload_type": "mutual_funds", "created_at": now, "statement_period": "2024-01",
            "metrics": b"corrupt-data", "holdings": b"corrupt", "transactions": b"corrupt", "sips": b"corrupt", "meta": {},
            "tax_data": None, "budget_txns": None, "budget_accounts": None,
        }
    ])

    resp_exp = auth_client.get("/accounts/me/export", headers=signed_in)
    assert resp_exp.status_code == 200
    exp_data = resp_exp.json()
    assert len(exp_data["sessions"]) == 4

    # 3. DELETE /accounts/me
    monkeypatch.setattr(session_stores, "evict_user", lambda uid: None)
    monkeypatch.setattr(storage, "delete_all_for_user", lambda uid: 3)
    monkeypatch.setattr(users, "invalidate", lambda uid: None)
    
    resp_purge = auth_client.delete("/accounts/me", headers=signed_in)
    assert resp_purge.status_code == 200
    assert resp_purge.json()["deleted_count"] == 3

    # 4. POST /accounts/clear_caches
    resp_clear = auth_client.post("/accounts/clear_caches", headers=signed_in)
    assert resp_clear.status_code == 200

    # Cache clear exception
    monkeypatch.setattr(session_stores, "clear_all", lambda: (_ for _ in ()).throw(RuntimeError("Cache lock failed")))
    resp_clear_err = auth_client.post("/accounts/clear_caches", headers=signed_in)
    assert resp_clear_err.status_code == 500


def test_accounts_router_unauthorized(auth_client):
    assert auth_client.get("/accounts/summary").status_code == 401
    assert auth_client.get("/accounts/me/export").status_code == 401
    assert auth_client.delete("/accounts/me").status_code == 401


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


def test_storage_save_load_delete_direct(monkeypatch):
    conn = FakeDbConn()
    monkeypatch.setattr(storage, "_connect", lambda **kw: conn)

    df_h = pd.DataFrame({"Fund": ["Fund 1"], "Market Value": [50000.0], "Invested": [40000.0]})
    df_t = pd.DataFrame({"Fund": ["Fund 1"], "Date": pd.to_datetime(["2024-01-15"]), "Amount": [40000.0], "Units": [400.0], "Type": ["Purchase"]})
    df_s = pd.DataFrame({"Fund": ["Fund 1"], "SIP Amount": [5000.0]})

    # 1. save_session new insert
    conn.queue_result(fetchone=("sess-direct-1",))
    sid = storage.save_session("sess-direct-1", df_h, df_t, df_s, is_partial=False, user_id="u1")
    assert sid == "sess-direct-1"

    # 2. save_session duplicate found
    conn.queue_result(fetchone=None) # INSERT returns nothing
    conn.queue_result(fetchone=("existing-sess-1",)) # SELECT returns existing
    sid_dup = storage.save_session("sess-direct-2", df_h, df_t, df_s, is_partial=False, user_id="u1")
    assert sid_dup == "existing-sess-1"

    # 3. save_session no insert no conflict -> raise RuntimeError
    conn.queue_result(fetchone=None)
    conn.queue_result(fetchone=None)
    with pytest.raises(RuntimeError):
        storage.save_session("sess-direct-3", df_h, df_t, df_s, is_partial=False, user_id="u1")

    # 4. load_session
    payload = storage.encode_payload(df_h, df_t, df_s)
    enc_h = crypto.encrypt(payload["holdings"], aad="s-load")
    enc_t = crypto.encrypt(payload["transactions"], aad="s-load")
    enc_s = crypto.encrypt(payload["sips"], aad="s-load")

    conn.queue_result(fetchone=(False, enc_h, enc_t, enc_s, payload["meta"]))
    loaded = storage.load_session("s-load")
    assert loaded is not None
    assert len(loaded[0]) == 1

    # load_session not found
    conn.queue_result(fetchone=None)
    assert storage.load_session("s-none") is None

    # load_session DecryptionFailed
    conn.queue_result(fetchone=(False, b"bad-h", b"bad-t", b"bad-s", {}))
    with pytest.raises(crypto.DecryptionFailed):
        storage.load_session("s-corrupt")

    # 5. get_session_owner
    conn.queue_result(fetchone=("owner-uuid",))
    found, owner = storage.get_session_owner("s-owner")
    assert found is True and owner == "owner-uuid"

    conn.queue_result(fetchone=None)
    found_no, owner_no = storage.get_session_owner("s-not-found")
    assert found_no is False and owner_no is None

    # 6. delete_session
    assert storage.delete_session("s-del") is True

    # 7. delete_all_for_user
    conn.queue_result(fetchone=(4,))
    assert storage.delete_all_for_user("u-purge") == 4

