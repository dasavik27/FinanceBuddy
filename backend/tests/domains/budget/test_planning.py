
"""Budget envelope planning."""

import pandas as pd
import pytest

from domains.budget.planning import envelope_status


def _txn(txn_id, date, description, amount, kind, bank="HDFC",
         account_type="Savings Account", category="Uncategorized", balance=None):
    row = {
        "txn_id": txn_id, "date": date, "description": description, "amount": amount,
        "type": kind, "source_bank": bank, "account_type": account_type,
        "category": category, "notes": "",
    }
    if balance is not None:
        row["balance"] = balance
    return row


def test_an_exceeded_envelope_is_over():
    df = pd.DataFrame([
        _txn("a", "2025-04-10", "RESTAURANT", 12000.0, "debit", category="Food & Dining")
    ])
    status = envelope_status(df, {"Food & Dining": 10000.0})[0]
    assert status["status"] == "over"
    assert status["remaining"] == 0.0

def test_an_untouched_envelope_still_appears():
    df = pd.DataFrame([_txn("a", "2025-04-10", "SWIGGY", 100.0, "debit", category="Other")])
    statuses = envelope_status(df, {"Travel": 5000.0})
    assert len(statuses) == 1 and statuses[0]["spent"] == 0.0

def test_envelope_pace_distinguishes_early_from_late():
    """60% of a budget is fine on the 25th and a problem on the 3rd."""
    early = pd.DataFrame([
        _txn("a", "2025-04-03", "RESTAURANT", 6000.0, "debit", category="Food & Dining")
    ])
    late = pd.DataFrame([
        _txn("a", "2025-04-25", "RESTAURANT", 6000.0, "debit", category="Food & Dining")
    ])
    caps = {"Food & Dining": 10000.0}

    assert envelope_status(early, caps)[0]["status"] == "ahead_of_pace"
    assert envelope_status(late, caps)[0]["status"] == "on_track"



"""Budget planning DB and envelope branches."""

import pandas as pd
import pytest

from domains.budget.planning import envelope_status, load_envelopes, set_envelope




import pandas as pd
import pytest

from domains.budget.planning import envelope_status, load_envelopes, set_envelope


def test_planning_envelope_status_and_db(monkeypatch):
    assert envelope_status(pd.DataFrame(), {}) == []
    df = pd.DataFrame([
        {"date": pd.Timestamp("2025-08-01"), "category": "Food", "amount": -500.0, "type": "debit"},
        {"date": pd.Timestamp("2025-08-10"), "category": "Food", "amount": -300.0, "type": "debit"},
    ])
    rows = envelope_status(df, {"Food": 5000.0}, as_of=pd.Timestamp("2025-08-15"))
    assert rows[0]["category"] == "Food"
    assert rows[0]["spent"] == -800.0

    assert load_envelopes(None) == {}


    class FakeConn:
        def execute(self, sql, params=None):
            if "SELECT" in sql:
                class Result:
                    def fetchall(self_inner):
                        return [("Food", 5000.0)]
                return Result()
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shared.db.connect", lambda: FakeConn())
    caps = load_envelopes("user-1")
    assert caps["Food"] == 5000.0
    set_envelope("user-1", "Travel", 2000.0)
    set_envelope("user-1", "Travel", None)

def test_planning_envelope_status_branches():
    df = pd.DataFrame([
        {"date": pd.Timestamp("2025-08-01"), "category": "Food", "amount": 5500.0, "type": "debit"},
    ])
    over = envelope_status(df, {"Food": 5000.0}, as_of=pd.Timestamp("2025-08-02"))
    assert over[0]["status"] == "over"

    df2 = pd.DataFrame([
        {"date": pd.Timestamp("2025-08-01"), "category": "Travel", "amount": -100.0, "type": "debit"},
    ])
    on_track = envelope_status(df2, {"Travel": 5000.0}, as_of=pd.Timestamp("2025-08-02"))
    assert on_track[0]["status"] == "on_track"



def test_planning_envelope_status_single_line_gap():
    caps = {"Food": 10000.0}
    df_plan = pd.DataFrame([
        {"date": "2024-06-20", "amount": 3000.0, "type": "debit", "category": "Food"},
    ])
    statuses = envelope_status(df_plan, caps, as_of=pd.Timestamp("2024-06-20"))
    assert statuses and statuses[0]["category"] == "Food"

def test_planning_envelope_slightly_ahead():
    from domains.budget import planning

    caps = {"Food": 10000.0}
    df = pd.DataFrame([{"date": "2024-06-20", "amount": 7000.0, "type": "debit", "category": "Food"}])
    statuses = planning.envelope_status(df, caps, as_of=pd.Timestamp("2024-06-20"))
    assert any(s["status"] == "slightly_ahead" for s in statuses)

