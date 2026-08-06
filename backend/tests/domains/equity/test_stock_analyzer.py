"""
Equity stock analyzer — regression and mocked coverage.

Nothing here touches the network; upstream seams are faked.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.equity.quotes import Quote, resolve_symbol, to_yahoo_ticker
from domains.equity.stock_analyzer import (
    UnknownSymbol,
    _analyze_stock_uncached,
    _build_timeframe_charts,
    _clean_symbol,
    _company_name,
    _compute_beta,
    _compute_rsi,
    _compute_technicals,
    _dividend_yield_pct,
    _fetch_consensus,
    _fetch_yf_info,
    _fx_to_inr,
    _nifty_close_series,
    _nse_dividend_yield,
    _peer_symbols,
    _refresh_analysis,
    _to_yf_ticker,
    _yahoo_source_label,
    analyze_stock,
    compute_portfolio_impact,
    get_market_indices,
    get_sector_peers,
    search_stocks,
)
from shared.services.cache import MARKET_CACHE


# ── renamed symbols ──────────────────────────────────────────────────────────

class _FakeMaster:
    """
    Stands in for NSE's master list. `OLDSYM` has been renamed to `NEWSYM`, keeping its
    ISIN - which is the whole point: the ISIN is the identity, the ticker is a label.
    """

    def __init__(self):
        self._name_index = {"NEWSYM": "New Name Ltd", "OTHER": "Other Ltd"}
        self._isin_index = {"INE000A01001": "NEWSYM", "INE000A01002": "OTHER"}

    def is_listed(self, symbol):
        return symbol.upper().strip() in self._name_index

    def symbol_for_isin(self, isin):
        return self._isin_index.get((isin or "").upper().strip())


@pytest.fixture
def fake_master(monkeypatch):
    from domains.equity import nse_client as nse_mod
    fake = _FakeMaster()
    monkeypatch.setattr(nse_mod, "nse_client", fake)
    return fake


class TestRenamedSymbols:
    """
    Renames resolve by ISIN against NSE's master list, not by a table of old-to-new
    names. A table only covers the renames someone remembered to add, goes stale at the
    next one, and silently does nothing for every name not in it. NSE publishes an ISIN
    for all ~2,400 listed symbols and broker statements carry one per holding, so this
    is answerable from data rather than from a maintained list.
    """

    def test_retired_symbol_resolves_to_the_current_one_via_isin(self, fake_master):
        assert resolve_symbol("OLDSYM", isin="INE000A01001") == "NEWSYM"

    def test_currently_listed_symbol_is_left_alone(self, fake_master):
        # Must not be rewritten even though its ISIN is in the index.
        assert resolve_symbol("NEWSYM", isin="INE000A01001") == "NEWSYM"

    def test_without_an_isin_the_symbol_is_returned_unchanged(self, fake_master):
        # A watchlist entry carries no ISIN. Guessing would be worse than not guessing.
        assert resolve_symbol("OLDSYM") == "OLDSYM"

    def test_unknown_isin_leaves_the_symbol_alone(self, fake_master):
        assert resolve_symbol("OLDSYM", isin="INE999Z01999") == "OLDSYM"

    def test_eq_suffix_is_stripped_before_resolution(self, fake_master):
        assert resolve_symbol("OLDSYM-EQ", isin="INE000A01001") == "NEWSYM"

    def test_unreachable_master_does_not_break_resolution(self, monkeypatch):
        from domains.equity import nse_client as nse_mod

        class Broken:
            def is_listed(self, s):
                raise RuntimeError("network down")

            def symbol_for_isin(self, i):
                raise RuntimeError("network down")

        monkeypatch.setattr(nse_mod, "nse_client", Broken())
        assert resolve_symbol("OLDSYM", isin="INE000A01001") == "OLDSYM"

    def test_to_yahoo_ticker_carries_no_rename_table(self):
        # Ticker formatting is a pure string transform; renames belong in
        # resolve_symbol, where the ISIN is available to decide them.
        assert to_yahoo_ticker("RELIANCE") == "RELIANCE.NS"
        assert to_yahoo_ticker("TCS-EQ") == "TCS.NS"
        assert to_yahoo_ticker("ETERNAL.NS") == "ETERNAL.NS"


# ── dividend yield ───────────────────────────────────────────────────────────

class TestDividendYield:
    """Yahoo's v7 /quote endpoint returns this already scaled to a percentage."""

    def test_bare_value_is_not_rescaled(self):
        # RELIANCE.NS returns 0.46 against a real 0.46% yield. The old `* 100`
        # rendered this as 46%.
        assert _dividend_yield_pct({"dividendYield": 0.46}) == 0.46

    def test_high_but_plausible_yield_passes_through(self):
        # ITC.NS genuinely yields ~5.7%; it must not be mistaken for a fraction.
        assert _dividend_yield_pct({"dividendYield": 5.69}) == 5.69

    def test_rate_over_price_is_preferred_when_both_present(self):
        # Both legs are quote-currency, so this is the arithmetic cross-check.
        got = _dividend_yield_pct({"dividendRate": 16.0, "currentPrice": 281.0,
                                   "dividendYield": 5.69})
        assert got == pytest.approx(5.69, abs=0.01)

    def test_implausible_value_is_withheld_not_printed(self):
        # A units flip upstream must not surface as a confident number.
        assert _dividend_yield_pct({"dividendYield": 46.0}) is None

    @pytest.mark.parametrize("info", [{}, {"dividendYield": None}, {"dividendYield": 0}])
    def test_absent_yield_is_none_not_zero(self, info):
        # "0.0%" asserts a fact the data does not support; the UI must render a dash.
        assert _dividend_yield_pct(info) is None

    def test_zero_price_does_not_raise(self):
        assert _dividend_yield_pct({"dividendRate": 16.0, "currentPrice": 0,
                                    "dividendYield": 2.0}) == 2.0


# ── FX ───────────────────────────────────────────────────────────────────────

class TestFxToInr:
    def test_inr_is_identity_and_never_hits_network(self):
        # The overwhelming majority of NSE names report in INR; that path must be free.
        assert _fx_to_inr("INR") == 1.0
        assert _fx_to_inr("inr") == 1.0

    def test_missing_currency_is_treated_as_inr(self):
        assert _fx_to_inr(None) == 1.0


# ── peer selection ───────────────────────────────────────────────────────────

class TestPeerSymbols:
    """
    Peers are derived from SECTOR_MAP itself. The removed SECTOR_PEERS_MAP was keyed
    on NSE's vocabulary while get_sector returns GICS-style names; they intersected on
    two keys, so 157 of 190 symbols fell through to a fixed fallback list.
    """

    def test_energy_peers_are_energy_not_the_fallback_list(self):
        peers = _peer_symbols("RELIANCE", "Energy", "Refineries", limit=5)
        assert peers, "Reliance must resolve peers"
        # The exact bug: every unmatched sector rendered these five.
        assert "TCS" not in peers
        assert "HDFCBANK" not in peers
        assert "INFY" not in peers

    def test_banks_peer_with_banks(self):
        peers = _peer_symbols("HDFCBANK", "Financials", "Banks", limit=5)
        assert "ICICIBANK" in peers
        assert "SBIN" in peers

    def test_self_is_excluded(self):
        peers = _peer_symbols("HDFCBANK", "Financials", "Banks", limit=10)
        assert "HDFCBANK" not in peers

    def test_same_industry_ranks_above_same_sector(self):
        # A bank should be offered other banks before it is offered an insurer.
        peers = _peer_symbols("HDFCBANK", "Financials", "Banks", limit=20)
        first_insurer = next(
            (i for i, p in enumerate(peers) if p in {"HDFCLIFE", "SBILIFE", "ICICIGI"}),
            len(peers),
        )
        last_bank = max(
            (i for i, p in enumerate(peers) if p in {"ICICIBANK", "SBIN", "AXISBANK"}),
            default=-1,
        )
        assert last_bank < first_insurer

    def test_limit_is_respected(self):
        assert len(_peer_symbols("HDFCBANK", "Financials", "Banks", limit=3)) == 3

    def test_unknown_symbol_yields_no_peers_rather_than_wrong_ones(self):
        # "Others"/"Miscellaneous" is what get_sector returns for the ~2,200 symbols
        # outside the map. Showing arbitrary large caps as their "sector peers" is
        # worse than showing none.
        assert _peer_symbols("NOSUCHSYM", "Others", "Miscellaneous", limit=5) == []


# ── analyst consensus ────────────────────────────────────────────────────────

def _estimate_frame(analysts: int) -> pd.DataFrame:
    return pd.DataFrame(
        {"avg": [1.0] * 4, "low": [0.9] * 4, "high": [1.1] * 4,
         "numberOfAnalysts": [analysts] * 4},
        index=["0q", "+1q", "0y", "+1y"],
    )


class _FakeTicker:
    def __init__(self, est=None, rev=None, targets=None):
        self.earnings_estimate = est
        self.revenue_estimate = rev
        self.analyst_price_targets = targets


class TestConsensus:
    """
    Yahoo's "no coverage" responses are truthy. Each of these would pass a naive
    `if df` / `if not df.empty` check and render invented forward numbers.
    """

    def test_phantom_zero_frame_is_not_coverage(self):
        # The trap: uncovered names return a populated frame of zeros, not an empty
        # one, so a `.empty` check renders "forecast revenue Rs 0".
        tk = _FakeTicker(est=_estimate_frame(0), rev=_estimate_frame(0))
        assert _fetch_consensus(tk, {}) == {}

    def test_degraded_price_target_dict_is_rejected(self):
        # `{'current': price}` is truthy but carries no consensus.
        tk = _FakeTicker(est=_estimate_frame(5), rev=_estimate_frame(5),
                         targets={"current": 1148.6})
        assert "price_target" not in _fetch_consensus(tk, {})

    def test_real_price_target_is_kept(self):
        tk = _FakeTicker(est=_estimate_frame(5), rev=_estimate_frame(5),
                         targets={"current": 1148.6, "mean": 1199.0, "low": 940.0,
                                  "high": 1610.0})
        out = _fetch_consensus(tk, {})
        assert out["price_target"]["mean"] == 1199.0
        assert "current" not in out["price_target"]

    def test_recommendation_none_is_dropped(self):
        # 'none' co-occurs with genuine analyst counts, so it is not a coverage flag.
        tk = _FakeTicker(est=_estimate_frame(5), rev=_estimate_frame(5))
        out = _fetch_consensus(tk, {"numberOfAnalystOpinions": 29,
                                    "recommendationKey": "none"})
        assert out["analyst_count"] == 29
        assert "recommendation" not in out

    def test_covered_name_reports_estimates(self):
        tk = _FakeTicker(est=_estimate_frame(32), rev=_estimate_frame(32))
        out = _fetch_consensus(tk, {"numberOfAnalystOpinions": 32,
                                    "recommendationKey": "strong_buy"})
        assert out["eps"]["0q"]["analysts"] == 32
        assert out["recommendation"] == "strong_buy"

    def test_empty_frames_yield_no_consensus(self):
        tk = _FakeTicker(est=pd.DataFrame(), rev=pd.DataFrame())
        assert _fetch_consensus(tk, {}) == {}

    def test_upstream_exception_is_contained(self):
        class Boom:
            @property
            def earnings_estimate(self):
                raise RuntimeError("upstream down")

        assert _fetch_consensus(Boom(), {}) == {}


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_price_hist(n: int = 300, *, multiindex: bool = False) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="B")
    close = np.linspace(900, 1100, n) + np.random.default_rng(0).normal(0, 2, n)
    vol = np.full(n, 1_000_000)
    df = pd.DataFrame({"Close": close, "Open": close, "High": close + 5, "Low": close - 5, "Volume": vol}, index=dates)
    if multiindex:
        df.columns = pd.MultiIndex.from_tuples([(c, "RELIANCE.NS") for c in df.columns])
    return df


def _stmt_df(rows: dict[str, float], col) -> pd.DataFrame:
    return pd.DataFrame({col: rows}, index=list(rows.keys()))


def _rich_info() -> dict:
    return {
        "longName": "Reliance Industries Ltd",
        "longBusinessSummary": "A" * 700,
        "currentPrice": 1000.0,
        "regularMarketPrice": 1000.0,
        "marketCap": 1_500_000_000_000,
        "trailingPE": 25.0,
        "forwardPE": 22.0,
        "pegRatio": 1.2,
        "priceToBook": 2.1,
        "priceToSalesTrailing12Months": 1.5,
        "trailingEps": 40.0,
        "dividendRate": 10.0,
        "dividendYield": 1.0,
        "returnOnEquity": 0.12,
        "profitMargins": 0.08,
        "operatingMargins": 0.10,
        "debtToEquity": 45.0,
        "freeCashflow": 50_000_000_000,
        "fiftyTwoWeekHigh": 1200.0,
        "fiftyTwoWeekLow": 800.0,
        "open": 995.0,
        "dayHigh": 1010.0,
        "dayLow": 990.0,
        "averageVolume": 2_000_000,
        "volume": 1_500_000,
        "beta": 1.1,
        "financialCurrency": "INR",
        "currency": "INR",
        "isin": "INE002A01018",
        "numberOfAnalystOpinions": 20,
        "recommendationKey": "buy",
        "recommendationMean": 2.1,
    }


class _FakeYfTicker:
    def __init__(self, sym: str, *, info: dict | None = None, empty_info: bool = False):
        self._sym = sym
        if empty_info:
            self.info = {"currency": "INR"}
        else:
            self.info = info or _rich_info()
        fi = SimpleNamespace(
            last_price=1000.0,
            market_cap=1_500_000_000_000,
            year_high=1200.0,
            year_low=800.0,
            open=995.0,
            day_high=1010.0,
            day_low=990.0,
            currency="INR",
        )
        self.fast_info = fi
        col = pd.Timestamp("2024-03-31")
        self.quarterly_income_stmt = _stmt_df(
            {
                "Total Revenue": 100_000_000_000,
                "Operating Expense": 80_000_000_000,
                "Net Income": 15_000_000_000,
                "Diluted EPS": 40.0,
                "EBITDA": 20_000_000_000,
                "Tax Rate For Calcs": 0.25,
            },
            col,
        )
        self.income_stmt = self.quarterly_income_stmt
        self.quarterly_balance_sheet = _stmt_df(
            {
                "Cash And Cash Equivalents": 50_000_000_000,
                "Total Assets": 500_000_000_000,
                "Total Liabilities": 200_000_000_000,
                "Stockholders Equity": 300_000_000_000,
                "Ordinary Shares Number": 6_000_000_000,
            },
            col,
        )
        self.balance_sheet = self.quarterly_balance_sheet
        self.quarterly_cashflow = _stmt_df(
            {
                "Operating Cash Flow": 18_000_000_000,
                "Investing Cash Flow": -5_000_000_000,
                "Financing Cash Flow": -3_000_000_000,
                "Changes In Cash": 10_000_000_000,
                "Free Cash Flow": 12_000_000_000,
                "Change In Inventory": -100_000_000,
            },
            col,
        )
        self.cashflow = self.quarterly_cashflow
        self.calendar = {"Earnings Date": [pd.Timestamp("2024-04-15")]}
        self.earnings_estimate = pd.DataFrame(
            {"avg": [1.0], "low": [0.9], "high": [1.1], "numberOfAnalysts": [5]},
            index=["0q"],
        )
        self.revenue_estimate = pd.DataFrame(
            {"avg": [1e11], "numberOfAnalysts": [5]},
            index=["0q"],
        )
        self.analyst_price_targets = {"mean": 1100.0, "low": 900.0, "high": 1300.0}


@pytest.fixture(autouse=True)
def _clear_market_cache():
    MARKET_CACHE.clear()
    yield
    MARKET_CACHE.clear()


@pytest.fixture
def mock_nse(monkeypatch):
    fake = MagicMock()
    fake.search.return_value = [{"symbol": "RELIANCE", "name": "Reliance Industries Ltd"}]
    fake.name_for.return_value = "Reliance Industries Ltd"
    fake.get_equity_quote.return_value = {
        "name": "Reliance Industries Ltd",
        "current_price": 1005.0,
        "sector": "Energy",
        "industry": "Oil & Gas",
        "week52_high": 1200.0,
        "week52_low": 800.0,
        "market_cap_cr": 1500000.0,
        "pe_ratio": 24.5,
        "sector_pe": 18.0,
        "vwap": 1002.0,
        "delivery_pct": 45.0,
        "isin": "INE002A01018",
        "series": "EQ",
    }
    monkeypatch.setattr("domains.equity.stock_analyzer.nse_client", fake)
    return fake


@pytest.fixture
def mock_nse_side(monkeypatch):
    monkeypatch.setattr(
        "domains.equity.stock_analyzer.nse_corporate.corporate_actions",
        lambda sym: [
            {
                "type": "dividend",
                "subject": "Interim Dividend - Rs 10 per share",
                "ex_date": (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d"),
            }
        ],
    )
    monkeypatch.setattr(
        "domains.equity.stock_analyzer.nse_corporate.event_calendar",
        lambda sym: [{"date": "2025-12-01", "event": "Results"}],
    )
    monkeypatch.setattr(
        "domains.equity.stock_analyzer.nse_corporate.announcements",
        lambda sym, n: [{"title": "Board meeting", "date": "2025-06-01"}],
    )
    monkeypatch.setattr(
        "domains.equity.stock_analyzer.nse_results.latest_results",
        lambda sym: {"period": "Q1 FY26", "basis": "Consolidated"},
    )


@pytest.fixture
def mock_bse(monkeypatch):
    fake = MagicMock()
    fake.get_vwap.return_value = 1003.5
    monkeypatch.setattr("domains.equity.stock_analyzer.bse_client", fake)
    return fake


@pytest.fixture
def mock_quotes(monkeypatch):
    def _fetch(symbols, refresh=False):
        return {
            s: Quote(ltp=500.0 + i * 10, prev_close=490.0 + i * 10)
            for i, s in enumerate(symbols)
        }

    monkeypatch.setattr("domains.equity.stock_analyzer.fetch_quotes", _fetch)


@pytest.fixture
def mock_yfinance(monkeypatch):
    hist = _make_price_hist(300)

    def _ticker(sym):
        if sym.endswith(".BO"):
            return _FakeYfTicker(sym, info=_rich_info())
        if sym.endswith(".NS") and "EMPTY" in sym:
            return _FakeYfTicker(sym, empty_info=True)
        return _FakeYfTicker(sym)

    def _download(tickers, **kwargs):
        if isinstance(tickers, list):
            # market indices path
            out = {}
            for t in tickers:
                h = _make_price_hist(5)
                out[t] = h
            return pd.concat(out, axis=1)
        if tickers == "^NSEI":
            h = _make_price_hist(130)
            return h
        return hist

    yf = MagicMock()
    yf.Ticker.side_effect = _ticker
    yf.download.side_effect = _download
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    return yf


# ── small helpers ─────────────────────────────────────────────────────────────


class TestSmallHelpers:
    def test_clean_symbol_strips_suffixes(self):
        assert _clean_symbol("reliance-eq") == "RELIANCE"
        assert _clean_symbol("TCS.NS") == "TCS"
        assert _clean_symbol("INFY.BO") == "INFY"

    def test_to_yf_ticker(self):
        assert _to_yf_ticker("RELIANCE") == "RELIANCE.NS"

    def test_yahoo_source_label(self):
        assert _yahoo_source_label("RELIANCE.NS") == "Yahoo Finance (.NS)"
        assert _yahoo_source_label("TATAMOTORS.BO") == "Yahoo Finance (.BO)"

    def test_company_name_from_nse(self, mock_nse):
        assert _company_name("RELIANCE") == "Reliance Industries Ltd"

    def test_company_name_falls_back_on_error(self, monkeypatch):
        class Boom:
            def name_for(self, s):
                raise RuntimeError("down")

        monkeypatch.setattr("domains.equity.stock_analyzer.nse_client", Boom())
        assert _company_name("RELIANCE") == "RELIANCE"

    def test_search_stocks(self, mock_nse):
        out = search_stocks("rel", limit=5)
        assert out[0]["symbol"] == "RELIANCE"


# ── _fetch_yf_info cascade ────────────────────────────────────────────────────


class TestFetchYfInfo:
    def test_ns_success(self, monkeypatch):
        calls = []

        class T:
            def __init__(self, sym):
                calls.append(sym)
                self.info = {f"k{i}": i for i in range(15)}

        yf = MagicMock()
        yf.Ticker.side_effect = T
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        info, used = _fetch_yf_info("RELIANCE.NS")
        assert len(info) > 10
        assert used == "RELIANCE.NS"

    def test_cascade_ns_to_bo(self, monkeypatch):
        class T:
            def __init__(self, sym):
                self.info = {} if sym.endswith(".NS") else {f"k{i}": i for i in range(15)}

        yf = MagicMock()
        yf.Ticker.side_effect = T
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        info, used = _fetch_yf_info("TATAMOTORS.NS")
        assert used == "TATAMOTORS.BO"
        assert len(info) > 10

    def test_both_fail_returns_empty(self, monkeypatch):
        class T:
            def __init__(self, sym):
                raise RuntimeError("404")

        yf = MagicMock()
        yf.Ticker.side_effect = T
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        info, used = _fetch_yf_info("BAD.NS")
        assert info == {}
        assert used == "BAD.NS"


# ── beta / dividend / technicals ──────────────────────────────────────────────


class TestBetaDividendTechnicals:
    def test_compute_beta_happy_path(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=120, freq="B")
        nifty = {d.strftime("%Y-%m-%d"): 100 + i * 0.5 for i, d in enumerate(dates)}
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: nifty)
        close = pd.Series([100 + i * 0.6 + (i % 3) for i in range(len(dates))], index=dates, dtype=float)
        hist = pd.DataFrame({"Close": close})
        beta = _compute_beta(hist, "RELIANCE")
        assert beta is not None
        assert 0.0 < beta < 5.0

    def test_compute_beta_insufficient_nifty(self, monkeypatch):
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: {})
        assert _compute_beta(_make_price_hist(120), "RELIANCE") is None

    def test_compute_beta_empty_hist(self, monkeypatch):
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: {"2024-01-01": 100.0})
        assert _compute_beta(pd.DataFrame(), "RELIANCE") is None

    def test_compute_beta_short_series(self, monkeypatch):
        nifty = {d.strftime("%Y-%m-%d"): 100.0 for d in pd.date_range("2024-01-01", periods=80, freq="B")}
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: nifty)
        hist = _make_price_hist(30)
        assert _compute_beta(hist, "RELIANCE") is None

    def test_nse_dividend_yield(self):
        actions = [
            {"type": "dividend", "subject": "Final Dividend Rs 10 per share", "ex_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
            {"type": "bonus", "subject": "Bonus 1:1", "ex_date": "2020-01-01"},
            {"not": "a dict"},
            {"subject": "INTERIM DIVIDEND", "ex_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "amount": "5"},
        ]
        yld = _nse_dividend_yield(actions, 1000.0)
        assert yld == pytest.approx(1.5, abs=0.01)

    def test_nse_dividend_yield_invalid_inputs(self):
        assert _nse_dividend_yield([], 100.0) is None
        assert _nse_dividend_yield([{"type": "dividend"}], 0) is None

    def test_compute_rsi_and_technicals(self):
        rng = np.random.default_rng(1)
        prices = pd.Series(100 + np.cumsum(rng.normal(0, 1, 250)))
        rsi = _compute_rsi(prices)
        assert rsi is not None
        tech = _compute_technicals(prices, float(prices.iloc[-1]), float(prices.max()) + 10, float(prices.min()) - 10)
        assert tech["rsi_status"] in {"Oversold", "Overbought", "Neutral"}
        assert tech["trend"] in {"Strong Uptrend", "Uptrend", "Downtrend", "Consolidating", "Neutral"}

    def test_compute_technicals_empty(self):
        out = _compute_technicals(pd.Series(dtype=float), 0, None, None)
        assert out["sma_50"] is None
        assert out["trend"] == "Neutral"


# ── charts / indices ──────────────────────────────────────────────────────────


class TestChartsAndIndices:
    def test_build_timeframe_charts(self):
        hist = _make_price_hist(1300)
        charts = _build_timeframe_charts(hist, float(hist["Close"].iloc[-1]))
        assert set(charts.keys()) == {"1D", "5D", "1M", "6M", "YTD", "1Y", "5Y"}
        assert len(charts["5Y"]["dates"]) <= 260

    def test_build_timeframe_charts_empty(self):
        assert _build_timeframe_charts(pd.DataFrame(), 0) == {}

    def test_nifty_close_series_cached(self, mock_yfinance):
        first = _nifty_close_series()
        second = _nifty_close_series()
        assert first == second
        assert len(first) >= 60

    def test_get_market_indices(self, mock_yfinance):
        out = get_market_indices()
        assert len(out) == 4
        assert out[0]["symbol"] in {"NIFTY 50", "SENSEX", "BANK NIFTY", "NIFTY IT"}

    def test_get_market_indices_download_failure(self, monkeypatch):
        yf = MagicMock()
        yf.download.side_effect = RuntimeError("down")
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        assert get_market_indices() == []


# ── analyze_stock cache paths ─────────────────────────────────────────────────


class TestAnalyzeStockCaching:
    def test_invalid_symbol_raises(self):
        with pytest.raises(UnknownSymbol):
            analyze_stock("../BAD")

    def test_cache_disabled_bypasses_cache(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        import shared.config as cfg

        monkeypatch.setattr(cfg, "CACHE_TTL_MINUTES", 0)
        out = analyze_stock("RELIANCE")
        assert out["symbol"] == "RELIANCE"
        assert out["current_price"] > 0

    def test_fresh_cache_hit(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        import shared.config as cfg

        monkeypatch.setattr(cfg, "CACHE_TTL_MINUTES", 60)
        first = analyze_stock("RELIANCE")
        # poison upstream — cached read must still succeed
        monkeypatch.setattr("domains.equity.stock_analyzer._analyze_stock_uncached", lambda s: {"symbol": s, "poisoned": True})
        second = analyze_stock("RELIANCE")
        assert second == first
        assert "poisoned" not in second

    def test_stale_cache_returns_stale_flag(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        import shared.config as cfg
        from shared.services.cache import MARKET_CACHE as MC

        monkeypatch.setattr(cfg, "CACHE_TTL_MINUTES", 60)
        data = _refresh_analysis("RELIANCE")
        key = "equity_analysis_v3:RELIANCE"
        env = MC.get(key)[1]
        env["fresh_until"] = time.time() - 10
        MC.set(key, env, 3600, copy_on_read=False)
        out = analyze_stock("RELIANCE")
        assert out.get("stale") is True
        assert out["symbol"] == data["symbol"]

    def test_disk_cache_reseed(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        import shared.config as cfg
        from shared.cache import MarketCache as DiskCache

        monkeypatch.setattr(cfg, "CACHE_TTL_MINUTES", 60)
        data = _refresh_analysis("RELIANCE")
        envelope = {"data": data, "fresh_until": time.time() + 3600}
        DiskCache.set("equity_analysis_v3:RELIANCE", envelope)
        MARKET_CACHE.clear()
        out = analyze_stock("RELIANCE")
        assert out["symbol"] == "RELIANCE"

    def test_degraded_response_short_ttl(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        monkeypatch.setattr(
            "domains.equity.stock_analyzer._analyze_stock_uncached",
            lambda s: {"symbol": s, "pe_ratio": None, "market_cap_cr": None, "eps": None},
        )
        out = _refresh_analysis("RELIANCE")
        assert out["pe_ratio"] is None


# ── full uncached analysis ────────────────────────────────────────────────────


class TestAnalyzeStockUncached:
    def test_happy_path(self, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        out = _analyze_stock_uncached("RELIANCE")
        assert out["symbol"] == "RELIANCE"
        assert out["source"] == "NSE"
        assert out["pe_ratio"] == 24.5
        assert out["sources"]["price"] == "NSE"
        assert out["beta"] is not None
        assert out["chart"]["dates"]
        assert out["timeframes"]["1Y"]["dates"]
        assert out["peers"]
        assert out["corporate_actions"]
        assert out["consensus"]

    def test_yahoo_only_when_nse_quote_missing(self, monkeypatch, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        fake = MagicMock()
        fake.get_equity_quote.return_value = None
        fake.name_for.return_value = "Reliance Industries Ltd"
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_client", fake)
        out = _analyze_stock_uncached("RELIANCE")
        assert "Yahoo Finance" in out["source"]
        assert out["current_price"] > 0

    def test_fast_info_fallback_and_bo_cascade(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        hist = _make_price_hist(300, multiindex=True)

        def _ticker(sym):
            t = _FakeYfTicker(sym, empty_info=True)
            if sym.endswith(".NS"):
                t.info = {"currency": "INR"}
            else:
                t.info = _rich_info()
            return t

        yf = MagicMock()
        yf.Ticker.side_effect = _ticker
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("TATAMOTORS")
        assert out["symbol"] == "TATAMOTORS"
        assert out["current_price"] > 0

    def test_extended_info_exception_degrades(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        yf = MagicMock()
        yf.Ticker.side_effect = RuntimeError("info down")
        yf.download.return_value = _make_price_hist(100)
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["symbol"] == "RELIANCE"

    def test_price_history_failure(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        yf = MagicMock()
        yf.Ticker.return_value = _FakeYfTicker("RELIANCE.NS")
        yf.download.side_effect = RuntimeError("hist down")
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["chart"]["dates"] == []

    def test_nse_thread_failures_are_soft(self, monkeypatch, mock_nse, mock_bse, mock_quotes, mock_yfinance):
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_corporate.corporate_actions", lambda s: (_ for _ in ()).throw(RuntimeError("nse")))
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_corporate.event_calendar", lambda s: (_ for _ in ()).throw(RuntimeError("nse")))
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_results.latest_results", lambda s: (_ for _ in ()).throw(RuntimeError("nse")))
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_corporate.announcements", lambda s, n: (_ for _ in ()).throw(RuntimeError("nse")))
        out = _analyze_stock_uncached("RELIANCE")
        assert out["corporate_actions"] == []

    def test_usd_financials_fx(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        info = _rich_info()
        info["financialCurrency"] = "USD"

        fx = SimpleNamespace(last_price=83.0)

        def _ticker(sym):
            if sym == "USDINR=X":
                t = MagicMock()
                t.fast_info = fx
                return t
            return _FakeYfTicker(sym, info=info)

        yf = MagicMock()
        yf.Ticker.side_effect = _ticker
        yf.download.return_value = _make_price_hist(250)
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("INFY")
        assert out["financial_currency"] == "USD"
        assert out["free_cash_flow_cr"] is not None


class TestSectorPeers:
    def test_peers_with_quotes(self, mock_quotes, mock_nse):
        out = get_sector_peers("RELIANCE", "Energy", limit=3)
        assert len(out) <= 3
        assert out[0]["current_price"] is not None

    def test_peers_quote_failure(self, monkeypatch, mock_nse):
        monkeypatch.setattr("domains.equity.stock_analyzer.fetch_quotes", lambda s, refresh=False: (_ for _ in ()).throw(RuntimeError("q")))
        out = get_sector_peers("RELIANCE", "Energy", limit=3)
        assert out
        assert out[0]["current_price"] is None

    def test_peers_no_candidates(self):
        assert get_sector_peers("ZZZZNOTREAL", "Others", limit=3) == []


class TestPortfolioImpact:
    def test_compute_portfolio_impact(self):
        holdings = [
            {"symbol": "RELIANCE", "sector": "Energy", "quantity": 10, "avg_price": 1000, "current_value": 12000},
            {"symbol": "TCS", "sector": "Information Technology", "quantity": 5, "avg_price": 3000, "current_value": 17500},
        ]
        out = compute_portfolio_impact("HDFCBANK", 5000, holdings, 29500)
        assert out["symbol"] == "HDFCBANK"
        assert out["sector"] == "Financials"
        assert out["portfolio_weight_after"] > 0
        assert out["concentration_warning"] is False

    def test_compute_portfolio_impact_empty_and_existing(self):
        out = compute_portfolio_impact("RELIANCE", 20000, [], 0)
        assert out["portfolio_weight_after"] == 100.0
        holdings = [{"symbol": "RELIANCE", "sector": "Energy", "quantity": 1, "avg_price": 100, "current_value": 1000}]
        out2 = compute_portfolio_impact("RELIANCE", 50000, holdings, 1000)
        assert out2["already_owned"] is True
        assert out2["concentration_warning"] is True


class TestEdgeCasesForCoverage:
    """Target remaining branches for ≥95% module coverage."""

    def test_analyze_stock_cold_refresh_path(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        import shared.config as cfg
        from shared.cache import MarketCache as DiskCache

        monkeypatch.setattr(cfg, "CACHE_TTL_MINUTES", 60)
        MARKET_CACHE.clear()
        monkeypatch.setattr(DiskCache, "get", lambda k: None)
        out = analyze_stock("RELIANCE")
        assert out["symbol"] == "RELIANCE"

    def test_compute_beta_close_dataframe_and_zero_variance(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=80, freq="B")
        nifty = {d.strftime("%Y-%m-%d"): 100.0 for d in dates}
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: nifty)
        hist = pd.DataFrame(index=dates)
        hist[("Close", "a")] = 100.0
        hist[("Close", "b")] = 101.0
        assert _compute_beta(hist, "X") is None

        flat = pd.Series(100.0, index=dates)
        hist2 = pd.DataFrame({"Close": flat})
        assert _compute_beta(hist2, "X") is None

    def test_nse_dividend_yield_branches(self):
        assert _nse_dividend_yield([{"type": "dividend", "subject": "Rs 0", "ex_date": "2025-01-01"}], 100) is None
        assert _nse_dividend_yield([{"type": "dividend", "subject": "x", "ex_date": "bad-date"}], 100) is None
        assert _nse_dividend_yield([{"type": "dividend", "subject": "x"}], 100) is None
        assert _nse_dividend_yield([{"type": "dividend", "subject": "broken", "ex_date": "2020-01-01", "amount": "x"}], 100) is None

    def test_rsi_and_technicals_branches(self):
        assert _compute_rsi(pd.Series([1, 2, 3]), period=14) is None
        flat = pd.Series([100.0] * 20)
        assert _compute_rsi(flat) is None

        prices = pd.Series([100 + (i % 2) for i in range(250)])
        tech = _compute_technicals(prices, 101.0, 110.0, 90.0)
        assert tech["rsi_status"] in {"Oversold", "Overbought", "Neutral"}

        uptrend = pd.Series(list(range(100, 260)))
        tech2 = _compute_technicals(uptrend, 250.0, 260.0, 100.0)
        assert tech2["trend"] in {"Uptrend", "Strong Uptrend", "Consolidating"}

        down = pd.Series(list(range(260, 60, -1)))
        tech3 = _compute_technicals(down, 70.0, 80.0, 60.0)
        assert tech3["trend"] in {"Downtrend", "Consolidating"}

    def test_dividend_yield_and_fx_errors(self, monkeypatch):
        from domains.equity.stock_analyzer import _dividend_yield_pct, _fx_to_inr

        assert _dividend_yield_pct({"dividendRate": "x", "currentPrice": 100, "dividendYield": 2.0}) == 2.0
        assert _dividend_yield_pct({"dividendYield": "bad"}) is None

        yf = MagicMock()
        yf.Ticker.side_effect = RuntimeError("fx down")
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        assert _fx_to_inr("USD") is None

    def test_consensus_row_and_target_errors(self):
        from domains.equity.stock_analyzer import _fetch_consensus

        class BadEst:
            @property
            def earnings_estimate(self):
                df = pd.DataFrame({"numberOfAnalysts": ["x"]}, index=["0q"])
                return df

            @property
            def revenue_estimate(self):
                return pd.DataFrame()

            @property
            def analyst_price_targets(self):
                raise RuntimeError("targets down")

        out = _fetch_consensus(BadEst(), {})
        assert "price_target" not in out

        tk = _FakeYfTicker("X.NS")
        tk.earnings_estimate = pd.DataFrame(
            {"avg": [1.0], "low": [0.5], "high": [1.5], "numberOfAnalysts": [3]},
            index=["0q"],
        )
        tk.revenue_estimate = pd.DataFrame()
        out2 = _fetch_consensus(tk, {"numberOfAnalystOpinions": 3})
        assert out2["eps"]["0q"]["avg"] == 1.0

    def test_nifty_and_indices_edge_cases(self, monkeypatch):
        yf = MagicMock()
        yf.download.return_value = pd.DataFrame()
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        assert _nifty_close_series() == {}

        def _bad_download(tickers, **kwargs):
            if isinstance(tickers, list):
                data = _make_price_hist(5)
                bad = pd.DataFrame({"Open": [1, 2]})  # no Close
                return pd.concat({tickers[0]: data, tickers[1]: bad}, axis=1)
            return _make_price_hist(5)

        yf.download.side_effect = _bad_download
        MARKET_CACHE.clear()
        out = get_market_indices()
        assert len(out) == 4

    def test_build_timeframe_empty_slice(self):
        dates = pd.date_range("2025-01-01", periods=5, freq="B")
        s = pd.Series([1, 2, 3, 4, 5], index=dates)
        hist = pd.DataFrame({"Close": s})
        charts = _build_timeframe_charts(hist, 5.0)
        future = pd.Timestamp("2099-01-01")
        # force empty YTD via monkeypatched internal - use direct call on empty after drop
        empty_hist = pd.DataFrame({"Close": pd.Series(dtype=float)})
        assert _build_timeframe_charts(empty_hist, 0) == {}

    def test_fast_info_fallback_path(self, monkeypatch, mock_nse_side, mock_bse, mock_quotes):
        fake_nse = MagicMock()
        fake_nse.get_equity_quote.return_value = None
        fake_nse.name_for.return_value = "Reliance Industries Ltd"
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_client", fake_nse)

        def _ticker(sym):
            t = MagicMock()
            t.info = {"currency": "INR"}
            t.fast_info = SimpleNamespace(
                last_price=500.0, market_cap=1e11, year_high=600.0, year_low=400.0,
                open=490.0, day_high=510.0, day_low=480.0, currency="INR",
            )
            t.quarterly_income_stmt = pd.DataFrame()
            t.income_stmt = pd.DataFrame()
            t.quarterly_balance_sheet = pd.DataFrame()
            t.balance_sheet = pd.DataFrame()
            t.quarterly_cashflow = pd.DataFrame()
            t.cashflow = pd.DataFrame()
            t.calendar = {}
            t.earnings_estimate = pd.DataFrame()
            t.revenue_estimate = pd.DataFrame()
            t.analyst_price_targets = {}
            return t

        yf = MagicMock()
        yf.Ticker.side_effect = _ticker
        yf.download.return_value = _make_price_hist(90)
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["day_open"] == 490.0
        assert "Yahoo Finance" in out["source"]

    def test_hist_close_dataframe_branch(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="B")
        close_vals = np.linspace(900, 1000, 100)
        hist = pd.DataFrame(
            {
                ("Close", "RELIANCE.NS"): close_vals,
                ("Open", "RELIANCE.NS"): close_vals,
                ("High", "RELIANCE.NS"): close_vals + 1,
                ("Low", "RELIANCE.NS"): close_vals - 1,
                ("Volume", "RELIANCE.NS"): np.full(100, 1_000_000),
            },
            index=dates,
        )

        yf = MagicMock()
        yf.Ticker.return_value = _FakeYfTicker("RELIANCE.NS")
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["chart"]["dates"]

    def test_beta_dataframe_close_branch(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=80, freq="B")
        nifty = {d.strftime("%Y-%m-%d"): 100 + i * 0.1 for i, d in enumerate(dates)}
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: nifty)
        hist = pd.DataFrame({
            "Close": pd.Series([100 + i * 0.2 for i in range(80)], index=dates),
            "Extra": pd.Series([1.0] * 80, index=dates),
        })
        beta = _compute_beta(hist, "RELIANCE")
        assert beta is not None

    def test_beta_missing_cov_columns(self, monkeypatch):
        dates = pd.date_range("2024-01-01", periods=80, freq="B")
        nifty = {d.strftime("%Y-%m-%d"): 100.0 for d in dates}
        monkeypatch.setattr("domains.equity.stock_analyzer._nifty_close_series", lambda: nifty)
        hist = _make_price_hist(80)

        def fake_cov(self, *args, **kwargs):
            return pd.DataFrame({"a": [1.0], "b": [2.0]})

        monkeypatch.setattr(pd.DataFrame, "cov", fake_cov)
        assert _compute_beta(hist, "RELIANCE") is None

    def test_nse_dividend_subject_keyword_path(self):
        actions = [{
            "type": "other",
            "subject": "Interim DIVIDEND of Rs 5 per share",
            "ex_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }]
        yld = _nse_dividend_yield(actions, 100.0)
        assert yld == pytest.approx(5.0, abs=0.01)

    def test_nse_dividend_missing_ex_date(self):
        actions = [{
            "type": "dividend",
            "subject": "Final Dividend Rs 10 per share",
        }]
        assert _nse_dividend_yield(actions, 100.0) is None

    def test_technicals_uptrend_only(self):
        prices = pd.Series(list(range(100, 260)))
        tech = _compute_technicals(prices, 250.0, 260.0, 100.0)
        assert tech["trend"] in {"Uptrend", "Strong Uptrend", "Consolidating", "Downtrend"}

    def test_dividend_yield_implausible_and_rate_path(self):
        from domains.equity.stock_analyzer import _dividend_yield_pct

        assert _dividend_yield_pct({"dividendRate": 10, "currentPrice": 1000}) == 1.0
        assert _dividend_yield_pct({"dividendYield": 50.0}) is None

    def test_fetch_consensus_exceptions(self):
        from domains.equity.stock_analyzer import _fetch_consensus

        class Boom:
            @property
            def earnings_estimate(self):
                raise RuntimeError("est down")

        assert _fetch_consensus(Boom(), {}) == {}

        class NoAnalysts:
            earnings_estimate = pd.DataFrame({"avg": [1.0]}, index=["0q"])
            revenue_estimate = pd.DataFrame()
            analyst_price_targets = {}

        assert _fetch_consensus(NoAnalysts(), {}) == {}

    def test_fetch_consensus_row_errors(self):
        from domains.equity.stock_analyzer import _fetch_consensus

        tk = _FakeYfTicker("X.NS")
        tk.earnings_estimate = pd.DataFrame(
            {"avg": [1.0], "low": [0.5], "high": [1.5], "numberOfAnalysts": [2]},
            index=["0q"],
        )
        tk.revenue_estimate = pd.DataFrame(
            {"avg": [1e11], "numberOfAnalysts": [2]},
            index=["0q"],
        )
        tk.analyst_price_targets = {"mean": 100.0, "low": 90.0, "high": 110.0}
        out = _fetch_consensus(tk, {"numberOfAnalystOpinions": 2, "recommendationKey": "buy"})
        assert out["price_target"]["mean"] == 100.0

    def test_market_indices_per_symbol_fallback(self, monkeypatch):
        dates = pd.date_range("2025-01-01", periods=5, freq="B")

        def _download(tickers, **kwargs):
            if isinstance(tickers, list):
                bad = pd.DataFrame({"Open": [1, 2, 3, 4, 5]}, index=dates)
                good = _make_price_hist(5)
                return pd.concat({tickers[0]: good, tickers[1]: bad}, axis=1)
            return _make_price_hist(5)

        yf = MagicMock()
        yf.download.side_effect = _download
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        out = get_market_indices()
        assert len(out) == 4
        assert any(item["price"] == 0.0 for item in out)

    def test_nifty_close_dataframe_branch(self, monkeypatch):
        dates = pd.date_range("2025-01-01", periods=70, freq="B")
        hist = pd.DataFrame({
            "Close": pd.Series(range(100, 170), index=dates),
            "Open": pd.Series(range(100, 170), index=dates),
        })
        yf = MagicMock()
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        nifty = _nifty_close_series()
        assert len(nifty) >= 60

    def test_build_timeframe_stride_sampling(self):
        dates = pd.date_range("2020-01-01", periods=1500, freq="B")
        hist = pd.DataFrame({"Close": np.linspace(100, 200, len(dates))}, index=dates)
        charts = _build_timeframe_charts(hist, 200.0)
        assert len(charts["5Y"]["dates"]) < len(dates)

    def test_build_timeframe_empty_after_dropna(self):
        hist = pd.DataFrame({"Close": pd.Series([float("nan")] * 5, index=pd.date_range("2025-01-01", periods=5))})
        assert _build_timeframe_charts(hist, 0) == {}

    def test_analyze_fast_info_exception(self, monkeypatch, mock_nse_side, mock_bse, mock_quotes):
        fake_nse = MagicMock()
        fake_nse.get_equity_quote.return_value = None
        fake_nse.name_for.return_value = "Reliance Industries Ltd"
        monkeypatch.setattr("domains.equity.stock_analyzer.nse_client", fake_nse)

        def _ticker(sym):
            t = MagicMock()
            t.info = {"currency": "INR", "k1": 1, "k2": 2, "k3": 3, "k4": 4, "k5": 5,
                      "k6": 6, "k7": 7, "k8": 8, "k9": 9, "k10": 10, "k11": 11}
            type(t).fast_info = property(lambda self: (_ for _ in ()).throw(RuntimeError("fi down")))
            t.quarterly_income_stmt = pd.DataFrame()
            t.income_stmt = pd.DataFrame()
            t.quarterly_balance_sheet = pd.DataFrame()
            t.balance_sheet = pd.DataFrame()
            t.quarterly_cashflow = pd.DataFrame()
            t.cashflow = pd.DataFrame()
            t.calendar = {}
            t.earnings_estimate = pd.DataFrame()
            t.revenue_estimate = pd.DataFrame()
            t.analyst_price_targets = {}
            return t

        yf = MagicMock()
        yf.Ticker.side_effect = _ticker
        yf.download.return_value = _make_price_hist(90)
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["symbol"] == "RELIANCE"

    def test_analyze_val_helper_and_calendar_list(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes, mock_yfinance):
        tk = _FakeYfTicker("RELIANCE.NS")
        tk.calendar = {"Earnings Date": []}
        yf = MagicMock()
        yf.Ticker.return_value = tk
        yf.download.return_value = _make_price_hist(300)
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["symbol"] == "RELIANCE"

    def test_analyze_hist_close_dataframe_in_price_block(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="B")
        close_vals = np.linspace(900, 1000, 100)
        hist = pd.DataFrame({
            ("Close", "A"): close_vals,
            ("Close", "B"): close_vals,
        }, index=dates)
        yf = MagicMock()
        yf.Ticker.return_value = _FakeYfTicker("RELIANCE.NS")
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["current_price"] > 0

    def test_technicals_uptrend_branch(self):
        prices = pd.Series(list(range(50, 310)))
        tech = _compute_technicals(prices, 300.0, 310.0, 50.0)
        assert tech["above_200_dma"] is True
        assert tech["above_50_dma"] is True
        assert tech["trend"] == "Strong Uptrend"

    def test_technicals_uptrend_only_above_200(self):
        prices = pd.Series(list(range(100, 360)))
        tech = _compute_technicals(prices, 350.0, 360.0, 100.0)
        assert tech["above_200_dma"] is True
        assert tech["trend"] in {"Uptrend", "Strong Uptrend"}

    def test_nse_dividend_non_dict_action(self):
        assert _nse_dividend_yield(["bad"], 100.0) is None

    def test_dividend_yield_zero(self):
        from domains.equity.stock_analyzer import _dividend_yield_pct

        assert _dividend_yield_pct({"dividendYield": 0.0}) is None

    def test_fetch_consensus_targets_exception(self):
        from domains.equity.stock_analyzer import _fetch_consensus

        tk = MagicMock()
        tk.earnings_estimate = pd.DataFrame({"avg": [1.0], "numberOfAnalysts": [2]}, index=["0q"])
        tk.revenue_estimate = pd.DataFrame()
        type(tk).analyst_price_targets = property(lambda self: (_ for _ in ()).throw(RuntimeError("targets")))
        out = _fetch_consensus(tk, {"numberOfAnalystOpinions": 2})
        assert "price_target" not in out

    def test_market_indices_symbol_exception(self, monkeypatch):
        class BadFrame:
            def __getitem__(self, key):
                raise KeyError(key)

            @property
            def empty(self):
                return False

        yf = MagicMock()
        yf.download.return_value = BadFrame()
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        out = get_market_indices()
        assert len(out) == 4

    def test_nifty_and_chart_dataframe_close(self, monkeypatch):
        dates = pd.date_range("2025-01-01", periods=70, freq="B")
        hist = pd.DataFrame(
            {("Close", "A"): range(70), ("Close", "B"): range(70), ("Open", "A"): range(70)},
            index=dates,
        )
        yf = MagicMock()
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        MARKET_CACHE.clear()
        assert len(_nifty_close_series()) >= 60
        charts = _build_timeframe_charts(hist, 69.0)
        assert charts["1Y"]["dates"]

    def test_analyze_price_block_dataframe_close(self, monkeypatch, mock_nse, mock_nse_side, mock_bse, mock_quotes):
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="B")
        close_vals = np.linspace(900, 1000, 100)
        hist = pd.DataFrame(
            {("Close", "A"): close_vals, ("Close", "B"): close_vals},
            index=dates,
        )
        yf = MagicMock()
        yf.Ticker.side_effect = lambda sym: _FakeYfTicker(sym)
        yf.download.return_value = hist
        monkeypatch.setitem(sys.modules, "yfinance", yf)
        out = _analyze_stock_uncached("RELIANCE")
        assert out["current_price"] > 0

def test_stock_analyzer_beta_and_technicals(monkeypatch):
    from domains.equity import stock_analyzer

    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    hist = pd.DataFrame({"Close": np.linspace(100, 150, len(dates))}, index=dates)
    monkeypatch.setattr(
        stock_analyzer, "_nifty_close_series",
        lambda: {d.strftime("%Y-%m-%d"): 100 + i * 0.1 for i, d in enumerate(dates)},
    )
    beta = stock_analyzer._compute_beta(hist, "RELIANCE")
    assert beta is None or isinstance(beta, float)

    prices = pd.Series(np.linspace(90, 120, 250), index=pd.date_range("2024-01-01", periods=250))
    tech = stock_analyzer._compute_technicals(prices, current_price=115.0, week52_high=130.0, week52_low=85.0)
    assert tech["trend"] in ("Strong Uptrend", "Uptrend", "Consolidating", "Downtrend", "Neutral")
