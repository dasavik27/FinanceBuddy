"""
tests/test_stock_analyzer.py

Regression cover for the equity Stock Analyzer.

Every case here corresponds to a number the analyzer was showing users incorrectly:
a 46% dividend yield for Reliance, Infosys' cash flow understated 85x, TCS and HDFC
Bank listed as Reliance's oil-and-gas peers, and an analyst "estimate" derived from
the actual it was compared against so that every quarter beat.

Nothing here touches the network - the upstream seams are faked.
"""

from __future__ import annotations

import pandas as pd
import pytest

from domains.equity.quotes import resolve_symbol, to_yahoo_ticker
from domains.equity.stock_analyzer import (
    _dividend_yield_pct,
    _fetch_consensus,
    _fx_to_inr,
    _peer_symbols,
)


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
