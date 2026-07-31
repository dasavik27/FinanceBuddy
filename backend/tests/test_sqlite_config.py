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

from shared import db as db_module
from shared import storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "meta.sqlite3"
    # shared/db.py is the only module that names the database, so one patch redirects
    # every store. db.connect() reads DB_PATH at call time, not at import.
    monkeypatch.setattr(db_module, "DB_PATH", str(path))
    storage._init_db()
    return str(path)


# ── one connection authority ──────────────────────────────────────────────────

def test_only_shared_db_opens_connections():
    """
    Every database connection must come from shared/db.py.

    Seven call sites used to open their own. Five of them used a bare
    `sqlite3.connect` with no busy_timeout, so a concurrent CAS upload - which holds a
    write transaction for most of a second - made them fail outright with "database is
    locked" instead of waiting; and `with sqlite3.connect(...)` commits without
    closing, so each held its locks until garbage collection.

    This also guards the Postgres migration: a connection opened outside shared/db.py
    is one that will not come from the pool.
    """
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    allowed = {backend / "shared" / "db.py"}

    offenders = []
    for path in backend.rglob("*.py"):
        if path in allowed or "tests" in path.parts or ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "sqlite3.connect(" in text:
            offenders.append(str(path.relative_to(backend)))

    assert not offenders, (
        "these modules open their own connection instead of using shared.db.connect(): "
        f"{offenders}"
    )


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


def test_session_payload_lookup_is_a_primary_key_seek(db):
    """
    load_session reads the payload with `WHERE session_id=?` on a table holding every
    session's blob, so that lookup must not be a scan.

    The three mf_* tables this replaced each needed an explicit index for the same
    query, created in two places because to_sql built the tables lazily. session_id is
    now the PRIMARY KEY, so the index is structural and cannot go missing.
    """
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-01-01"), "Fund": "F",
        "Type": "Purchase", "Units": 1.0, "Amount": 100.0, "NAV": 100.0,
    }])
    storage.save_session("sid-index-test", df_h, df_t, pd.DataFrame(), is_partial=False)

    with storage._connect() as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT holdings, transactions, sips, meta FROM session_payloads "
            "WHERE session_id = ?",
            ("sid-index-test",),
        ).fetchall()
    text = " ".join(str(row) for row in plan)
    assert "SEARCH" in text, f"payload lookup is not an index seek: {text}"


def test_session_payload_write_is_one_row_per_session(db):
    """Rehydration is one round trip, where the mf_* version took three."""
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    storage.save_session("sid-one-row", df_h, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    with storage._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM session_payloads WHERE session_id = ?", ("sid-one-row",)
        ).fetchone()[0]
    assert count == 1


# ── schema drift ──────────────────────────────────────────────────────────────

def test_parser_drift_does_not_break_uploads(db):
    """
    A parser gaining, losing or renaming a field must not break uploads.

    This used to be a real hazard: the mf_* tables had no explicit DDL, so their
    schema was frozen from the first upload and a later frame with an extra column
    failed with an opaque `DatabaseError: Execution failed`. The mitigation was a
    runtime `ALTER TABLE ADD COLUMN` using document-controlled identifiers.

    The payload codec removes the failure mode rather than mitigating it — a blob has
    no schema to drift from. The assertion is therefore on the round trip, which is
    what actually matters, instead of on the physical column set.
    """
    base = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0}])
    storage.save_session("sid-drift-1", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    # A parser gains a field.
    wider = pd.DataFrame([{
        "Fund": "G", "Units": 2.0, "Market Value": 200.0, "BrandNewColumn": "x",
    }])
    storage.save_session("sid-drift-2", wider, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    loaded = storage.load_session("sid-drift-2")
    assert loaded is not None
    df_h, _, _, _ = loaded
    assert "BrandNewColumn" in df_h.columns, "new parser field was dropped"
    assert df_h["BrandNewColumn"].iloc[0] == "x"

    # A narrower frame afterwards still works, and does not inherit the wider session's
    # column — each payload is independent, where one shared table could not be.
    storage.save_session("sid-drift-3", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)
    loaded = storage.load_session("sid-drift-3")
    assert loaded is not None
    assert "BrandNewColumn" not in loaded[0].columns


def test_payload_round_trip_preserves_datetimes_in_every_frame(db):
    """
    Both transactions and SIPs carry a Date column that downstream code (FIFO lots,
    XIRR, rolling returns) requires as datetime64.

    SQLite had no datetime type, so the old read path restored these with a hardcoded
    check for a column named "Date" — added for transactions, and only later for SIPs
    after the missing conversion was found to be misparsing ambiguous days via
    `dayfirst=True`. The codec records datetime columns by name, so this is general.
    """
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-03-11"), "Fund": "F",
        "Type": "Purchase", "Units": 1.0, "Amount": 100.0, "NAV": 100.0,
    }])
    df_s = pd.DataFrame([{"Date": pd.Timestamp("2024-03-11"), "Fund": "F", "Amount": 500.0}])

    storage.save_session("sid-dt", df_h, df_t, df_s, is_partial=False)
    loaded = storage.load_session("sid-dt")
    assert loaded is not None
    _, out_t, out_s, _ = loaded

    for name, frame in (("transactions", out_t), ("sips", out_s)):
        assert pd.api.types.is_datetime64_any_dtype(frame["Date"]), \
            f"{name}.Date came back as {frame['Date'].dtype}, not datetime64"
        # The 11th of March, not the 3rd of November.
        assert frame["Date"].iloc[0] == pd.Timestamp("2024-03-11")


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_payload_preserves_datetime_resolution(db, unit):
    """
    The codec writes naive datetimes as integer epoch counts, so it must restore them
    at the resolution they were written at.

    This failed in exactly one direction and silently. pandas has supported
    non-nanosecond datetimes since 2.0 and `pd.to_datetime` yields datetime64[us] on
    pandas 3, but the unit was read via `dtype.unit` - which only pandas *extension*
    dtypes expose. A tz-naive column is a plain numpy dtype, so the lookup hit its
    "ns" default and every timestamp came back divided by 1000: 2023 became 1970,
    with no error anywhere. np.datetime_data is the accessor that works for both.
    """
    when = pd.Timestamp("2023-11-07 09:30:00")
    df_t = pd.DataFrame({
        "Date": pd.Series([when], dtype=f"datetime64[{unit}]"),
        "Fund": ["F"], "Type": ["Purchase"], "Units": [1.0],
        "Amount": [100.0], "NAV": [100.0],
    })
    storage.save_session(f"sid-unit-{unit}", pd.DataFrame(), df_t, pd.DataFrame(), is_partial=False)

    loaded = storage.load_session(f"sid-unit-{unit}")
    assert loaded is not None
    _, out_t, _, _ = loaded

    assert pd.api.types.is_datetime64_any_dtype(out_t["Date"])
    assert out_t["Date"].iloc[0] == when, (
        f"datetime64[{unit}] round-tripped to {out_t['Date'].iloc[0]}, expected {when}"
    )


def test_payload_preserves_missing_datetimes_as_nat(db):
    """NaT must survive the integer epoch encoding rather than becoming 1677-09-21."""
    df_t = pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-01", None]),
        "Fund": ["F", "G"], "Type": ["Purchase", "Purchase"], "Amount": [1.0, 2.0],
    })
    storage.save_session("sid-nat", pd.DataFrame(), df_t, pd.DataFrame(), is_partial=False)

    loaded = storage.load_session("sid-nat")
    assert loaded is not None
    out_t = loaded[1]
    assert out_t["Date"].iloc[0] == pd.Timestamp("2024-01-01")
    assert pd.isna(out_t["Date"].iloc[1])


def test_empty_frames_round_trip_without_losing_their_columns(db):
    """A session with no SIPs must restore an empty frame, not a malformed one."""
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    storage.save_session("sid-empty", df_h, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    loaded = storage.load_session("sid-empty")
    assert loaded is not None
    _, out_t, out_s, _ = loaded
    assert out_t.empty and out_s.empty
