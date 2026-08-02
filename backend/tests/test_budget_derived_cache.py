"""
The budget derived cache.

Correctness first, speed second. A cache key that collides across two users' ledgers
serves one person's bank transactions to another, so the tests that matter here are the
ones asserting that different inputs get different entries - not the ones asserting a
hit. This mirrors the contract in test_derived_cache.py.
"""

import threading

import pandas as pd
import pytest

from shared.services.cache import DERIVED_CACHE
from domains.budget import derived


@pytest.fixture(autouse=True)
def clear_cache():
    DERIVED_CACHE.clear()
    yield
    DERIVED_CACHE.clear()


def _frame(amount=100.0, description="SWIGGY", rows=3):
    return pd.DataFrame([
        {"txn_id": f"t{i}", "date": f"2025-04-0{i + 1}", "description": description,
         "amount": amount + i, "type": "debit", "source_bank": "HDFC",
         "account_type": "Savings Account", "category": "Food & Dining"}
        for i in range(rows)
    ])


class _Counter:
    def __init__(self, value="computed"):
        self.calls = 0
        self.value = value

    def __call__(self):
        self.calls += 1
        return self.value


def test_repeat_calls_compute_once():
    df = _frame()
    producer = _Counter()
    for _ in range(8):
        derived.recurring(df, producer)
    assert producer.calls == 1


def test_a_different_ledger_gets_its_own_entry():
    a, b = _Counter("a"), _Counter("b")
    assert derived.recurring(_frame(amount=100.0), a) == "a"
    assert derived.recurring(_frame(amount=999.0), b) == "b"
    assert (a.calls, b.calls) == (1, 1)


def test_same_shape_different_values_gets_its_own_entry():
    """A shape-only fingerprint would collide here, which is the dangerous case."""
    a, b = _Counter("a"), _Counter("b")
    derived.recurring(_frame(description="SWIGGY"), a)
    assert derived.recurring(_frame(description="ZOMATO"), b) == "b"


def test_row_order_changes_the_key():
    """
    Order matters for the cumulative-balance and reconciliation views, so two frames
    differing only in order must not share an entry.
    """
    df = _frame(rows=4)
    a, b = _Counter("a"), _Counter("b")
    derived.reconciliation(df, a)
    derived.reconciliation(df.iloc[::-1], b)
    assert b.calls == 1


def test_the_engines_do_not_share_a_namespace():
    """recurring() and anomalies() over one frame are different answers."""
    df = _frame()
    r, a = _Counter("recurring"), _Counter("anomalies")
    assert derived.recurring(df, r) == "recurring"
    assert derived.anomalies(df, a) == "anomalies"


def test_user_flags_change_the_transfer_key():
    """An override changes the answer without changing the frame."""
    df = _frame()
    a, b = _Counter("without"), _Counter("with")
    assert derived.transfers(df, "none", a) == "without"
    assert derived.transfers(df, "abc123", b) == "with"


def test_account_metadata_changes_the_account_key():
    df = _frame()
    a, b = _Counter("before"), _Counter("after")
    assert derived.account_summary(df, "none", a) == "before"
    assert derived.account_summary(df, "limit-set", b) == "after"


def test_concurrent_callers_collapse_to_one_computation():
    df = _frame()
    barrier = threading.Barrier(6)
    calls = []
    lock = threading.Lock()

    def producer():
        with lock:
            calls.append(1)
        return "value"

    def worker():
        barrier.wait()
        derived.recurring(df, producer)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1


def test_an_unhashable_frame_bypasses_the_cache_rather_than_colliding():
    """
    If a fingerprint cannot be computed we must recompute, never guess at a key.
    A guessed key is how one ledger's results get served for another.
    """
    df = _frame()
    df["weird"] = [{"nested": 1}, {"nested": 2}, {"nested": 3}]

    assert derived.frame_fingerprint(df) is None

    producer = _Counter()
    derived.recurring(df, producer)
    derived.recurring(df, producer)
    assert producer.calls == 2


def test_empty_and_none_frames_are_distinguishable():
    assert derived.frame_fingerprint(None) == "none"
    assert derived.frame_fingerprint(pd.DataFrame()) == "empty"


def test_fingerprint_is_stable_across_equal_frames():
    assert derived.frame_fingerprint(_frame()) == derived.frame_fingerprint(_frame())
