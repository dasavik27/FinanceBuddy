"""
test_market_indices_full_coverage.py

Full unit test coverage for shared.services.market_indices:
- Cache invalidation
- Live market summary fetching & fallbacks
- Slicing and historical benchmark splicing logic
- Benchmark fetching for Yahoo tickers, MF schemes, and synthetic indices
- Hybrid 50/50 benchmark construction and edge cases
- Benchmark trailing returns computation
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest

from shared.services import market_indices


def test_clear_benchmark_cache():
    market_indices.clear_benchmark_cache()


def test_fetch_live_market_summary(monkeypatch):
    mock_fast_info = MagicMock()
    mock_fast_info.last_price = 24500.50
    mock_fast_info.previous_close = 24350.00

    mock_ticker = MagicMock()
    mock_ticker.fast_info = mock_fast_info

    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker

    monkeypatch.setattr(market_indices, "yf", mock_yf, raising=False)
    monkeypatch.setitem(sys.modules, "yfinance", mock_yf)

    res = market_indices.fetch_live_market_summary()
    assert "nifty" in res
    assert res["nifty"]["price"] == 24500.50
    assert res["nifty"]["is_live"] is True


def test_slice_trailing_days():
    dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    s = pd.Series(range(len(dates)), index=dates)

    sliced = market_indices._slice_trailing_days(s, 30)
    assert len(sliced) <= 35
    assert len(sliced) >= 25

    full = market_indices._slice_trailing_days(s, 9999)
    assert len(full) == len(s)


def test_benchmark_uses_price_index_blend():
    assert market_indices.benchmark_uses_price_index_blend("120716", 1500) is True
    assert market_indices.benchmark_uses_price_index_blend("120716", 200) is False
    assert market_indices.benchmark_uses_price_index_blend("^NSEI", 1500) is False


def test_splice_benchmark_series():
    mf_dates = pd.date_range("2020-01-01", "2024-01-01", freq="ME")
    mf_s = pd.Series(np.linspace(10, 20, len(mf_dates)), index=mf_dates)

    yf_dates = pd.date_range("2015-01-01", "2024-01-01", freq="ME")
    yf_s = pd.Series(np.linspace(1000, 2000, len(yf_dates)), index=yf_dates)

    spliced = market_indices._splice_benchmark_series(mf_s, yf_s)
    assert not spliced.empty
    assert spliced.index.min() == yf_dates.min()
    assert spliced.index.max() == mf_dates.max()

    assert len(market_indices._splice_benchmark_series(pd.Series(dtype=float), yf_s)) == len(yf_s)
    assert len(market_indices._splice_benchmark_series(mf_s, pd.Series(dtype=float))) == len(mf_s)


def test_fetch_yahoo_series(monkeypatch):
    mock_yf = MagicMock()
    monkeypatch.setitem(sys.modules, "yfinance", mock_yf)

    dates = pd.date_range("2024-01-01", "2024-06-01", freq="D")
    df_good = pd.DataFrame({"Close": np.linspace(100, 150, len(dates))}, index=dates)
    mock_yf.download.return_value = df_good

    s = market_indices._fetch_yahoo_series("^NSEI", 90)
    assert not s.empty
    assert len(s) <= 95

    # Empty DF return
    mock_yf.download.return_value = pd.DataFrame()
    s_empty = market_indices._fetch_yahoo_series("^NSEI", 90)
    assert s_empty.empty

    # Error handling
    mock_yf.download.side_effect = RuntimeError("Network error")
    s_err = market_indices._fetch_yahoo_series("^NSEI", 90)
    assert s_err.empty


def test_fetch_mf_nav_series(monkeypatch):
    mock_prov = MagicMock()
    dates = pd.date_range("2024-01-01", "2024-06-01", freq="D")
    mock_prov.fetch_nav_series.return_value = pd.Series(range(len(dates)), index=dates)
    monkeypatch.setattr(market_indices, "get_provider", lambda: mock_prov)

    s = market_indices._fetch_mf_nav_series("120716", 90)
    assert not s.empty

    mock_prov.fetch_nav_series.side_effect = RuntimeError("DB error")
    s_err = market_indices._fetch_mf_nav_series("120716", 90)
    assert s_err.empty


def test_build_hybrid_benchmark(monkeypatch):
    dates = pd.date_range("2024-01-01", "2024-06-01", freq="D")
    s_eq = pd.Series(np.linspace(100, 200, len(dates)), index=dates)
    s_debt = pd.Series(np.linspace(1000, 1050, len(dates)), index=dates)

    def mock_fetch(ticker, period):
        if "^NSEI" in ticker:
            return s_eq
        if "LIQUIDCASE" in ticker:
            return s_debt
        return pd.Series(dtype=float)

    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", mock_fetch)

    hybrid = market_indices._build_hybrid_benchmark(90)
    assert not hybrid.empty
    assert hybrid.iloc[0] == pytest.approx(100.0)

    # Empty cases
    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", lambda t, p: pd.Series(dtype=float))
    assert market_indices._build_hybrid_benchmark(90).empty

    # Only equity
    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", lambda t, p: s_eq if "^NSEI" in t else pd.Series(dtype=float))
    assert not market_indices._build_hybrid_benchmark(90).empty

    # Only debt
    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", lambda t, p: s_debt if "LIQUIDCASE" in t or "LICNETFGSC" in t else pd.Series(dtype=float))
    assert not market_indices._build_hybrid_benchmark(90).empty


def test_fetch_benchmark_series_caching(monkeypatch):
    dates = pd.date_range("2020-01-01", "2024-01-01", freq="D")
    sample_series = pd.Series(np.linspace(100, 200, len(dates)), index=dates)

    monkeypatch.setattr(market_indices, "_fetch_benchmark_series_uncached", lambda t, p: sample_series)

    # 1. Normal cached fetch
    res = market_indices.fetch_benchmark_series("^NSEI", period_days=90)
    assert not res.empty
    assert len(res) <= 100

    # 2. Refresh = True
    res_ref = market_indices.fetch_benchmark_series("^NSEI", period_days=90, refresh=True)
    assert not res_ref.empty

    # 3. Fallback path when full is empty
    def mock_uncached(t, p):
        if p >= 9000:
            return pd.Series(dtype=float)
        return sample_series

    monkeypatch.setattr(market_indices, "_fetch_benchmark_series_uncached", mock_uncached)
    res_fall = market_indices.fetch_benchmark_series("^SHORT_ONLY", period_days=90)
    assert not res_fall.empty



def test_fetch_benchmark_series_uncached_branches(monkeypatch):
    dates = pd.date_range("2024-01-01", "2024-06-01", freq="D")
    sample_series = pd.Series(range(len(dates)), index=dates)

    # 1. HYBRID_50_50
    monkeypatch.setattr(market_indices, "_build_hybrid_benchmark", lambda p: sample_series)
    assert not market_indices._fetch_benchmark_series_uncached("HYBRID_50_50", 90).empty

    # 2. Index alias (NIFTY 50 -> ^NSEI)
    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", lambda t, p: sample_series if t == "^NSEI" else pd.Series(dtype=float))
    assert not market_indices._fetch_benchmark_series_uncached("NIFTY 50", 90).empty

    # 3. ISIN
    from shared.services import market_data
    monkeypatch.setattr(market_data, "fetch_nav_series_by_isin", lambda isin, p: sample_series)
    assert not market_indices._fetch_benchmark_series_uncached("INF879O01019", 90).empty

    # 4. Scheme Code
    monkeypatch.setattr(market_data, "fetch_nav_series_by_code", lambda code, p: sample_series)
    assert not market_indices._fetch_benchmark_series_uncached("122639", 90).empty

    # 5. BSE Fallback
    def mock_yahoo(t, p):
        if t == "^CNXSC":
            return pd.Series(dtype=float)
        if t == "BSE-SMLCAP.BO":
            return sample_series
        return pd.Series(dtype=float)

    monkeypatch.setattr(market_indices, "_fetch_yahoo_series", mock_yahoo)
    res_bse = market_indices._fetch_benchmark_series_uncached("^CNXSC", 90)
    assert not res_bse.empty


def test_get_benchmark_trailing_returns(monkeypatch):
    dates = pd.date_range("2020-01-01", "2024-01-01", freq="D")
    sample_series = pd.Series(np.linspace(100, 200, len(dates)), index=dates)

    monkeypatch.setattr(market_indices, "fetch_benchmark_series", lambda t, period_days: sample_series)
    ret = market_indices.get_benchmark_trailing_returns("^NSEI")
    assert ret is not None
    assert "1Y" in ret

    # Empty series
    monkeypatch.setattr(market_indices, "fetch_benchmark_series", lambda t, period_days: pd.Series(dtype=float))
    ret_empty = market_indices.get_benchmark_trailing_returns("^NSEI")
    assert ret_empty["1Y"] is None
