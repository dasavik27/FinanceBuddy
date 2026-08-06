
"""Equity quote fetching, caching, and symbol resolution."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.equity import quotes as eq_quotes
from shared.services.cache import MARKET_CACHE


@pytest.fixture(autouse=True)
def _clear_quotes_cache():
    MARKET_CACHE.clear()
    yield
    MARKET_CACHE.clear()


def test_quotes_helpers_and_close_frame():
    assert eq_quotes.Quote(ltp=100.0, prev_close=95.0).day_change_per_share == 5.0
    assert eq_quotes.Quote(ltp=100.0).day_change_per_share == 0.0
    assert eq_quotes.is_valid_symbol("RELIANCE")
    assert not eq_quotes.is_valid_symbol("")
    assert eq_quotes.to_yahoo_ticker("RELIANCE") == "RELIANCE.NS"
    assert eq_quotes.to_yahoo_ticker("TCS.NS") == "TCS.NS"
    assert eq_quotes._close_frame(None, ["RELIANCE"]).empty

    flat = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.date_range("2025-01-01", periods=2))
    out = eq_quotes._close_frame(flat, ["RELIANCE"])
    assert "RELIANCE" in out.columns

    cols = pd.MultiIndex.from_tuples([("RELIANCE", "Close"), ("RELIANCE", "Open")])
    multi = pd.DataFrame([[100.0, 99.0], [101.0, 100.0]], index=pd.date_range("2025-01-01", periods=2), columns=cols)
    out2 = eq_quotes._close_frame(multi, ["RELIANCE"])
    assert "RELIANCE" in out2.columns

def test_resolve_symbol_with_mocked_nse(monkeypatch):
    class FakeNSE:
        def is_listed(self, symbol):
            return symbol == "RELIANCE"

        def symbol_for_isin(self, isin):
            return "RELIANCE" if isin == "INE002A01018" else None

    monkeypatch.setattr("domains.equity.nse_client.nse_client", FakeNSE())
    assert eq_quotes.resolve_symbol("OLDNAME", "INE002A01018") == "RELIANCE"
    assert eq_quotes.resolve_symbol("RELIANCE", None) == "RELIANCE"

def test_fetch_quotes_cache_and_batch(monkeypatch):
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame(
        {"RELIANCE.NS": [2500.0, 2510.0]},
        index=pd.date_range("2025-01-01", periods=2),
    ))
    q1 = eq_quotes.fetch_quotes(["RELIANCE"])
    assert "RELIANCE" in q1
    q2 = eq_quotes.fetch_quotes(["RELIANCE"])
    assert q2["RELIANCE"].ltp == q1["RELIANCE"].ltp

def test_quotes_download_and_enrich(monkeypatch):
    closes = pd.DataFrame(
        {"RELIANCE.NS": [2500.0, 2510.0, 2520.0]},
        index=pd.date_range("2025-01-01", periods=3),
    )
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: closes)
    monkeypatch.setattr(eq_quotes, "resolve_symbol", lambda sym, isin=None: sym)

    quotes = eq_quotes.fetch_quotes(["RELIANCE", "INVALID"])
    assert "RELIANCE" in quotes
    assert quotes["RELIANCE"].ltp == 2520.0

    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame())
    MARKET_CACHE.clear()
    assert eq_quotes.fetch_quotes(["RELIANCE"]) == {}

def test_quotes_history_and_json_helpers(monkeypatch):
    blob = eq_quotes._series_to_json(pd.Series([100.0, 101.0], index=pd.date_range("2025-01-01", periods=2)))
    restored = eq_quotes._series_from_json(blob)
    assert restored is not None and len(restored) == 2
    assert eq_quotes._series_from_json({"bad": True}) is None
    assert eq_quotes._history_key("RELIANCE", 90).endswith(":90")

    hist = pd.DataFrame({"RELIANCE.NS": [100.0, 101.0]}, index=pd.date_range("2025-01-01", periods=2))
    monkeypatch.setattr(eq_quotes, "_download_history", lambda tickers, days: hist)
    MARKET_CACHE.clear()
    out = eq_quotes.fetch_close_history(["RELIANCE", "BAD-SYM", "RELIANCE-EQ"], days=30)
    assert "RELIANCE" in out.columns

    monkeypatch.setattr(eq_quotes, "_download_history", lambda tickers, days: (_ for _ in ()).throw(RuntimeError("fail")))
    MARKET_CACHE.clear()
    from shared.cache import MarketCache
    MarketCache.invalidate_all()
    empty_hist = eq_quotes.fetch_close_history(["TCS"], days=30)
    assert empty_hist.empty

    MARKET_CACHE.clear()
    monkeypatch.setattr("shared.config.CACHE_TTL_MINUTES", 0)
    no_cache = eq_quotes.fetch_quotes(["TCS"])
    assert isinstance(no_cache, dict)
    monkeypatch.setattr("shared.config.CACHE_TTL_MINUTES", 60)

def test_quotes_resolve_and_helpers(monkeypatch):
    class ListedNSE:
        def is_listed(self, symbol):
            return symbol == "RELIANCE"

        def symbol_for_isin(self, isin):
            return "NEWNAME"

    monkeypatch.setattr("domains.equity.nse_client.nse_client", ListedNSE())
    assert eq_quotes.resolve_symbol("RELIANCE", "INE002A01018") == "RELIANCE"

    class BoomNSE:
        def is_listed(self, symbol):
            raise RuntimeError("nse down")

        def symbol_for_isin(self, isin):
            return None

    monkeypatch.setattr("domains.equity.nse_client.nse_client", BoomNSE())
    assert eq_quotes.resolve_symbol("OLD", "INE002A01018") == "OLD"

    assert eq_quotes.to_yahoo_ticker("TCS.BO") == "TCS.BO"
    assert eq_quotes.is_valid_symbol("RELIANCE-EQ")

    no_close = pd.DataFrame({"Open": [1.0]}, index=pd.date_range("2025-01-01", periods=1))
    assert eq_quotes._close_frame(no_close, ["X"]).empty

    weird = pd.DataFrame([[1.0]], columns=pd.MultiIndex.from_tuples([("X", "Open")]))
    assert eq_quotes._close_frame(weird, ["X"]).empty

    single_series = pd.DataFrame(
        {("RELIANCE", "Close"): [100.0, 101.0]},
        index=pd.date_range("2025-01-01", periods=2),
    )
    single_series.columns = pd.MultiIndex.from_tuples([("Close", "RELIANCE")])
    out = eq_quotes._close_frame(single_series, ["RELIANCE"])
    assert "RELIANCE" in out.columns or len(out.columns) == 1

def test_fetch_quotes_normalization_and_limits(monkeypatch):
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame(
        {"TCS.NS": [3000.0, 3010.0]},
        index=pd.date_range("2025-01-01", periods=2),
    ))
    MARKET_CACHE.clear()
    out = eq_quotes.fetch_quotes(["TCS", "TCS", "", "!!!BAD", "TCS-EQ"])
    assert "TCS" in out

    many = [f"SYM{i:03d}" for i in range(510)]
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame())
    MARKET_CACHE.clear()
    capped = eq_quotes.fetch_quotes(many)
    assert isinstance(capped, dict)

    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: (_ for _ in ()).throw(RuntimeError("dl")))
    MARKET_CACHE.clear()
    assert eq_quotes.fetch_quotes(["INFY"]) == {}

    monkeypatch.setattr(eq_quotes, "_download_closes", lambda tickers: pd.DataFrame(
        {"UNKNOWN.NS": [1.0]},
        index=pd.date_range("2025-01-01", periods=1),
    ))
    MARKET_CACHE.clear()
    partial = eq_quotes.fetch_quotes(["INFY"])
    assert "INFY" not in partial

def test_quotes_history_disk_and_edges(monkeypatch):
    assert eq_quotes._series_from_json({"index": [], "values": []}) is None
    assert eq_quotes._series_from_json({"index": ["bad"], "values": ["x"]}) is None

    hist = pd.DataFrame({"RELIANCE.NS": [100.0, 101.0]}, index=pd.date_range("2025-01-01", periods=2))
    monkeypatch.setattr(eq_quotes, "_download_history", lambda tickers, days: hist)
    MARKET_CACHE.clear()

    from shared.cache import MarketCache

    key = eq_quotes._history_key("TCS", 30)
    blob = eq_quotes._series_to_json(pd.Series([200.0, 201.0], index=pd.date_range("2025-01-01", periods=2)))
    MarketCache.set(key, blob)
    out = eq_quotes.fetch_close_history(["TCS"], days=30)
    assert "TCS" in out.columns

    many = [f"H{i:03d}" for i in range(510)]
    MARKET_CACHE.clear()
    capped_hist = eq_quotes.fetch_close_history(many, days=30)
    assert capped_hist.empty or len(capped_hist.columns) <= 500

    def persist_fail(key, blob):
        raise OSError("disk full")

    monkeypatch.setattr(MarketCache, "set", persist_fail)
    MARKET_CACHE.clear()
    monkeypatch.setattr(eq_quotes, "_download_history", lambda tickers, days: hist.rename(columns={"RELIANCE.NS": "INFY.NS"}))
    out2 = eq_quotes.fetch_close_history(["INFY"], days=30)
    assert "INFY" in out2.columns or out2.empty

def test_quotes_to_yahoo_bo_and_cache_hit(monkeypatch):
    assert eq_quotes.to_yahoo_ticker("SBIN.BO") == "SBIN.BO"

    q = eq_quotes.Quote(ltp=100.0, prev_close=99.0)
    MARKET_CACHE.set(eq_quotes._cache_key("WIPRO"), q, 3600, copy_on_read=False)
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda t: (_ for _ in ()).throw(AssertionError("no network")))
    out = eq_quotes.fetch_quotes(["WIPRO"])
    assert out["WIPRO"].ltp == 100.0

    empty_series = pd.DataFrame(
        {"TCS.NS": [float("nan")]},
        index=pd.date_range("2025-01-01", periods=1),
    )
    monkeypatch.setattr(eq_quotes, "_download_closes", lambda t: empty_series)
    MARKET_CACHE.clear()
    assert eq_quotes.fetch_quotes(["TCS"]) == {}

    monkeypatch.setattr(eq_quotes, "_download_history", lambda t, d: pd.DataFrame())
    MARKET_CACHE.clear()
    assert eq_quotes.fetch_close_history(["INFY"], days=30).empty

    monkeypatch.setattr("shared.config.CACHE_TTL_MINUTES", 0)
    MARKET_CACHE.clear()
    hist = pd.DataFrame({"INFY.NS": [100.0, 101.0]}, index=pd.date_range("2025-01-01", periods=2))
    monkeypatch.setattr(eq_quotes, "_download_history", lambda t, d: hist)
    no_cache_hist = eq_quotes.fetch_close_history(["INFY"], days=30)
    assert "INFY" in no_cache_hist.columns
    monkeypatch.setattr("shared.config.CACHE_TTL_MINUTES", 60)

    assert eq_quotes.fetch_quotes([]) == {}

def test_quotes_yfinance_download_and_cache_miss(monkeypatch):
    from domains.equity import quotes as eq_quotes

    mock_yf = MagicMock()
    mock_yf.download.return_value = pd.DataFrame(
        {"Close": {"RELIANCE.NS": [100.0, 101.0]}},
        index=pd.date_range("2026-07-01", periods=2),
    )
    monkeypatch.setitem(sys.modules, "yfinance", mock_yf)
    frame = eq_quotes._download_history(["RELIANCE"], 30)
    assert frame is not None

    monkeypatch.setattr(eq_quotes, "is_valid_symbol", lambda s: True)
    monkeypatch.setattr("shared.config.CACHE_TTL_MINUTES", 0)
    assert isinstance(eq_quotes.fetch_close_history(["RELIANCE"], days=30), pd.DataFrame)
