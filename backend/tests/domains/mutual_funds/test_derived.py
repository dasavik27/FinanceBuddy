"""Derived analytics cache layer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.mutual_funds import derived
from shared.cache import MarketCache
from shared.services.cache import DERIVED_CACHE


@pytest.fixture(autouse=True)
def _clear_caches():
    MarketCache.invalidate_all()
    DERIVED_CACHE.clear()
    yield
    MarketCache.invalidate_all()
    DERIVED_CACHE.clear()


def test_derived_fingerprints_and_cache_bypass(monkeypatch):
    assert derived._frame_fingerprint(None) == "none"
    assert derived._frame_fingerprint(pd.DataFrame()) == "empty"
    assert derived._series_fingerprint(None) == "none"
    assert derived._series_fingerprint(pd.Series(dtype=float)) == "empty"

    s = pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2))
    assert derived._series_fingerprint(s).startswith("2:")

    df_t = pd.DataFrame([{"Date": "2024-01-01", "Amount": -1000, "Fund": "F"}])
    df_h = pd.DataFrame([{"Fund": "F", "Market Value": 1200}])

    calls = {"n": 0}

    def fake_xirr(df_t_in, df_h_in):
        calls["n"] += 1
        return [{"fy": "FY24-25", "cumulative_xirr": 10.0}]

    monkeypatch.setattr("domains.mutual_funds.finance.compute_xirr_by_fy", fake_xirr)
    r1 = derived.cached_xirr_by_fy(df_t, df_h)
    r2 = derived.cached_xirr_by_fy(df_t, df_h)
    assert r1 == r2
    assert calls["n"] == 1

    # Unhashable frame -> bypass cache
    bad = pd.DataFrame({"x": [object()]})
    monkeypatch.setattr("domains.mutual_funds.finance.compute_xirr_by_fy", lambda *a: [{"fy": "direct"}])
    assert derived.cached_xirr_by_fy(bad, df_h) == [{"fy": "direct"}]

def test_cached_period_comparison_and_stats(monkeypatch):
    df_t = pd.DataFrame([{"Date": "2024-01-01", "Amount": -1000, "Fund": "F"}])
    df_h = pd.DataFrame([{"Fund": "F", "Market Value": 1200}])
    bench = pd.Series([100.0, 110.0], index=pd.date_range("2024-01-01", periods=2))

    payload = {"portfolio": [100, 110], "benchmark": [100, 105]}
    monkeypatch.setattr(
        "domains.mutual_funds.derived.compute_period_comparison",
        lambda *a, **k: payload,
    )
    out = derived.cached_period_comparison(df_t, df_h, 1200.0, bench, 365)
    assert out == payload
    stats = derived.derived_cache_stats()
    assert isinstance(stats, dict)

def test_derived_fingerprint_failures_and_direct_compute(monkeypatch):
    bad_series = pd.Series([1.0, 2.0], index=["a", "b"])
    assert derived._series_fingerprint(bad_series) is None

    real_hash = pd.util.hash_pandas_object

    def flaky(df, **kwargs):
        if "unhashable" in df.columns:
            raise RuntimeError("bad")
        return real_hash(df, **kwargs)

    monkeypatch.setattr(pd.util, "hash_pandas_object", flaky)
    bad = pd.DataFrame({"Date": [pd.Timestamp("2024-01-01")], "unhashable": [object()]})
    df_h = pd.DataFrame([{"Fund": "F", "Market Value": 1200}])
    assert derived._frame_fingerprint(bad) is None
    monkeypatch.setattr("domains.mutual_funds.finance.compute_xirr_by_fy", lambda *a: [{"fy": "direct"}])
    assert derived.cached_xirr_by_fy(bad, df_h) == [{"fy": "direct"}]

    df_t = pd.DataFrame([{"Date": "2024-01-01", "Amount": -1000, "Fund": "F"}])
    bench = pd.Series([100.0], index=pd.date_range("2024-01-01", periods=1))
    out = derived.cached_period_comparison(df_t, df_h, 1200.0, bench, 365)
    assert isinstance(out, dict)

