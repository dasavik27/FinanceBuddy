"""
SQLite configuration and index coverage.

Under the default rollback journal a writer takes an EXCLUSIVE lock on the whole
database, so a CAS upload blocked every reader and, past the busy timeout, returned
"database is locked" as a 500. These assert the settings that prevent that, plus the
indexes that stop each PAN-scoped read being a full table scan.
"""

import sqlite3

import pandas as pd
import pytest

from shared import storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "meta.sqlite3"
    monkeypatch.setattr(storage, "DB_PATH", str(path))
    storage._init_db()
    return str(path)


# ── pragmas ───────────────────────────────────────────────────────────────────

def test_wal_is_enabled(db):
    with storage._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"journal_mode is {mode!r}; readers will block on writes"


def test_busy_timeout_is_set(db):
    with storage._connect() as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 5000, f"busy_timeout is {timeout}ms; writers will fail instantly under contention"


def test_synchronous_is_not_full(db):
    """FULL fsyncs every commit, which buys nothing on an ephemeral disk."""
    with storage._connect() as conn:
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert sync == 1, f"synchronous={sync}; expected 1 (NORMAL)"


def test_connection_is_closed_even_on_error(db):
    """`with sqlite3.connect(...)` commits but does not close. This wrapper must."""
    captured = {}

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with storage._connect() as conn:
            captured["conn"] = conn
            raise Boom()

    # A closed connection raises ProgrammingError on use.
    with pytest.raises(sqlite3.ProgrammingError):
        captured["conn"].execute("SELECT 1")


def test_transaction_rolls_back_on_error(db):
    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with storage._connect() as conn:
            conn.execute("INSERT INTO users (pan_id) VALUES ('ROLLBACK1A')")
            raise Boom()

    with storage._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE pan_id = 'ROLLBACK1A'"
        ).fetchone()[0]
    assert count == 0, "failed transaction left its row behind"


# ── indexes ───────────────────────────────────────────────────────────────────

def test_pan_scoped_history_query_uses_an_index(db):
    with storage._connect() as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT * FROM sessions WHERE pan_id = ? AND upload_type = ? "
            "ORDER BY created_at DESC",
            ("AAAAA1111A", "mutual_funds"),
        ).fetchall()
    text = " ".join(str(row) for row in plan)
    assert "SEARCH" in text, f"expected an index seek, got: {text}"
    assert "USE TEMP B-TREE" not in text, f"sort not covered by the index: {text}"


def test_mf_tables_are_indexed_on_session_id(db):
    """
    load_session runs three `WHERE session_id=?` reads on tables holding every session.

    Asserts the index EXISTS rather than that the planner uses it. With a handful of
    rows SQLite correctly prefers a scan, so an EXPLAIN-based assertion here says more
    about table size than about schema — it failed on a one-row fixture even though the
    index was present and correct.
    """
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-01-01"), "Fund": "F",
        "Type": "Purchase", "Units": 1.0, "Amount": 100.0, "NAV": 100.0,
    }])
    storage.save_session("sid-index-test", df_h, df_t, pd.DataFrame(), is_partial=False)

    with storage._connect() as conn:
        for table in ("mf_holdings", "mf_transactions"):
            indexes = {
                row[1] for row in conn.execute(f'PRAGMA index_list("{table}")').fetchall()
            }
            assert f"idx_{table}_session_id" in indexes, (
                f"{table} has no session_id index; every rehydration is a full scan "
                f"over every other session's rows. Present: {indexes}"
            )


# ── schema drift ──────────────────────────────────────────────────────────────

def test_parser_drift_does_not_break_uploads(db):
    """
    The mf_* tables have no explicit DDL — their schema is frozen from the first
    upload. A later frame with an extra column used to fail with an opaque
    `DatabaseError: Execution failed`, which on a persistent disk means every upload
    breaks after any parser change.
    """
    base = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0}])
    storage.save_session("sid-drift-1", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    # A parser gains a field.
    wider = pd.DataFrame([{
        "Fund": "G", "Units": 2.0, "Market Value": 200.0, "BrandNewColumn": "x",
    }])
    storage.save_session("sid-drift-2", wider, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    with storage._connect() as conn:
        cols = {r[1] for r in conn.execute('PRAGMA table_info("mf_holdings")')}
    assert "BrandNewColumn" in cols, "new parser field was dropped instead of migrated"

    # And a narrower frame afterwards still works.
    storage.save_session("sid-drift-3", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)
    loaded = storage.load_session("sid-drift-3")
    assert loaded is not None
