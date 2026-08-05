"""
test_tax_sessions_full_coverage.py

Comprehensive unit tests for domains/tax_expert/tax_sessions.py to achieve full branch coverage:
- In-memory and persisted storage lifecycle (_load_from_disk, _rehydrate, _persist_one, _delete_many)
- Fingerprinting and deduplication (find_duplicate, _ais_fingerprint)
- Authorization and record ownership (_owned_or_none)
- Mutation pipelines (update_deductions, update_ais_data, update_overrides, update_itr_data, get_itr_data)
- History retrieval, limits, and pagination (get_sessions_by_user, clamp_history_limit)
- Cache eviction, drop, and registration (evict_for_user, delete_tax_session, clear_all, _clear_all_with_computations)
"""

import time
from unittest.mock import MagicMock
import pytest

from domains.tax_expert import tax_sessions
from shared import crypto, identity


class FakeDbCursor:
    def __init__(self, fetch_val=None, fetchall_val=None, rowcount=1):
        self._fetch_val = fetch_val
        self._fetchall_val = fetchall_val or []
        self.rowcount = rowcount
        self.executemany_calls = []

    def fetchone(self):
        return self._fetch_val

    def fetchall(self):
        return self._fetchall_val

    def execute(self, sql, params=None):
        return self

    def executemany(self, sql, params_seq):
        self.executemany_calls.append((sql, params_seq))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeDbConn:
    def __init__(self):
        self.executed = []
        self._cursor_queue = []

    def queue_result(self, fetchone=None, fetchall=None, rowcount=1):
        self._cursor_queue.append(FakeDbCursor(fetchone, fetchall, rowcount))

    def cursor(self):
        if self._cursor_queue:
            return self._cursor_queue.pop(0)
        return FakeDbCursor()

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

    def __exit__(self, *args):
        pass


def test_tax_sessions_load_and_rehydrate(monkeypatch):
    tax_sessions.clear_all()

    # 1. _load_from_disk
    conn = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)

    # Valid encrypted row + invalid row
    valid_blob = crypto.encrypt_json({"user_id": "u1", "test": True}, aad="s1")
    invalid_blob = b"corrupt-json"

    conn.queue_result(fetchall=[
        ("s1", valid_blob, time.time()),
        ("s2", invalid_blob, time.time()),
    ])

    tax_sessions._load_from_disk_locked()
    assert "s1" in tax_sessions._tax_sessions
    assert "s2" not in tax_sessions._tax_sessions

    # DB error in _load_from_disk_locked
    monkeypatch.setattr(tax_sessions.db, "connect", MagicMock(side_effect=RuntimeError("DB Down")))
    tax_sessions._load_from_disk_locked()


    # 2. _rehydrate
    monkeypatch.setattr(tax_sessions.db, "connect", MagicMock(side_effect=RuntimeError("DB error")))
    assert tax_sessions._rehydrate("s-err") is None

    # Not found in DB
    conn2 = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn2)
    conn2.queue_result(fetchone=None)
    assert tax_sessions._rehydrate("s-none") is None

    # Corrupt in DB
    conn3 = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn3)
    conn3.queue_result(fetchone=(b"bad-data", time.time()))
    assert tax_sessions._rehydrate("s-bad") is None

    # Valid in DB
    conn4 = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn4)
    valid_s3 = crypto.encrypt_json({"user_id": "u1", "val": 123}, aad="s3")
    conn4.queue_result(fetchone=(valid_s3, time.time()))
    rehydrated = tax_sessions._rehydrate("s3")
    assert rehydrated is not None
    assert rehydrated["val"] == 123
    assert "s3" in tax_sessions._tax_sessions


def test_tax_sessions_dedup_and_creation(monkeypatch):
    tax_sessions._sessions_loaded = True
    conn = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)

    # 1. find_duplicate
    assert tax_sessions.find_duplicate({"pan": "A"}, None) is None

    # Duplicate found in DB
    conn.queue_result(fetchone=("s-existing",))
    assert tax_sessions.find_duplicate({"pan": "A"}, "u1") == "s-existing"

    # Duplicate not found in DB
    conn.queue_result(fetchone=None)
    assert tax_sessions.find_duplicate({"pan": "A"}, "u1") is None

    # DB error in find_duplicate
    monkeypatch.setattr(tax_sessions.db, "connect", MagicMock(side_effect=RuntimeError("DB error")))
    assert tax_sessions.find_duplicate({"pan": "A"}, "u1") is None

    # 2. create_tax_session
    conn_create = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn_create)
    monkeypatch.setattr(identity, "current_user_id", lambda: "u1")

    # Reuse existing
    conn_create.queue_result(fetchone=("s-existing-2",))
    assert tax_sessions.create_tax_session({"pan": "A"}) == "s-existing-2"

    # Create brand new
    conn_create.queue_result(fetchone=None) # find_duplicate
    new_sid = tax_sessions.create_tax_session({"pan": "B"})
    assert new_sid is not None
    assert new_sid in tax_sessions._tax_sessions


def test_tax_sessions_access_and_mutations(monkeypatch):
    tax_sessions._sessions_loaded = True
    conn = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)
    monkeypatch.setattr(identity, "current_user_id", lambda: "u1")
    monkeypatch.setattr(identity, "owns_record", lambda owner: owner == "u1")

    # 1. get_tax_session
    # Memory hit, authorized
    tax_sessions._tax_sessions["s-auth"] = {"user_id": "u1", "ais_data": {"salary": {"gross": 50000}}}
    assert tax_sessions.get_tax_session("s-auth") is not None

    # Memory hit, unauthorized
    tax_sessions._tax_sessions["s-unauth"] = {"user_id": "u2", "ais_data": {}}
    assert tax_sessions.get_tax_session("s-unauth") is None

    # Memory miss -> rehydrate
    blob = crypto.encrypt_json({"user_id": "u1", "ais_data": {"salary": {"gross": 60000}}}, aad="s-rehyd")
    conn.queue_result(fetchone=(blob, time.time()))
    res_rehyd = tax_sessions.get_tax_session("s-rehyd")
    assert res_rehyd is not None
    assert res_rehyd["ais_data"]["salary"]["gross"] == 60000

    # 2. update_deductions, update_ais_data, update_overrides, update_itr_data, get_itr_data
    # Missing session
    conn.queue_result(fetchone=None)
    assert not tax_sessions.update_deductions("s-nonexistent", {"80C": 150000})

    # Success updates on s-auth
    assert tax_sessions.update_deductions("s-auth", {"80C": 150000})
    assert tax_sessions._tax_sessions["s-auth"]["deductions"]["80C"] == 150000

    assert tax_sessions.update_ais_data("s-auth", {"salary": {"gross": 55000}})
    assert tax_sessions._tax_sessions["s-auth"]["ais_data"]["salary"]["gross"] == 55000

    assert tax_sessions.update_overrides("s-auth", {"deductions": {"80D": 25000}, "val": 10})
    assert tax_sessions.update_overrides("s-auth", {"deductions": {"80C": 100000}})
    assert tax_sessions._tax_sessions["s-auth"]["overrides"]["deductions"]["80D"] == 25000

    assert tax_sessions.update_itr_data("s-auth", {"itr_form": "ITR-1"})
    assert tax_sessions.get_itr_data("s-auth") == {"itr_form": "ITR-1"}
    assert tax_sessions.get_itr_data("s-unauth") is None


def test_tax_sessions_history_and_eviction(monkeypatch):
    tax_sessions._sessions_loaded = True
    conn = FakeDbConn()
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)

    # 1. clamp_history_limit
    assert tax_sessions.clamp_history_limit(-5) == 1
    assert tax_sessions.clamp_history_limit(10) == 10
    assert tax_sessions.clamp_history_limit(500) == tax_sessions.HISTORY_MAX_PAGE_SIZE

    # 2. get_sessions_by_user
    assert tax_sessions.get_sessions_by_user("") == []

    # DB Error
    monkeypatch.setattr(tax_sessions.db, "connect", MagicMock(side_effect=RuntimeError("DB error")))
    assert tax_sessions.get_sessions_by_user("u1") == []

    # Success with valid and undecryptable rows
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)
    import datetime
    now = datetime.datetime.now()
    valid_metrics = crypto.encrypt_json({"summary": {"name": "Avik", "fy": "2025-26", "gross_salary": 1000000}}, aad="s-hist-1")
    bad_metrics = b"corrupted-blob"

    conn.queue_result(fetchall=[
        ("s-hist-1", now, now, valid_metrics),
        ("s-hist-2", now, now, bad_metrics),
    ])

    results = tax_sessions.get_sessions_by_user("u1")
    assert len(results) == 2
    assert results[0]["name"] == "Avik"
    assert results[1]["name"] == ""

    # 3. evict_for_user and delete_tax_session
    tax_sessions._tax_sessions.clear()
    tax_sessions._tax_sessions["s-u1"] = {"user_id": "u1"}
    tax_sessions._tax_sessions["s-u2"] = {"user_id": "u2"}

    assert tax_sessions.evict_for_user("u1") == 1
    assert "s-u1" not in tax_sessions._tax_sessions
    assert "s-u2" in tax_sessions._tax_sessions

    assert tax_sessions.delete_tax_session("s-u2") is True
    assert tax_sessions.delete_tax_session("s-u2") is False

    # 4. list_sessions and clear_all
    tax_sessions._tax_sessions["s-all"] = {"user_id": "u1"}
    assert len(tax_sessions.list_sessions()) >= 1

    tax_sessions._clear_all_with_computations()
    assert len(tax_sessions._tax_sessions) == 0
