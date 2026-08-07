"""
PostgreSQL schema, index coverage and payload round-tripping integration tests.
Runs against real PostgreSQL when TEST_DATABASE_URL is provided.
"""

import pandas as pd
import pytest

from shared import db, storage

from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def seeded(clean_db):
    """A saved session to query against."""
    return clean_db


def test_row_factory_does_not_leak_between_pooled_connections(clean_db):
    """
    A connection borrowed with dict_row must go back to the pool as it came.
    """
    from psycopg.rows import dict_row

    with db.connect(row_factory=dict_row) as conn:
        assert isinstance(conn.execute("SELECT 1 AS n").fetchone(), dict)

    with db.connect() as conn:
        row = conn.execute("SELECT 1 AS n").fetchone()
    assert isinstance(row, tuple), (
        f"pooled connection came back configured as {type(row).__name__}; "
        "a later caller expecting tuples would unpack column names instead of values"
    )


def test_a_dict_row_read_does_not_break_the_next_session_load(clean_db):
    """
    The end-to-end shape of the leak: get_history uses dict_row, load_session does
    not, and in production one routinely follows the other on the same connection.
    """
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    storage.save_session("sid-factory", df_h, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    storage.get_history()                         # borrows with dict_row
    loaded = storage.load_session("sid-factory")  # expects tuples

    assert loaded is not None, "load_session broke after a dict_row query on the same pool"
    assert not loaded[0].empty


def test_session_payload_lookup_is_a_primary_key_seek(clean_db):
    """
    load_session reads the payload with `WHERE session_id=?` on a table holding every
    session's blob, so that lookup must not be a scan.
    """
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    df_t = pd.DataFrame([{
        "Date": pd.Timestamp("2024-01-01"), "Fund": "F",
        "Type": "Purchase", "Units": 1.0, "Amount": 100.0, "NAV": 100.0,
    }])
    storage.save_session("sid-index-test", df_h, df_t, pd.DataFrame(), is_partial=False)

    with db.connect() as conn:
        plan = conn.execute(
            "EXPLAIN "
            "SELECT holdings, transactions, sips, meta FROM session_payloads "
            "WHERE session_id = %s",
            ("sid-index-test",),
        ).fetchall()
    text = " ".join(str(row) for row in plan)
    assert "Index Scan" in text, f"payload lookup is not an index seek: {text}"
    assert "Seq Scan" not in text, f"payload lookup fell back to a table scan: {text}"


def test_session_payload_write_is_one_row_per_session(clean_db):
    """Rehydration is one round trip, where the mf_* version took three."""
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    storage.save_session("sid-one-row", df_h, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM session_payloads WHERE session_id = %s", ("sid-one-row",)
        ).fetchone()[0]
    assert count == 1


def test_parser_drift_does_not_break_uploads(clean_db):
    base = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0}])
    storage.save_session("sid-drift-1", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    wider = pd.DataFrame([{
        "Fund": "G", "Units": 2.0, "Market Value": 200.0, "BrandNewColumn": "x",
    }])
    storage.save_session("sid-drift-2", wider, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    loaded = storage.load_session("sid-drift-2")
    assert loaded is not None
    df_h, _, _, _ = loaded
    assert "BrandNewColumn" in df_h.columns, "new parser field was dropped"
    assert df_h["BrandNewColumn"].iloc[0] == "x"

    storage.save_session("sid-drift-3", base, pd.DataFrame(), pd.DataFrame(), is_partial=False)
    loaded = storage.load_session("sid-drift-3")
    assert loaded is not None
    assert "BrandNewColumn" not in loaded[0].columns


def test_payload_round_trip_preserves_datetimes_in_every_frame(clean_db):
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
        assert frame["Date"].iloc[0] == pd.Timestamp("2024-03-11")


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_payload_preserves_datetime_resolution(clean_db, unit):
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


def test_payload_preserves_missing_datetimes_as_nat(clean_db):
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


def test_empty_frames_round_trip_without_losing_their_columns(clean_db):
    df_h = pd.DataFrame([{"Fund": "F", "Units": 1.0, "Market Value": 100.0, "Invested": 90.0}])
    storage.save_session("sid-empty", df_h, pd.DataFrame(), pd.DataFrame(), is_partial=False)

    loaded = storage.load_session("sid-empty")
    assert loaded is not None
    _, out_t, out_s, _ = loaded
    assert out_t.empty and out_s.empty
