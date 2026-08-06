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
from tests.helpers import FakeDbConn

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
def test_tax_sessions_load_rehydrate(monkeypatch):
    from domains.tax_expert import tax_sessions
    from shared import crypto

    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = False

    conn = FakeDbConn()
    blob = crypto.encrypt_json({"fy": "2025-26", "personal": {}}, aad="sid1")
    conn.queue_result(fetchall=[("sid1", blob, time.time())])
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)
    with tax_sessions._SESSIONS_LOCK:
        tax_sessions._load_from_disk_locked()

    sid_new = "sid-new"
    blob2 = crypto.encrypt_json({"fy": "2025-26", "personal": {}}, aad=sid_new)
    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=(blob2, time.time()))
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn2)
    assert tax_sessions._rehydrate(sid_new) is not None

    conn3 = FakeDbConn()
    conn3.queue_result(fetchone=(b"corrupt", time.time()))
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn3)
    assert tax_sessions._rehydrate("sid-bad") is None

def test_tax_sessions_type_errors_and_version(monkeypatch):
    from domains.tax_expert import tax_sessions
    from shared import crypto

    tax_sessions.clear_all()
    tax_sessions._sessions_loaded = False
    conn = FakeDbConn()
    blob = crypto.encrypt_json(["not", "a", "dict"], aad="sid-bad-type")
    conn.queue_result(fetchall=[("sid-bad-type", blob, time.time())])
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn)
    with tax_sessions._SESSIONS_LOCK:
        tax_sessions._load_from_disk_locked()

    sid = "sid-race"
    blob2 = crypto.encrypt_json({"fy": "2025-26"}, aad=sid)
    conn2 = FakeDbConn()
    conn2.queue_result(fetchone=(blob2, time.time()))
    monkeypatch.setattr(tax_sessions.db, "connect", lambda: conn2)
    tax_sessions._tax_sessions[sid] = {"fy": "2025-26", "_version": 3}
    restored = tax_sessions._rehydrate(sid)
    assert restored["_version"] == 3
    assert tax_sessions.get_session_version("missing") == -1

def test_computation_cache_evict_and_invalidate():
    from domains.tax_expert import computation_cache

    computation_cache.clear_all()
    computation_cache._cache[("s1", "new")] = {"result": 1}
    computation_cache._cache[("s1", "old")] = {"result": 2}
    computation_cache._cache[("s2", "new")] = {"result": 3}
    computation_cache.invalidate_session("s1")
    assert not any(k[0] == "s1" for k in computation_cache._cache)
    computation_cache.clear_all()



import threading

import pytest

from domains.tax_expert import tax_sessions
from shared import identity
from shared.identity import Caller

TEST_PAN = "ABCDE1234F"
OWNER_USER_ID = "00000000-0000-0000-0000-0000000000ff"
OWNER_CALLER = Caller(
    user_id=OWNER_USER_ID, pan=TEST_PAN, status="active", role="user", email="tax@example.test"
)


@pytest.fixture(autouse=True)
def _clean_tax_state_for_mocked_sessions():
    from domains.tax_expert import computation_cache

    computation_cache.clear_all()
    tax_sessions.clear_all()
    yield
    computation_cache.clear_all()
    tax_sessions.clear_all()


@pytest.fixture
def sample_ais():
    return {
        "fy": "2025-26",
        "personal": {"pan": TEST_PAN, "name": "Session Test"},
        "salary": {"gross": 1_800_000, "tds_deducted": 150_000},
        "capital_gains_equity": [],
    }


@pytest.fixture
def tax_session_id(sample_ais):
    with identity.identity_scope(OWNER_CALLER):
        sid = tax_sessions.create_tax_session(sample_ais)
    return sid


def test_concurrent_tax_session_mutations():
    """
    Stress-test concurrent read/write on the tax session store
    to guarantee no RuntimeError: OrderedDict mutated during iteration.
    """
    errors = []
    stop = threading.Event()

    def writer():
        try:
            for i in range(20):
                with identity.identity_scope(OWNER_CALLER):
                    sid = tax_sessions.create_tax_session({
                        "personal": {"pan": f"PAN{i}"},
                        "fy": "2025-26",
                    })
                    tax_sessions.update_overrides(sid, {"manual_tds": i * 100})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            while not stop.is_set():
                sessions = tax_sessions.list_sessions()
                for sid, _ in sessions:
                    tax_sessions.get_tax_session(sid)
        except Exception as e:
            errors.append(e)

    t_writer = threading.Thread(target=writer)
    t_reader = threading.Thread(target=reader)

    t_reader.start()
    t_writer.start()

    t_writer.join(timeout=5)
    stop.set()
    t_reader.join(timeout=5)

    assert len(errors) == 0, f"Concurrent tax session mutations caused errors: {errors}"

def test_session_version_bumps_on_mutation_mocked(tax_session_id):
    v0 = tax_sessions.get_session_version(tax_session_id)
    tax_sessions.update_overrides(tax_session_id, {"manual_tds": 1234})
    assert tax_sessions.get_session_version(tax_session_id) > v0

