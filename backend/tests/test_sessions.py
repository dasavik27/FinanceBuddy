"""
Tests for session memory bounding and record serialization.

df_to_records was rewritten from a per-cell Python lambda into vectorized column
operations, so `reference_df_to_records` below is a literal transcription of the
original and the equivalence test is the specification - same pattern as
test_reconciliation_equivalence.py.
"""

import random

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds import sessions
from domains.mutual_funds.sessions import _compact_dtypes, df_to_records


# ---------------------------------------------------------------------------
# df_to_records equivalence
# ---------------------------------------------------------------------------

def reference_df_to_records(df: pd.DataFrame) -> list:
    """Literal transcription of the pre-optimization implementation."""
    if df is None or df.empty:
        return []
    df2 = df.copy()
    for col in df2.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df2[col] = df2[col].dt.strftime("%Y-%m-%d")
    for col in df2.columns:
        df2[col] = df2[col].apply(
            lambda v: None if (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else v
        )
    return df2.to_dict(orient="records")


def _random_frame(rng: random.Random) -> pd.DataFrame:
    n = rng.randrange(1, 12)
    funds = ["Axis Bluechip", "SBI Small Cap", "HDFC Flexi", "Parag Parikh"]
    data = {
        "Fund": [rng.choice(funds) for _ in range(n)],
        "Type": [rng.choice(["Purchase", "Redemption", "Switch In"]) for _ in range(n)],
        "Units": [rng.choice([0.0, 12.345, float("nan"), 9_999_999.5]) for _ in range(n)],
        "NAV": [rng.choice([100.5, float("inf"), float("-inf"), 55.0]) for _ in range(n)],
        "Amount": [rng.choice([1000.0, 0.0, float("nan"), 10_000_000.50]) for _ in range(n)],
        "Count": [rng.randrange(0, 100) for _ in range(n)],
        "Date": [
            rng.choice([pd.Timestamp("2024-01-15"), pd.Timestamp("2020-06-30"), pd.NaT])
            for _ in range(n)
        ],
        "Note": [rng.choice(["ok", None, "", float("nan")]) for _ in range(n)],
    }
    return pd.DataFrame(data)


def _normalize(records):
    """NaN != NaN, so canonicalize any residual float nan to None before comparing."""
    out = []
    for row in records:
        clean = {}
        for k, v in row.items():
            if isinstance(v, float) and not np.isfinite(v):
                clean[k] = None
            elif v is pd.NaT:
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out


def test_df_to_records_matches_reference_on_random_frames():
    rng = random.Random(20260729)
    for i in range(150):
        df = _random_frame(rng)
        expected = _normalize(reference_df_to_records(df))
        actual = _normalize(df_to_records(df))
        assert actual == expected, (
            f"divergence on case {i}\nframe=\n{df}\nexpected={expected}\nactual={actual}"
        )


def test_df_to_records_emits_no_non_json_floats():
    df = pd.DataFrame({
        "a": [float("nan"), float("inf"), float("-inf"), 1.5],
        "b": ["x", "y", None, "z"],
    })
    for row in df_to_records(df):
        for value in row.values():
            assert not (isinstance(value, float) and not np.isfinite(value)), (
                f"NaN/Inf leaked into the JSON payload: {row}"
            )


def test_df_to_records_handles_empty_and_none():
    assert df_to_records(None) == []
    assert df_to_records(pd.DataFrame()) == []


def test_df_to_records_survives_categorical_columns():
    """Compaction makes columns categorical, and category dtype rejects None."""
    df = pd.DataFrame({
        "Fund": ["Axis Bluechip", "Axis Bluechip", "SBI Small Cap"],
        "Units": [1.0, float("nan"), 3.0],
    })
    # Force the dtype rather than relying on the size heuristic - the behaviour
    # under test is serialization of a categorical, not when compaction triggers.
    df["Fund"] = df["Fund"].astype("category")

    records = df_to_records(df)
    assert records[0]["Fund"] == "Axis Bluechip"
    assert records[1]["Units"] is None


def test_df_to_records_preserves_monetary_precision():
    """
    Guards the decision not to downcast money to float32: 10000000.50 needs 10
    significant digits and float32 carries about 7.
    """
    df = pd.DataFrame({"Amount": [10_000_000.50, 12_345_678.91]})
    _compact_dtypes(df)
    records = df_to_records(df)
    assert records[0]["Amount"] == pytest.approx(10_000_000.50, abs=1e-6)
    assert records[1]["Amount"] == pytest.approx(12_345_678.91, abs=1e-6)


# ---------------------------------------------------------------------------
# dtype compaction
# ---------------------------------------------------------------------------

def test_compaction_shrinks_repeated_strings():
    n = 2000
    df = pd.DataFrame({
        "Fund": ["Some Rather Long Mutual Fund Name - Direct Plan Growth"] * n,
        "Type": ["Purchase"] * n,
        "Amount": np.linspace(1000, 99999, n),
    })
    before = df.memory_usage(deep=True).sum()
    _compact_dtypes(df)
    after = df.memory_usage(deep=True).sum()

    assert after < before / 2, f"expected a large saving, got {before} -> {after}"


def test_compaction_leaves_high_cardinality_columns_alone():
    # A category dictionary the same size as the column is pure overhead.
    # Asserting "not category" rather than "== object" keeps this independent of
    # the pandas default string dtype, which changed in pandas 3.
    df = pd.DataFrame({"Fund": [f"Fund {i}" for i in range(100)]})
    _compact_dtypes(df)
    assert df["Fund"].dtype.name != "category"


def test_compaction_does_not_alter_values():
    df = pd.DataFrame({
        "Fund": ["A", "B", "A", "A"],
        "Category": ["Equity", "Debt", "Equity", "Equity"],
        "Amount": [1.5, 2.5, 3.5, 4.5],
    })
    original = df.copy()
    _compact_dtypes(df)
    pd.testing.assert_series_equal(
        df["Fund"].astype(object), original["Fund"], check_dtype=False
    )
    pd.testing.assert_series_equal(df["Amount"], original["Amount"])


def test_compaction_is_safe_on_empty_frame():
    assert _compact_dtypes(pd.DataFrame()) is not None


# ---------------------------------------------------------------------------
# Resident-session bounding
# ---------------------------------------------------------------------------

class _FakePortfolio:
    def __init__(self, tag):
        self.tag = tag


@pytest.fixture
def clean_store(monkeypatch):
    monkeypatch.setattr(sessions, "_SESSIONS", sessions.OrderedDict())
    monkeypatch.setattr(sessions, "MAX_RESIDENT_SESSIONS", 3)
    return sessions._SESSIONS


def test_resident_sessions_are_capped(clean_store):
    for i in range(10):
        sessions._remember(f"s{i}", _FakePortfolio(i))

    assert len(clean_store) == 3, "resident session count is not bounded"
    assert sessions.session_stats()["resident"] == 3


def test_eviction_drops_least_recently_used(clean_store):
    for sid in ("a", "b", "c"):
        sessions._remember(sid, _FakePortfolio(sid))

    # Touch 'a' so 'b' becomes the eviction candidate.
    clean_store.move_to_end("a")
    sessions._remember("d", _FakePortfolio("d"))

    assert "a" in clean_store
    assert "b" not in clean_store
    assert set(clean_store) == {"a", "c", "d"}


def test_get_session_raises_404_when_absent_from_memory_and_disk(clean_store, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(sessions.storage, "load_session", lambda sid: None)
    with pytest.raises(HTTPException) as excinfo:
        sessions.get_session("nope")
    assert excinfo.value.status_code == 404


def test_evicted_session_is_rehydrated_from_disk(clean_store, monkeypatch):
    """Eviction must be invisible to callers - that is what makes the cap safe."""
    df_h = pd.DataFrame({"Fund": ["A"], "ISIN": ["INF1"], "Units": [10.0]})
    df_t = pd.DataFrame({"Fund": ["A"], "Type": ["Purchase"], "Amount": [100.0]})
    df_s = pd.DataFrame()

    loaded = []

    def fake_load(sid):
        loaded.append(sid)
        return df_h.copy(), df_t.copy(), df_s.copy(), False

    refreshed = []

    class Stub:
        def __init__(self, *a, **k):
            pass

        def update_live_navs(self):
            refreshed.append(1)

    monkeypatch.setattr(sessions.storage, "load_session", fake_load)
    monkeypatch.setattr(sessions, "Portfolio", Stub)
    # The disk path now authorizes against the registry before loading frames, so the
    # session has to exist there. That requirement is the fix for a real leak: frames
    # whose registry row has been deleted must not be loadable, because with the row
    # gone there is nothing left to say who owns them. Unowned (None) keeps this test
    # about rehydration rather than about authorization.
    monkeypatch.setattr(sessions.storage, "get_session_owner", lambda sid: (True, None))

    sessions.get_session("gone")
    assert loaded == ["gone"]
    assert refreshed == [1], (
        "rehydrated session was not revalued; it would serve CAS-era NAVs"
    )
    assert "gone" in clean_store
