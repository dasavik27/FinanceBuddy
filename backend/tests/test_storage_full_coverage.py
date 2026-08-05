"""
test_storage_full_coverage.py

Comprehensive tests for shared/storage.py:
- compute_ledger_hash (equity columns, MF columns, holdings-only, empty)
- check_duplicate_upload
- get_session_owner (existing, unowned, absent, error handling)
- save_session (insertion, duplicate race, missing conflict exception)
- load_session (success, not found, decryption error, query error)
- get_history (filtering, decrypted metrics, decryption error resilience)
- delete_session & delete_all_for_user
"""

from unittest.mock import MagicMock
import pandas as pd
import pytest

from shared import crypto, storage


class MockDbConn:
    def __init__(self, fetchone_val=None, fetchall_val=None):
        self.cursor = MagicMock()
        self.cursor.fetchone.return_value = fetchone_val
        self.cursor.fetchall.return_value = fetchall_val or []
        self.execute = MagicMock(return_value=self.cursor)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_storage_compute_ledger_hash_variations():
    # 1. Equity format
    df_eq = pd.DataFrame([
        {"date": "2025-01-01", "symbol": "INFY", "type": "BUY", "quantity": 10.0, "price": 1500.0},
    ])
    hash_eq = storage.compute_ledger_hash(df_eq, user_id="u1")
    assert isinstance(hash_eq, str) and len(hash_eq) == 64

    # 2. MF format
    df_mf = pd.DataFrame([
        {"Date": "2025-01-01", "Fund": "HDFC Top 100", "Type": "PURCHASE", "Units": 100.0, "Amount": 5000.0},
    ])
    hash_mf = storage.compute_ledger_hash(df_mf, user_id="u1")
    assert isinstance(hash_mf, str) and len(hash_mf) == 64

    # 3. Empty transactions with holdings
    df_h = pd.DataFrame([{"Fund": "HDFC", "Units": 50.0}])
    hash_h = storage.compute_ledger_hash(pd.DataFrame(), user_id="u1", df_holdings=df_h)
    assert isinstance(hash_h, str) and len(hash_h) == 64

    # 4. Empty transactions and empty holdings
    hash_empty = storage.compute_ledger_hash(pd.DataFrame(), user_id="u1", df_holdings=pd.DataFrame())
    assert hash_empty.startswith("empty_ledger_")


def test_storage_check_duplicate_upload(monkeypatch):
    mock_conn = MockDbConn(fetchone_val=("sess-dup-1",))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn)
    assert storage.check_duplicate_upload("hash123", "u1") == "sess-dup-1"

    # Not found
    mock_conn_none = MockDbConn(fetchone_val=None)
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_none)
    assert storage.check_duplicate_upload("hash_new", "u1") is None


def test_storage_get_session_owner(monkeypatch):
    # Found owned
    mock_conn = MockDbConn(fetchone_val=("u-owner",))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn)
    exists, owner = storage.get_session_owner("s1")
    assert exists is True
    assert owner == "u-owner"

    # Found unowned (user_id NULL)
    mock_conn_unowned = MockDbConn(fetchone_val=(None,))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_unowned)
    exists, owner = storage.get_session_owner("s2")
    assert exists is True
    assert owner is None

    # Absent
    mock_conn_absent = MockDbConn(fetchone_val=None)
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_absent)
    exists, owner = storage.get_session_owner("s-missing")
    assert exists is False
    assert owner is None

    # DB Error raises OwnerLookupFailed
    monkeypatch.setattr(storage, "_connect", MagicMock(side_effect=RuntimeError("DB Lock")))
    with pytest.raises(storage.OwnerLookupFailed):
        storage.get_session_owner("s-err")


def test_storage_save_session_full(monkeypatch):
    df_h = pd.DataFrame([{"Market Value": 10000.0, "Invested": 8000.0}])
    df_t = pd.DataFrame([{"Date": "2025-01-01", "Fund": "SBI", "Type": "BUY", "Units": 10.0, "Amount": 1000.0}])
    df_s = pd.DataFrame()

    # 1. Normal insert
    mock_conn = MockDbConn(fetchone_val=("s-new",))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn)
    res_sid = storage.save_session("s-new", df_h, df_t, df_s, is_partial=False, user_id="u1")
    assert res_sid == "s-new"

    # 2. Conflict deduplication (insert returns None, select returns existing)
    mock_conn_conflict = MockDbConn()
    mock_conn_conflict.execute.side_effect = [
        MagicMock(fetchone=lambda: None),            # INSERT returns None
        MagicMock(fetchone=lambda: ("s-existing",)), # SELECT returns existing
        MagicMock(),
    ]
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_conflict)
    res_existing = storage.save_session("s-new", df_h, df_t, df_s, is_partial=False, user_id="u1")
    assert res_existing == "s-existing"

    # 3. Neither inserted nor found raises RuntimeError
    mock_conn_err = MockDbConn()
    mock_conn_err.execute.side_effect = [
        MagicMock(fetchone=lambda: None),
        MagicMock(fetchone=lambda: None),
    ]
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_err)
    with pytest.raises(RuntimeError):
        storage.save_session("s-new", df_h, df_t, df_s, is_partial=False, user_id="u1")


def test_storage_load_session_full(monkeypatch):
    # 1. Absent
    mock_conn_none = MockDbConn(fetchone_val=None)
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_none)
    assert storage.load_session("s-none") is None

    # 2. Success load
    sid = "s-load-ok"
    payload = storage.encode_payload(
        pd.DataFrame([{"Fund": "Axis", "Market Value": 2000}]),
        pd.DataFrame([{"Date": "2025-01-01", "Fund": "Axis", "Type": "BUY", "Units": 10.0, "Amount": 1000.0}]),
        pd.DataFrame(),
    )
    enc_h = crypto.encrypt(payload["holdings"], aad=sid)
    enc_t = crypto.encrypt(payload["transactions"], aad=sid)
    enc_s = crypto.encrypt(payload["sips"], aad=sid)

    mock_conn_ok = MockDbConn(fetchone_val=(False, enc_h, enc_t, enc_s, payload["meta"]))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_ok)
    res = storage.load_session(sid)
    assert res is not None
    loaded_h, loaded_t, loaded_s, is_partial = res
    assert len(loaded_h) == 1
    assert is_partial is False

    # 3. Decryption error raises DecryptionFailed
    mock_conn_bad = MockDbConn(fetchone_val=(False, b"bad_blob", b"bad_blob", b"bad_blob", {}))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_bad)
    with pytest.raises(crypto.DecryptionFailed):
        storage.load_session(sid)

    # 4. DB execution error returns None
    monkeypatch.setattr(storage, "_connect", MagicMock(side_effect=RuntimeError("DB Error")))
    assert storage.load_session(sid) is None


def test_storage_get_history_and_deletes(monkeypatch):
    # 1. get_history with decrypted metrics
    sid = "s-hist-1"
    metrics_blob = crypto.encrypt_json(
        {"total_value": 50000.0, "total_invested": 40000.0, "num_funds": 2, "summary": {"k": "v"}},
        aad=sid,
    )
    row1 = {
        "session_id": sid,
        "user_id": "00000000-0000-0000-0000-000000000001",
        "upload_type": "mutual_funds",
        "created_at": "2025-01-01",
        "updated_at": "2025-01-01",
        "is_partial": False,
        "statement_period": "2024-2025",
        "metrics": metrics_blob,
    }
    # Row with bad metrics that fails decryption
    row2 = {
        "session_id": "s-hist-2",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "upload_type": "mutual_funds",
        "created_at": "2025-01-02",
        "updated_at": "2025-01-02",
        "is_partial": False,
        "statement_period": "2024-2025",
        "metrics": b"corrupt_metrics",
    }

    mock_conn = MockDbConn(fetchall_val=[row1, row2])
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn)

    history = storage.get_history(user_id="u1", upload_type="mutual_funds")
    assert len(history) == 2
    assert history[0]["total_value"] == 50000.0
    assert history[1]["total_value"] is None  # Degraded safely

    # 2. delete_session
    mock_conn_del = MockDbConn()
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_del)
    assert storage.delete_session("s1") is True

    # delete_session error returns False
    monkeypatch.setattr(storage, "_connect", MagicMock(side_effect=RuntimeError("Fail")))
    assert storage.delete_session("s1") is False

    # 3. delete_all_for_user
    mock_conn_purge = MockDbConn(fetchone_val=(3,))
    monkeypatch.setattr(storage, "_connect", lambda *args, **kwargs: mock_conn_purge)
    assert storage.delete_all_for_user("u1") == 3
