"""
cache_key() must refuse inputs it cannot key safely.

The bug this pins: `_key_part` fell through to `str(value)` for anything it did not
recognise. pandas and numpy *truncate* their reprs with "...", so two different
objects render to a byte-identical string — verified below with two 100-row frames
differing only at row 50.

That matters because `request_memo`'s own docstring recommended it for "ledger
rebuilds", i.e. `_get_standard_ledger(df_t)`. Following the documentation as written
would have served one portfolio's ledger to another user in the same request scope.
"""

import numpy as np
import pandas as pd
import pytest

from shared.services.cache import UnsafeCacheKey, cache_key, request_memo, request_scope


def test_dataframes_are_rejected_not_silently_collided():
    a = pd.DataFrame({"Amount": list(range(100))})
    b = a.copy()
    b.loc[50, "Amount"] = 999_999  # differs only where the repr elides

    # The old behaviour: str(a) == str(b), so both produced the same key.
    assert str(a) == str(b), "precondition: pandas truncates these reprs identically"

    with pytest.raises(UnsafeCacheKey):
        cache_key(a)
    with pytest.raises(UnsafeCacheKey):
        cache_key(df=b)


@pytest.mark.parametrize("value", [
    pd.DataFrame({"x": [1]}),
    pd.Series([1, 2, 3]),
    pd.Index([1, 2, 3]),
    np.array([1, 2, 3]),
    {1, 2, 3},
    frozenset({1, 2}),
])
def test_truncating_or_unordered_types_are_rejected(value):
    with pytest.raises(UnsafeCacheKey):
        cache_key(value)


@pytest.mark.parametrize("args,kwargs", [
    (("abc",), {}),
    ((123,), {}),
    ((1.5,), {}),
    ((True,), {}),
    ((None,), {}),
    ((["a", "b"],), {}),
    ((("a", 1),), {}),
    ((), {"ticker": "^NSEI", "days": 9999}),
])
def test_safe_types_still_work(args, kwargs):
    assert isinstance(cache_key(*args, **kwargs), str)


def test_integral_floats_share_a_key_with_their_int():
    assert cache_key(9999.0) == cache_key(9999)


def test_request_memo_bypasses_rather_than_colliding():
    """
    A decorated function called with a DataFrame must compute every time, not return
    a previous caller's result.
    """
    calls = []

    @request_memo("test_ledger")
    def rebuild(df):
        calls.append(len(df))
        return df["Amount"].sum()

    a = pd.DataFrame({"Amount": list(range(100))})
    b = a.copy()
    b.loc[50, "Amount"] = 999_999

    with request_scope():
        first = rebuild(a)
        second = rebuild(b)

    assert first != second, "memo returned a colliding result for a different frame"
    assert len(calls) == 2, "expected the memo to be bypassed, not hit"


def test_request_memo_still_memoizes_safe_arguments():
    calls = []

    @request_memo("test_nav")
    def fetch(code: str, days: int):
        calls.append((code, days))
        return f"{code}:{days}"

    with request_scope():
        assert fetch("12345", 365) == "12345:365"
        assert fetch("12345", 365) == "12345:365"
        assert fetch("67890", 365) == "67890:365"

    assert len(calls) == 2, f"expected one call per distinct key, got {calls}"


def test_request_memo_is_inert_outside_a_request():
    calls = []

    @request_memo("test_outside")
    def compute():
        calls.append(1)
        return 42

    assert compute() == 42
    assert compute() == 42
    assert len(calls) == 2, "no store outside a request; must not memoize globally"
