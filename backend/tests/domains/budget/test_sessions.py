
"""Budget session storage, encoding, and ownership."""

from __future__ import annotations

import json
import zlib
from contextlib import contextmanager

import pandas as pd
import pytest
from fastapi import HTTPException

from domains.budget import sessions as budget_sessions
from shared import identity
from shared.identity import Caller, identity_scope
from tests.helpers import FakeDbConn


USER_A = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
USER_B = Caller(user_id="bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb")


def _budget_frame(**overrides) -> pd.DataFrame:
    row = {
        "txn_id": "t1",
        "date": "2025-04-01",
        "description": "SWIGGY",
        "amount": 250.0,
        "type": "debit",
        "source_bank": "HDFC",
        "account_type": "Savings Account",
        "category": "Food",
        "notes": "",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _encrypted_frame(session_id: str, df: pd.DataFrame | None = None) -> bytes:
    from shared import crypto

    body = budget_sessions._compress_frame(df if df is not None else _budget_frame())
    return crypto.encrypt(body, aad=session_id)


class _BudgetConn:
    """Stateful fake DB connection for budget session tests."""

    def __init__(self, **kwargs):
        self.owner = kwargs.get("owner", USER_A.user_id)
        self.payload = kwargs.get("payload")
        self.accounts = kwargs.get("accounts", {"filename": "hdfc.csv", "bank": "HDFC", "rows": 1})
        self.metrics = kwargs.get("metrics")
        self.exists = kwargs.get("exists", True)
        self.raise_on_owner = kwargs.get("raise_on_owner", False)
        self.rows = kwargs.get("rows", [])
        self.session_id = kwargs.get("session_id", "sess-1")
        self.created_at = kwargs.get("created_at", pd.Timestamp("2025-04-01"))
        self.byte_size = kwargs.get("byte_size", 128)
        self.period = kwargs.get("period", "2025-04-01..2025-04-01")
        self.insert_session_id = kwargs.get("insert_session_id", "sess-1")
        self.queries: list[str] = []
        self.updates: list[tuple] = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(sql.split()))
        sql_norm = " ".join(sql.split())
        if "SELECT user_id FROM sessions WHERE session_id" in sql_norm and "upload_type = 'budget'" in sql_norm:
            if self.raise_on_owner:
                raise RuntimeError("connection reset")
            self._result = None if not self.exists else (self.owner,)
        elif "FROM budget_payloads" in sql_norm and "SELECT" in sql_norm:
            if self.rows:
                self._result = self.rows.pop(0)
            elif self.payload is not None:
                self._result = (self.payload, self.accounts)
            else:
                self._result = None
        elif "JOIN budget_payloads" in sql_norm or "JOIN sessions s ON b.session_id" in sql_norm:
            self._result = self.rows if self.rows else []
        elif "INSERT INTO sessions" in sql_norm:
            self._result = (self.insert_session_id,)
        elif sql_norm.startswith("UPDATE budget_payloads"):
            self.updates.append(params)
            self._result = None
        elif sql_norm.startswith("DELETE FROM"):
            self._result = None
        elif "budget_txn_flags" in sql_norm:
            self._result = kwargs_rows if (kwargs_rows := getattr(self, "_flag_rows", [])) else None
        else:
            self._result = None
        return self

    def fetchone(self):
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return self._result
        return []


@pytest.fixture
def budget_db(monkeypatch):
    holder: dict = {}

    @contextmanager
    def _connect(row_factory=None):
        yield holder["conn"]

    monkeypatch.setattr(budget_sessions.db, "connect", _connect)

    def install(**kwargs):
        holder["conn"] = _BudgetConn(**kwargs)
        return holder["conn"]

    return install
def test_budget_decode_and_get_session(budget_db):
    enc = _encrypted_frame("sess-1")
    df, acc = budget_sessions.decode_budget_payload(enc, {"bank": "HDFC"}, "sess-1")
    assert len(df) == 1
    df2, acc2 = budget_sessions.decode_budget_payload(None, json.dumps({"bank": "HDFC"}), "sess-1")
    assert df2.empty

    budget_db(owner=USER_A.user_id, payload=enc)
    with identity_scope(USER_A):
        got, meta = budget_sessions.get_budget_session("sess-1")
    assert len(got) == 1

    budget_db(owner=USER_A.user_id, payload=None, exists=True)
    with identity_scope(USER_A):
        empty, meta = budget_sessions.get_budget_session("sess-1")
    assert empty.empty

def test_budget_delete_session(budget_db):
    budget_db(owner=USER_A.user_id)
    with identity_scope(USER_A):
        assert budget_sessions.delete_budget_session(USER_A.user_id, "sess-1") is True

def test_budget_ensure_columns_and_merge():
    df = pd.DataFrame([{"date": "2025-01-01", "description": "x", "amount": 1, "type": "debit"}])
    out = budget_sessions._ensure_columns(df, {"filename": "icici_credit_card.csv", "bank": "ICICI"})
    assert out.iloc[0]["source_bank"] == "ICICI"
    assert out.iloc[0]["account_type"] == "Credit Card"

    df2 = pd.DataFrame([
        {"session_id": "s1", "date": "2025-01-01", "description": "x", "amount": 1,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings"},
    ])
    assert len(budget_sessions._merge_overlapping_statements(df2)) == 1

    no_key = pd.DataFrame([
        {"session_id": "s1", "foo": 1},
        {"session_id": "s2", "foo": 1},
    ])
    assert len(budget_sessions._merge_overlapping_statements(no_key)) == 2

def test_budget_get_all_and_list(monkeypatch):
    sid1 = "sess-a"
    frame = _budget_frame()
    blob = budget_sessions._compress_frame(frame)

    from shared import crypto

    enc = crypto.encrypt(blob, aad=sid1)
    metrics = crypto.encrypt_json({"total_income": 1000.0, "total_expense": 250.0}, aad=sid1)
    session_rows = [(enc, sid1, {"filename": "hdfc.csv", "bank": "HDFC", "rows": 1})]
    list_rows = [(sid1, pd.Timestamp("2025-04-01"), {"filename": "hdfc.csv", "bank": "HDFC", "rows": 1},
                  metrics, 100, "2025-04-01..2025-04-01")]

    class MultiConn:
        def execute(self, sql, params=None):
            sql_norm = " ".join(sql.split())
            if "ORDER BY s.created_at DESC" in sql_norm:
                self._result = list_rows
            elif "JOIN sessions s ON b.session_id = s.session_id" in sql_norm:
                self._result = session_rows
            else:
                self._result = None
            return self

        def fetchone(self):
            return self._result if isinstance(self._result, tuple) else None

        def fetchall(self):
            return self._result if isinstance(self._result, list) else []

    holder = {"conn": MultiConn()}

    @contextmanager
    def _connect(row_factory=None):
        yield holder["conn"]

    monkeypatch.setattr(budget_sessions.db, "connect", _connect)

    master, accounts = budget_sessions.get_all_budget_sessions(USER_A.user_id)
    assert not master.empty
    assert accounts.get("bank") == "HDFC" or "HDFC" in str(accounts)

    listing = budget_sessions.list_budget_sessions(USER_A.user_id)
    assert listing and listing[0]["bank"] == "HDFC"

def test_budget_save_and_dedup(monkeypatch, budget_db):
    monkeypatch.setattr(budget_sessions.storage, "check_duplicate_upload", lambda h, u: "existing-sid")
    sid = budget_sessions.save_budget_session("new-sid", USER_A.user_id, _budget_frame(), {"bank": "HDFC"})
    assert sid == "existing-sid"

    monkeypatch.setattr(budget_sessions.storage, "check_duplicate_upload", lambda h, u: None)
    conn = budget_db(insert_session_id="winning-sid")
    df = _budget_frame()
    sid2 = budget_sessions.save_budget_session("new-sid", USER_A.user_id, df, {"bank": "HDFC", "rows": 1})
    assert sid2 == "winning-sid"
    assert any("INSERT INTO budget_payloads" in q for q in conn.queries)

def test_budget_sessions_encoding_and_hash(monkeypatch):
    assert budget_sessions._compress_frame(None) == b""
    assert budget_sessions._compress_frame(pd.DataFrame()) == b""
    assert budget_sessions._decompress_frame(None).empty
    assert budget_sessions._decompress_frame(b"").empty

    empty_hash = budget_sessions._budget_ledger_hash(pd.DataFrame(), "user-1")
    assert empty_hash.startswith("budget_empty_")
    df = _budget_frame()
    h1 = budget_sessions._budget_ledger_hash(df, "user-1")
    h2 = budget_sessions._budget_ledger_hash(df, "user-2")
    assert h1 != h2

    real_hash = pd.util.hash_pandas_object

    def flaky_hash(subset, **kwargs):
        raise RuntimeError("unhashable")

    monkeypatch.setattr(pd.util, "hash_pandas_object", flaky_hash)
    h3 = budget_sessions._budget_ledger_hash(df, "user-1")
    assert len(h3) == 64

    def bad_dates(series):
        raise RuntimeError("bad dates")

    monkeypatch.setattr(budget_sessions.pd, "to_datetime", bad_dates)
    out = budget_sessions._normalise_dates(pd.Series(["2025-01-01"]))
    assert out.iloc[0] == "2025-01-01"

def test_budget_sessions_helpers():
    from domains.budget import sessions as budget_sessions

    df = pd.DataFrame([
        {"date": pd.Timestamp("2025-01-01"), "amount": 100.0, "description": "Test", "source_bank": "HDFC"},
    ])
    blob = budget_sessions._compress_frame(df)
    restored = budget_sessions._decompress_frame(blob)
    assert len(restored) == 1
    assert budget_sessions._bank_from_filename("hdfc_savings_jan2025.csv") == "HDFC"
    assert budget_sessions._account_type_from_filename("icici_credit_card.csv") == "Credit Card"

def test_budget_sessions_remaining_edges(budget_db, monkeypatch):
    assert budget_sessions._statement_period(pd.DataFrame({"date": ["not-a-date"]})) == ""
    df = budget_sessions._ensure_columns(
        pd.DataFrame([{"date": "2025-01-01", "description": "x", "amount": 1, "type": "debit"}]),
        "not-json",
    )
    assert df.iloc[0]["category"] == "Uncategorized"

    from shared import crypto

    bad_metrics = b"not-valid"
    budget_db(
        owner=USER_A.user_id,
        rows=[("sess-x", pd.Timestamp("2025-04-01"), {"filename": "x.csv", "rows": 0}, bad_metrics, 0, "")],
    )
    listing = budget_sessions.list_budget_sessions(USER_A.user_id)
    assert listing[0]["total_income"] == 0.0

    enc = _encrypted_frame("sess-u")
    budget_db(owner=USER_A.user_id, payload=enc, session_id="sess-u")
    with identity_scope(USER_A):
        assert budget_sessions.update_budget_transactions(USER_A.user_id, "sess-u", [{"txn_id": "missing"}]) is True

    class ReapplyConn:
        def execute(self, sql, params=None):
            sql_norm = " ".join(sql.split())
            if "SELECT s.session_id, b.transactions" in sql_norm:
                self._result = [("bad", b"corrupt"), ("empty", None)]
            return self

        def fetchall(self):
            return getattr(self, "_result", [])

    @contextmanager
    def _reconnect(row_factory=None):
        yield ReapplyConn()

    monkeypatch.setattr(budget_sessions.db, "connect", _reconnect)
    monkeypatch.setattr("domains.budget.categorizer.load_user_rules", lambda uid: [])
    assert budget_sessions.reapply_rules_to_all_sessions(USER_A.user_id) == 0

def test_budget_statement_period_and_filenames():
    assert budget_sessions._statement_period(pd.DataFrame()) == ""
    assert budget_sessions._statement_period(pd.DataFrame({"amount": [1]})) == ""
    df = pd.DataFrame({"date": ["2025-01-05", "2025-01-01"]})
    assert budget_sessions._statement_period(df) == "2025-01-01..2025-01-05"
    assert budget_sessions._bank_from_filename("icici_optransaction.csv") == "ICICI"
    assert budget_sessions._bank_from_filename("sbi_stmt.csv") == "SBI"
    assert budget_sessions._bank_from_filename("axis.csv") == "AXIS"
    assert budget_sessions._bank_from_filename("kotak.csv") == "KOTAK"
    assert budget_sessions._bank_from_filename("unknown.csv") == "GENERIC"
    assert budget_sessions._account_type_from_filename("my_current.csv") == "Current Account"
    assert budget_sessions._account_type_from_filename("salary_acct.csv") == "Salary Account"

def test_budget_update_and_reapply(budget_db, monkeypatch):
    enc = _encrypted_frame("sess-1")
    conn = budget_db(owner=USER_A.user_id, payload=enc)

    with identity_scope(USER_A):
        assert budget_sessions.update_budget_transactions(USER_A.user_id, "sess-1", []) is True
        assert budget_sessions.update_budget_transactions(
            USER_A.user_id, "sess-1", [{"txn_id": "t1", "category": "Food", "notes": "lunch"}]
        ) is True

    budget_db(owner=USER_A.user_id, payload=None)
    with identity_scope(USER_A):
        assert budget_sessions.update_budget_transactions(USER_A.user_id, "sess-1", [{"txn_id": "t1"}]) is False

    recoded_df = _budget_frame()
    enc_bytes = _encrypted_frame("sess-r", recoded_df)

    class ReapplyConn(_BudgetConn):
        def execute(self, sql, params=None):
            sql_norm = " ".join(sql.split())
            if "JOIN budget_payloads b ON s.session_id = b.session_id" in sql_norm and "SELECT s.session_id" in sql_norm:
                self._result = [("sess-r", enc_bytes)]
            elif sql_norm.startswith("UPDATE budget_payloads"):
                self.updates.append(params)
            else:
                return super().execute(sql, params)
            return self

    holder = {"conn": ReapplyConn(owner=USER_A.user_id)}

    @contextmanager
    def _connect(row_factory=None):
        yield holder["conn"]

    monkeypatch.setattr(budget_sessions.db, "connect", _connect)
    monkeypatch.setattr(
        "domains.budget.categorizer.load_user_rules",
        lambda uid: [],
    )
    monkeypatch.setattr(
        "domains.budget.categorizer.categorize_transactions",
        lambda df, rules=None: (df.assign(category="Auto"), {}),
    )
    total = budget_sessions.reapply_rules_to_all_sessions(USER_A.user_id)
    assert total >= 1



def test_budget_sessions_decode_errors_and_defaults(monkeypatch):
    from shared import crypto

    conn = FakeDbConn()
    conn.queue_result(fetchall=[(crypto.encrypt(b"bad", aad="s1"), "s1", "{}"), (None, "s2", "{}")])
    monkeypatch.setattr(budget_sessions.db, "connect", lambda: conn)
    df, _ = budget_sessions.get_all_budget_sessions("user-1")
    assert df.empty

    raw = pd.DataFrame([{"amount": 100.0, "type": "debit", "date": "2025-01-01", "description": "X"}])
    blob = budget_sessions._compress_frame(raw)
    conn2 = FakeDbConn()
    conn2.queue_result(fetchall=[(blob, "s3", None)])
    monkeypatch.setattr(budget_sessions.db, "connect", lambda: conn2)
    df2, _ = budget_sessions.get_all_budget_sessions("user-2")
    assert "category" in df2.columns or df2.empty


# ── ownership enforcement (cross-user session access) ─────────────────────────

SID = "budget-session-under-test"


def _auth_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"txn_id": "t1", "date": "2025-04-01", "description": "SWIGGY",
         "amount": 250.0, "type": "debit", "source_bank": "HDFC",
         "account_type": "Savings Account", "category": "Food & Dining", "notes": ""},
    ])


class _AuthFakeConn:
    def __init__(self, owner, payload=b"", exists=True, raise_on_owner=False):
        self.owner = owner
        self.payload = payload
        self.exists = exists
        self.raise_on_owner = raise_on_owner
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(" ".join(sql.split()))
        if "FROM sessions" in sql and "user_id" in sql:
            if self.raise_on_owner:
                raise RuntimeError("connection reset")
            self._result = None if not self.exists else (self.owner,)
        elif "FROM budget_payloads" in sql:
            self._result = (self.payload, {}) if self.payload else None
        else:
            self._result = None
        return self

    def fetchone(self):
        return self._result

    def fetchall(self):
        return []


@pytest.fixture
def fake_db(monkeypatch):
    holder = {}

    @contextmanager
    def _connect(row_factory=None):
        yield holder["conn"]

    monkeypatch.setattr(budget_sessions.db, "connect", _connect)

    def install(**kwargs):
        holder["conn"] = _AuthFakeConn(**kwargs)
        return holder["conn"]

    return install


def _encrypted_auth(session_id: str) -> bytes:
    from shared import crypto

    body = zlib.compress(_auth_frame().to_json(orient="records").encode("utf-8"))
    return crypto.encrypt(body, aad=session_id)


def test_another_users_session_is_denied(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 404


def test_denial_does_not_fetch_the_payload(fake_db):
    conn = fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException):
            budget_sessions.get_budget_session(SID)

    assert not any("budget_payloads" in q for q in conn.queries)


def test_the_owner_is_served(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))

    with identity.identity_scope(USER_A):
        df, _ = budget_sessions.get_budget_session(SID)

    assert len(df) == 1
    assert df.iloc[0]["description"] == "SWIGGY"


def test_anonymous_caller_cannot_read_an_owned_session(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))

    with identity.identity_scope(None):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 404


def test_absent_and_denied_are_indistinguishable(fake_db):
    fake_db(owner=None, exists=False)
    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as absent:
            budget_sessions.get_budget_session(SID)

    fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))
    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as denied:
            budget_sessions.get_budget_session(SID)

    assert absent.value.status_code == denied.value.status_code == 404
    assert absent.value.detail == denied.value.detail


def test_ownership_check_fails_closed_when_the_lookup_errors(fake_db):
    fake_db(owner=USER_A.user_id, raise_on_owner=True)

    with identity.identity_scope(USER_A):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.get_budget_session(SID)

    assert exc.value.status_code == 503


def test_delete_denies_another_users_session(fake_db):
    conn = fake_db(owner=USER_A.user_id)

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.delete_budget_session(USER_B.user_id, SID)

    assert exc.value.status_code == 404
    assert not any("DELETE" in q for q in conn.queries)


def test_delete_removes_the_owners_session(fake_db):
    conn = fake_db(owner=USER_A.user_id)

    with identity.identity_scope(USER_A):
        assert budget_sessions.delete_budget_session(USER_A.user_id, SID) is True

    deletes = [q for q in conn.queries if q.startswith("DELETE")]
    assert len(deletes) == 1
    assert "user_id = %s" in deletes[0]


def test_update_denies_another_users_session(fake_db):
    fake_db(owner=USER_A.user_id, payload=_encrypted_auth(SID))

    with identity.identity_scope(USER_B):
        with pytest.raises(HTTPException) as exc:
            budget_sessions.update_budget_transactions(
                USER_B.user_id, SID, [{"txn_id": "t1", "category": "Hijacked"}]
            )

    assert exc.value.status_code == 404


def test_owns_record_with_the_callers_own_id_is_a_no_op():
    with identity.identity_scope(USER_B):
        caller = identity.current_user_id()
        assert identity.owns_record(caller) is True
        assert identity.owns_record(USER_A.user_id) is False
