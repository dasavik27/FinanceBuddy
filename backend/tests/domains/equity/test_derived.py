"""
Server-side compute caching for the equity domain.

Equity had no derived cache: every tab recomputed from scratch, where the mutual-fund
side collapses duplicate work. These tests pin that the two payloads worth memoizing
actually are, that the keys are content-addressed (so a changed input is never served a
stale answer), and that a live-price refresh does not needlessly discard realised gains.
"""

import pandas as pd
import pytest

from shared.services.cache import DERIVED_CACHE, MARKET_CACHE


@pytest.fixture(autouse=True)
def clean_caches():
    DERIVED_CACHE.clear()
    MARKET_CACHE.clear()
    yield
    DERIVED_CACHE.clear()
    MARKET_CACHE.clear()


@pytest.fixture(autouse=True)
def caching_on(monkeypatch):
    from shared import config
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)


def _stub_prices(monkeypatch, prices: dict[str, list[float]]):
    import domains.equity.quotes as eq

    def fake(tickers):
        idx = pd.date_range("2026-07-27", periods=2)
        cols = {t: prices[t] for t in tickers if t in prices}
        return pd.DataFrame(cols, index=idx) if cols else pd.DataFrame()

    monkeypatch.setattr(eq, "_download_closes", fake)


def _holdings(n: int = 3) -> pd.DataFrame:
    sectors = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC"]
    return pd.DataFrame([{
        "symbol": sectors[i % len(sectors)], "isin": "", "name": "", "exchange": "NSE",
        "quantity": 10.0 + i, "avg_price": 100.0, "ltp": 120.0,
        "current_value": (10.0 + i) * 120.0, "invested": (10.0 + i) * 100.0,
        "unrealized_pnl": (10.0 + i) * 20.0, "pnl_pct": 20.0,
        "day_change": 0.0, "day_change_pct": 0.0, "broker": "zerodha",
    } for i in range(n)])


def _trades() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2024-05-10", "symbol": "INFY", "type": "BUY", "quantity": 100, "price": 1000.0},
        {"date": "2025-06-15", "symbol": "INFY", "type": "SELL", "quantity": 100, "price": 1500.0},
    ])


def _portfolio(monkeypatch, trades=None):
    from domains.equity.models import EquityPortfolio
    _stub_prices(monkeypatch, {})
    return EquityPortfolio(_holdings(), trades if trades is not None else pd.DataFrame())


# ── the duplicate work that is now collapsed ──────────────────────────────────

def test_sector_allocation_is_computed_once_across_two_tabs(monkeypatch):
    """
    Overview renders the top six sectors and the Sector tab renders all of them, from
    the same inputs, on one dashboard load. The second groupby pair was pure waste.
    """
    p = _portfolio(monkeypatch)
    calls = {"n": 0}
    original = p._sector_allocation_uncached

    def counting():
        calls["n"] += 1
        return original()

    monkeypatch.setattr(p, "_sector_allocation_uncached", counting)

    first = p.get_sector_allocation()
    second = p.get_sector_allocation()   # the other tab

    assert calls["n"] == 1, f"recomputed {calls['n']} times"
    assert first == second


def test_capital_gains_is_computed_once(monkeypatch):
    p = _portfolio(monkeypatch, trades=_trades())
    calls = {"n": 0}
    original = p._compute_capital_gains_uncached

    def counting():
        calls["n"] += 1
        return original()

    monkeypatch.setattr(p, "_compute_capital_gains_uncached", counting)

    p.get_pnl_analysis()
    p.get_pnl_analysis()
    p._compute_capital_gains()

    assert calls["n"] == 1, f"FIFO matching ran {calls['n']} times"


# ── content addressing: a changed input is never served a stale answer ─────────

def test_a_different_portfolio_is_not_served_the_first_ones_allocation(monkeypatch):
    from domains.equity.models import EquityPortfolio
    _stub_prices(monkeypatch, {})

    a = EquityPortfolio(_holdings(2), pd.DataFrame())
    b = EquityPortfolio(_holdings(5), pd.DataFrame())

    alloc_a = a.get_sector_allocation()
    alloc_b = b.get_sector_allocation()

    assert alloc_a != alloc_b, "two different portfolios shared a cache entry"
    assert len(alloc_b["by_sector"]) >= len(alloc_a["by_sector"])


def test_a_changed_tradebook_recomputes_gains(monkeypatch):
    from domains.equity.models import EquityPortfolio
    _stub_prices(monkeypatch, {})

    p1 = EquityPortfolio(_holdings(), _trades())
    first = p1._compute_capital_gains()

    more = pd.concat([_trades(), pd.DataFrame([
        {"date": "2024-01-10", "symbol": "TCS", "type": "BUY", "quantity": 10, "price": 100.0},
        {"date": "2025-09-10", "symbol": "TCS", "type": "SELL", "quantity": 10, "price": 300.0},
    ])], ignore_index=True)
    p2 = EquityPortfolio(_holdings(), more)
    second = p2._compute_capital_gains()

    assert first["lifetime_ltcg"] != second["lifetime_ltcg"], (
        "an extra round-trip in the tradebook did not change the result"
    )


def test_price_refresh_does_not_invalidate_realised_gains(monkeypatch):
    """
    Realised gains are a function of executed trades, not of today's price. Keying them
    on the holdings frame too would have thrown the entry away on every 5-minute sync.
    """
    from domains.equity.models import EquityPortfolio

    _stub_prices(monkeypatch, {"RELIANCE.NS": [100.0, 999.0], "TCS.NS": [100.0, 888.0],
                               "HDFCBANK.NS": [100.0, 777.0]})
    p = EquityPortfolio(_holdings(), _trades())

    before = p._compute_capital_gains()

    calls = {"n": 0}
    original = p._compute_capital_gains_uncached

    def counting():
        calls["n"] += 1
        return original()

    monkeypatch.setattr(p, "_compute_capital_gains_uncached", counting)

    p.update_live_prices()          # holdings frame changes; tradebook does not
    after = p._compute_capital_gains()

    assert calls["n"] == 0, "a price refresh discarded the capital-gains entry"
    assert before["lifetime_ltcg"] == after["lifetime_ltcg"]


def test_price_refresh_does_invalidate_sector_allocation(monkeypatch):
    """The mirror of the above: allocation percentages DO move with price, so that
    entry must not survive a refresh."""
    from domains.equity.models import EquityPortfolio

    _stub_prices(monkeypatch, {"RELIANCE.NS": [100.0, 999.0], "TCS.NS": [100.0, 888.0],
                               "HDFCBANK.NS": [100.0, 777.0]})
    p = EquityPortfolio(_holdings(), pd.DataFrame())

    before = p.get_sector_allocation()
    p.update_live_prices()
    after = p.get_sector_allocation()

    assert before != after, "stale allocation served after a price change"


def test_unhashable_input_bypasses_the_cache_rather_than_guessing(monkeypatch):
    """
    A frame that cannot be fingerprinted must not be given a made-up key - that is how
    one portfolio ends up serving another's numbers.
    """
    from domains.equity import derived

    monkeypatch.setattr(derived, "_frame_fingerprint", lambda df: None)

    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"by_sector": [], "by_industry": []}

    derived.sector_allocation(_holdings(), 100.0, compute)
    derived.sector_allocation(_holdings(), 100.0, compute)

    assert calls["n"] == 2, "an unfingerprintable frame was cached under some key anyway"


# ── L2: close history survives a process restart ──────────────────────────────

def test_close_history_is_restored_from_disk_after_an_l1_wipe(monkeypatch, tmp_path):
    """
    A free-tier instance that just woke has an empty L1. Without an L2 tier it
    re-downloads every symbol's history; MF's NAV bundle already survives this.
    """
    import shared.cache as disk
    import domains.equity.quotes as eq

    monkeypatch.setattr(disk, "CACHE_DIR", str(tmp_path))

    downloads: list[int] = []
    dates = pd.bdate_range("2026-01-01", periods=40)

    def counting_history(tickers, days):
        downloads.append(len(tickers))
        return pd.DataFrame({t: range(len(dates)) for t in tickers}, index=dates, dtype="float64")

    monkeypatch.setattr(eq, "_download_history", counting_history)

    first = eq.fetch_close_history(["RELIANCE", "TCS"], 30)
    assert len(downloads) == 1 and not first.empty

    # Simulate a restart: L1 gone, disk intact.
    MARKET_CACHE.clear()

    second = eq.fetch_close_history(["RELIANCE", "TCS"], 30)

    assert len(downloads) == 1, "history was re-downloaded despite being on disk"
    assert list(second.columns) == list(first.columns)
    assert second.shape == first.shape
    pd.testing.assert_frame_equal(
        first.sort_index(axis=1), second.sort_index(axis=1), check_freq=False
    )


def test_live_quotes_are_deliberately_not_persisted_to_disk(monkeypatch, tmp_path):
    """
    Quotes stay L1-only on purpose: their TTL is 5 minutes but MarketCache expires
    against the global CACHE_TTL_MINUTES (60), so a disk hit could serve an hour-old
    last-traded price. This pins the decision so it is not "fixed" by accident.
    """
    import shared.cache as disk
    import domains.equity.quotes as eq

    monkeypatch.setattr(disk, "CACHE_DIR", str(tmp_path))

    calls: list[int] = []

    def counting(tickers):
        calls.append(len(tickers))
        idx = pd.date_range("2026-07-27", periods=2)
        return pd.DataFrame({t: [100.0, 110.0] for t in tickers}, index=idx)

    monkeypatch.setattr(eq, "_download_closes", counting)

    eq.fetch_quotes(["RELIANCE"])
    MARKET_CACHE.clear()            # restart
    eq.fetch_quotes(["RELIANCE"])

    assert len(calls) == 2, (
        "a live quote was restored from disk; it could be up to an hour stale"
    )

def test_equity_derived_fingerprint_and_memo(monkeypatch):
    from domains.equity import derived as eq_derived

    def _holdings_df() -> pd.DataFrame:
        return pd.DataFrame([
            {
                "symbol": "RELIANCE", "quantity": 10.0, "avg_price": 1000.0, "ltp": 1200.0,
                "current_value": 12000.0, "invested": 10000.0, "unrealized_pnl": 2000.0,
                "pnl_pct": 20.0, "day_change": 50.0, "day_change_pct": 0.5,
                "exchange": "NSE", "name": "Reliance", "isin": "INE002A01018", "broker": "zerodha",
                "sector": "Energy", "industry": "Oil & Gas",
            },
        ])

    assert eq_derived._frame_fingerprint(None) == "none"

    real_hash = pd.util.hash_pandas_object

    def flaky_hash(df, **kwargs):
        if "bad" in df.columns:
            raise RuntimeError("unhashable")
        return real_hash(df, **kwargs)

    monkeypatch.setattr(pd.util, "hash_pandas_object", flaky_hash)
    assert eq_derived._frame_fingerprint(pd.DataFrame({"bad": [1]})) is None

    df = _holdings_df()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"sectors": []}

    r1 = eq_derived.sector_allocation(df, 12000.0, compute)
    r2 = eq_derived.sector_allocation(df, 12000.0, compute)
    assert r1 == r2
    assert calls["n"] >= 1
    assert eq_derived._memo(None, lambda: {"x": 1}) == {"x": 1}
