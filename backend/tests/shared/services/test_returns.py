"""Trailing returns computation."""

import logging

import numpy as np
import pandas as pd
import pytest

from shared.services.returns import PERIOD_LABELS, compute_trailing_returns


def test_trailing_returns_empty():
    assert compute_trailing_returns(None) == {p: None for p in PERIOD_LABELS}
    assert compute_trailing_returns(pd.Series(dtype=float)) == {p: None for p in PERIOD_LABELS}

def test_trailing_returns_insufficient_history():
    idx = pd.date_range("2025-05-01", periods=45, freq="D")
    nav = pd.Series([100.0 + i for i in range(45)], index=idx)
    result = compute_trailing_returns(nav)
    assert result["1Y"] is None
    assert result["3Y"] is None
    assert result["1M"] is not None

def test_trailing_returns_sanity_warning(caplog):
    # Flat NAV over long history triggers 3Y/5Y proximity warning
    idx = pd.date_range("2018-01-01", periods=3000, freq="D")
    nav = pd.Series([100.0] * len(idx), index=idx)

    with caplog.at_level(logging.WARNING):
        compute_trailing_returns(nav)

    assert any("TRAILING RETURNS WARN" in r.message for r in caplog.records)

def test_trailing_returns_simple_and_cagr():
    idx = pd.date_range("2020-01-01", periods=2000, freq="D")
    nav = pd.Series([100.0 * (1.0003 ** i) for i in range(len(idx))], index=idx)
    result = compute_trailing_returns(nav)

    assert result["1M"] is not None
    assert result["3M"] is not None
    assert result["1Y"] is not None
    assert result["3Y"] is not None
    assert result["5Y"] is not None

def test_trailing_returns_zero_start_nav():
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    nav = pd.Series([0.0] * 200 + [100.0] * 200, index=idx)
    result = compute_trailing_returns(nav)
    assert result["1Y"] is None

def test_trailing_returns_all_nan_after_dropna():
    idx = pd.DatetimeIndex([pd.Timestamp("2024-01-01")])
    s = pd.Series([np.nan], index=idx)
    out = compute_trailing_returns(s)
    assert all(v is None for v in out.values())

