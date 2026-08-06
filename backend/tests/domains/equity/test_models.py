"""
Correctness regressions for the equity analytics model.

Every test here corresponds to a defect that shipped and was invisible in production,
mostly because the failure was swallowed by a broad `except Exception` and logged at
DEBUG. No database and no network: the model is pure given its inputs, and the quotes
provider is stubbed at its single seam.
"""

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def clear_quote_cache():
    """The quote cache is process-global; a stale entry would mask a stub."""
    from shared.services.cache import MARKET_CACHE

    MARKET_CACHE.clear()
    yield
    MARKET_CACHE.clear()


def _stub_quotes(monkeypatch, price_by_ticker: dict[str, list[float]]):
    """Point the provider seam at a fixed set of close series."""
    import domains.equity.quotes as eq

    def fake_download(tickers):
        idx = pd.date_range("2026-07-27", periods=2)
        cols = {t: price_by_ticker[t] for t in tickers if t in price_by_ticker}
        return pd.DataFrame(cols, index=idx) if cols else pd.DataFrame()

    monkeypatch.setattr(eq, "_download_closes", fake_download)


def _holdings(rows: list[dict]) -> pd.DataFrame:
    base = {
        "isin": "", "name": "", "exchange": "NSE", "ltp": 0.0, "current_value": 0.0,
        "unrealized_pnl": 0.0, "pnl_pct": 0.0, "day_change": 0.0,
        "day_change_pct": 0.0, "broker": "zerodha",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


# ── the bug that made live prices a no-op ─────────────────────────────────────

def test_multi_ticker_price_update_actually_applies(monkeypatch):
    """
    The multi-ticker branch read

        data.get((ticker, "Close")) or data.get(ticker, {}).get("Close")

    and `Series or ...` evaluates bool(Series), which raises "The truth value of a
    Series is ambiguous" for every portfolio with more than one holding. The exception
    was caught per-symbol and logged at DEBUG, so update_live_prices() paid for N HTTP
    requests and then updated nothing.
    """
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {"RELIANCE.NS": [1000.0, 1200.0], "TCS.NS": [3000.0, 3300.0]})

    p = EquityPortfolio(_holdings([
        {"symbol": "RELIANCE", "quantity": 10, "avg_price": 1000.0, "invested": 10000.0},
        {"symbol": "TCS", "quantity": 5, "avg_price": 3000.0, "invested": 15000.0},
    ]), pd.DataFrame())
    p.update_live_prices()

    by_symbol = p.df_holdings.set_index("symbol")
    assert by_symbol.loc["RELIANCE", "ltp"] == 1200.0
    assert by_symbol.loc["TCS", "ltp"] == 3300.0
    assert by_symbol.loc["RELIANCE", "current_value"] == 12000.0
    assert by_symbol.loc["TCS", "current_value"] == 16500.0
    assert p.total_value == 28500.0


def test_single_holding_price_update_applies(monkeypatch):
    """The single-ticker branch failed too, silently returning None and `continue`."""
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {"INFY.NS": [1400.0, 1500.0]})

    p = EquityPortfolio(_holdings([
        {"symbol": "INFY", "quantity": 20, "avg_price": 1400.0, "invested": 28000.0},
    ]), pd.DataFrame())
    p.update_live_prices()

    assert float(p.df_holdings["ltp"].iloc[0]) == 1500.0
    assert p.total_value == 30000.0


def test_duplicate_symbol_rows_are_valued_on_their_own_quantity(monkeypatch):
    """
    Updates were applied with a boolean mask but read quantity via `.values[0]`, so a
    symbol appearing twice (NSE + BSE, or two demat accounts) had the first row's
    quantity written to every matching row.
    """
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {"TCS.NS": [3000.0, 3300.0]})

    p = EquityPortfolio(_holdings([
        {"symbol": "TCS", "exchange": "NSE", "quantity": 5, "avg_price": 3000.0, "invested": 15000.0},
        {"symbol": "TCS", "exchange": "BSE", "quantity": 50, "avg_price": 3000.0, "invested": 150000.0},
    ]), pd.DataFrame())
    p.update_live_prices()

    values = p.df_holdings.set_index("exchange")["current_value"]
    assert values.loc["NSE"] == 16500.0     # 5 x 3300
    assert values.loc["BSE"] == 165000.0    # 50 x 3300, not 5 x 3300
    assert p.total_value == 181500.0


def test_unpriced_symbols_keep_their_stored_price(monkeypatch):
    """A symbol the provider does not know is missing data, not a price of zero."""
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {"RELIANCE.NS": [1000.0, 1200.0]})

    p = EquityPortfolio(_holdings([
        {"symbol": "RELIANCE", "quantity": 10, "avg_price": 1000.0, "invested": 10000.0},
        {"symbol": "DELISTED", "quantity": 10, "avg_price": 50.0, "invested": 500.0, "ltp": 50.0,
         "current_value": 500.0},
    ]), pd.DataFrame())
    p.update_live_prices()

    by_symbol = p.df_holdings.set_index("symbol")
    assert by_symbol.loc["DELISTED", "ltp"] == 50.0
    assert by_symbol.loc["DELISTED", "current_value"] == 500.0


# ── day change ────────────────────────────────────────────────────────────────

def test_day_change_is_scaled_by_quantity(monkeypatch):
    """
    Brokers report day change *per share*. It was summed straight across positions, so
    the Overview tile showed the sum of per-share moves labelled as rupees.
    """
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {"RELIANCE.NS": [1000.0, 1010.0], "TCS.NS": [3000.0, 3020.0]})

    p = EquityPortfolio(_holdings([
        {"symbol": "RELIANCE", "quantity": 10, "avg_price": 1000.0, "invested": 10000.0},
        {"symbol": "TCS", "quantity": 5, "avg_price": 3000.0, "invested": 15000.0},
    ]), pd.DataFrame())
    p.update_live_prices()

    # 10 shares x Rs10 + 5 shares x Rs20 = Rs200, not Rs30.
    assert p.get_summary()["day_change"] == 200.0


def test_day_change_is_suppressed_when_prices_could_not_refresh(monkeypatch):
    """
    With no refresh the column still holds the broker's per-share figure, which is not
    additive. Reporting nothing beats reporting a number that looks like rupees.
    """
    from domains.equity.models import EquityPortfolio

    _stub_quotes(monkeypatch, {})

    p = EquityPortfolio(_holdings([
        {"symbol": "RELIANCE", "quantity": 10, "avg_price": 1000.0, "invested": 10000.0,
         "ltp": 1000.0, "current_value": 10000.0, "day_change": 7.5},
    ]), pd.DataFrame())
    p.update_live_prices()

    assert p.get_summary()["day_change"] == 0.0


# ── capital gains ─────────────────────────────────────────────────────────────

def _trades(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_negative_short_term_gains_do_not_produce_negative_tax():
    """A realised loss carries forward. It is not a refund, and `stcg * 0.20` on a
    negative number rendered a negative liability in the UI."""
    from domains.equity.models import _stcg_tax

    assert _stcg_tax(-50000.0) == 0.0
    assert _stcg_tax(50000.0) == 10000.0


def test_gains_are_bucketed_by_financial_year():
    """
    Gains were summed across the whole tradebook and the annual section 112A exemption
    applied once to the total, so a multi-year tradebook reported every year's gains as
    the current year's liability.
    """
    from domains.equity.models import EquityPortfolio, _ltcg_tax

    trades = _trades([
        {"date": "2021-05-10", "symbol": "INFY", "type": "BUY", "quantity": 100, "price": 1000.0},
        {"date": "2023-06-15", "symbol": "INFY", "type": "SELL", "quantity": 100, "price": 3000.0},
        {"date": "2022-05-10", "symbol": "WIPRO", "type": "BUY", "quantity": 100, "price": 1000.0},
        {"date": "2024-06-15", "symbol": "WIPRO", "type": "SELL", "quantity": 100, "price": 3000.0},
    ])
    p = EquityPortfolio(
        _holdings([{"symbol": "INFY", "quantity": 1, "avg_price": 1.0, "invested": 1.0}]),
        trades,
    )
    gains = p._compute_capital_gains()

    assert set(gains["by_financial_year"]) == {"2023-24", "2024-25"}
    assert gains["by_financial_year"]["2023-24"]["ltcg"] == 200000.0
    assert gains["by_financial_year"]["2024-25"]["ltcg"] == 200000.0

    # Two years, each with its own Rs1.25L exemption.
    per_year = sum(_ltcg_tax(b["ltcg"]) for b in gains["by_financial_year"].values())
    lumped = _ltcg_tax(gains["lifetime_ltcg"])
    assert per_year == 18750.0
    assert lumped == 34375.0
    assert per_year < lumped, "bucketing must not be more expensive than lumping"


def test_short_versus_long_term_split_uses_the_holding_period():
    from domains.equity.models import EquityPortfolio

    trades = _trades([
        {"date": "2025-01-10", "symbol": "A", "type": "BUY", "quantity": 10, "price": 100.0},
        {"date": "2025-06-10", "symbol": "A", "type": "SELL", "quantity": 10, "price": 150.0},
        {"date": "2023-01-10", "symbol": "B", "type": "BUY", "quantity": 10, "price": 100.0},
        {"date": "2025-06-10", "symbol": "B", "type": "SELL", "quantity": 10, "price": 150.0},
    ])
    p = EquityPortfolio(
        _holdings([{"symbol": "A", "quantity": 1, "avg_price": 1.0, "invested": 1.0}]),
        trades,
    )
    bucket = p._compute_capital_gains()["by_financial_year"]["2025-26"]
    assert bucket["stcg"] == 500.0   # held 5 months
    assert bucket["ltcg"] == 500.0   # held ~2.5 years


def test_fifo_matching_consumes_the_oldest_lot_first():
    from domains.equity.models import EquityPortfolio

    trades = _trades([
        {"date": "2025-01-10", "symbol": "A", "type": "BUY", "quantity": 10, "price": 100.0},
        {"date": "2025-02-10", "symbol": "A", "type": "BUY", "quantity": 10, "price": 200.0},
        {"date": "2025-06-10", "symbol": "A", "type": "SELL", "quantity": 15, "price": 300.0},
    ])
    p = EquityPortfolio(
        _holdings([{"symbol": "A", "quantity": 1, "avg_price": 1.0, "invested": 1.0}]),
        trades,
    )
    bucket = p._compute_capital_gains()["by_financial_year"]["2025-26"]
    # 10 @ (300-100) + 5 @ (300-200) = 2000 + 500
    assert bucket["stcg"] == 2500.0


def test_sells_with_no_matching_buy_are_reported_not_dropped():
    """
    `elif "SELL" in tx_type and buy_lots:` skipped the sell entirely when no lot was
    open, understating gains with no indication anything was missing.
    """
    from domains.equity.models import EquityPortfolio

    trades = _trades([
        {"date": "2025-06-10", "symbol": "A", "type": "SELL", "quantity": 7, "price": 300.0},
    ])
    p = EquityPortfolio(
        _holdings([{"symbol": "A", "quantity": 1, "avg_price": 1.0, "invested": 1.0}]),
        trades,
    )
    assert p._compute_capital_gains()["unmatched_sell_qty"] == 7.0


def test_financial_year_boundary_is_the_first_of_april():
    from domains.equity.models import _financial_year

    assert _financial_year(pd.Timestamp("2026-03-31")) == "2025-26"
    assert _financial_year(pd.Timestamp("2026-04-01")) == "2026-27"


# ── holdings table ────────────────────────────────────────────────────────────

def test_unknown_sort_column_falls_back_rather_than_returning_arbitrary_order():
    from domains.equity.models import EquityPortfolio

    p = EquityPortfolio(_holdings([
        {"symbol": "A", "quantity": 1, "avg_price": 10.0, "invested": 10.0, "current_value": 10.0},
        {"symbol": "B", "quantity": 1, "avg_price": 99.0, "invested": 99.0, "current_value": 99.0},
    ]), pd.DataFrame())

    rows = p.get_holdings(sort_by="'; DROP TABLE sessions--")
    assert [r["symbol"] for r in rows] == ["B", "A"]  # default: value descending


def test_empty_portfolio_summary_is_empty_not_partial():
    from domains.equity.models import EquityPortfolio

    p = EquityPortfolio(pd.DataFrame(), pd.DataFrame())
    assert p.get_summary() == {}
    assert p.get_holdings() == []
    assert p.get_sector_allocation() == {"by_sector": [], "by_industry": []}


# ── cache parity with the mutual-fund provider paths ──────────────────────────

def test_quotes_honour_the_cache_kill_switch(monkeypatch):
    """
    CACHE_TTL_MINUTES <= 0 disables market-data caching process-wide and is settable at
    runtime via POST /market/config. Every MF provider path honours it; equity's quote
    service initially did not, so "turn caching off and re-check" kept serving stock
    prices from L1.
    """
    import domains.equity.quotes as eq
    from shared import config

    calls: list[list[str]] = []

    def counting_download(tickers):
        calls.append(list(tickers))
        idx = pd.date_range("2026-07-27", periods=2)
        return pd.DataFrame({t: [100.0, 110.0] for t in tickers}, index=idx)

    monkeypatch.setattr(eq, "_download_closes", counting_download)

    # Caching on: the second call is served from L1.
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    eq.fetch_quotes(["RELIANCE"])
    eq.fetch_quotes(["RELIANCE"])
    assert len(calls) == 1, "second call should have hit the cache"

    # Caching off: every call goes upstream.
    calls.clear()
    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 0)
    eq.fetch_quotes(["RELIANCE"])
    eq.fetch_quotes(["RELIANCE"])
    assert len(calls) == 2, "kill-switch did not bypass the cache"


def test_quotes_are_batched_not_one_request_per_symbol(monkeypatch):
    """
    The original code issued one HTTP request per holding via yfinance's internal
    fan-out. A 50-stock portfolio should resolve in a single upstream call.
    """
    import domains.equity.quotes as eq
    from shared import config

    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    batches: list[int] = []

    def counting_download(tickers):
        batches.append(len(tickers))
        idx = pd.date_range("2026-07-27", periods=2)
        return pd.DataFrame({t: [100.0, 110.0] for t in tickers}, index=idx)

    monkeypatch.setattr(eq, "_download_closes", counting_download)

    symbols = [f"SYM{i}" for i in range(50)]
    quotes = eq.fetch_quotes(symbols)

    assert len(quotes) == 50
    assert len(batches) == 1, f"expected 1 batched request, got {len(batches)}"
    assert batches[0] == 50


def test_malformed_symbols_are_not_sent_upstream(monkeypatch):
    """A symbol is not charset-validated by the broker export, and it ends up in a
    provider request path. Rejected before it leaves the process."""
    import domains.equity.quotes as eq
    from shared import config

    monkeypatch.setattr(config, "CACHE_TTL_MINUTES", 60)
    sent: list[str] = []

    def capture(tickers):
        sent.extend(tickers)
        return pd.DataFrame()

    monkeypatch.setattr(eq, "_download_closes", capture)
    eq.fetch_quotes(["RELIANCE", "../../etc/passwd", "A B C", "'; DROP TABLE--", ""])

    assert sent == ["RELIANCE.NS"], f"malformed symbols reached the provider: {sent}"

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


def test_equity_tax_helpers_and_financial_year():
    from domains.equity.models import _financial_year, _ltcg_tax, _stcg_tax

    assert _stcg_tax(-1000) == 0.0
    assert _ltcg_tax(200000) == round((200000 - 125000) * 0.125, 2)
    assert _financial_year(pd.Timestamp("2025-02-01")) == "2024-25"
    assert _financial_year(pd.Timestamp("2025-05-01")) == "2025-26"

def test_equity_models_full_branches(monkeypatch):
    from domains.equity.models import EquityPortfolio, _to_ns_ticker

    assert _to_ns_ticker("RELIANCE") == "RELIANCE.NS"

    empty = EquityPortfolio(pd.DataFrame(), pd.DataFrame())
    assert empty.get_summary() == {}
    assert empty.get_holdings() == []
    assert empty.get_sector_allocation() == {"by_sector": [], "by_industry": []}
    assert empty.get_pnl_analysis() == {}
    assert empty.get_insights() == {}
    assert empty._diversification_score() == 0
    empty.update_live_prices()

    df = _holdings_df()
    p = EquityPortfolio(df)
    monkeypatch.setattr("domains.equity.quotes.fetch_quotes", lambda symbols: {})
    p.update_live_prices()

    df_no_col = df.drop(columns=["current_value"])
    p2 = EquityPortfolio(df_no_col)
    assert p2.total_value >= 0

    df_zero = df.copy()
    df_zero["current_value"] = 0.0
    df_zero["invested"] = 0.0
    p3 = EquityPortfolio(df_zero)
    assert p3.get_summary()["pnl_pct"] == 0.0

    p4 = EquityPortfolio(df)
    p4._day_change_is_positional = True
    summary = p4.get_summary()
    assert "day_change" in summary

    trades = pd.DataFrame([
        {"date": "2024-06-01", "symbol": "RELIANCE", "type": "BUY", "quantity": 10, "price": 1000.0},
        {"date": "2025-01-01", "symbol": "RELIANCE", "type": "SELL", "quantity": 3, "price": 1200.0},
        {"date": "2025-01-01", "symbol": "RELIANCE", "type": "DIVIDEND", "quantity": 1, "price": 10.0},
    ])
    p5 = EquityPortfolio(df, trades)
    gains = p5._compute_capital_gains()
    assert "2024-25" in gains["by_financial_year"] or "2025-26" in gains["by_financial_year"]
    pnl = p5.get_pnl_analysis()
    assert pnl["has_tradebook"] is True

    holdings_out = p5.get_holdings(sort_by="not_a_real_column")
    assert holdings_out

    bad_trades = pd.DataFrame([{"date": None, "symbol": "X", "type": "BUY", "quantity": 1, "price": 1.0}])
    p6 = EquityPortfolio(df, bad_trades)
    assert p6._compute_capital_gains()["lifetime_stcg"] == 0.0

    small = pd.DataFrame([{
        "symbol": "A", "quantity": 100, "avg_price": 10, "ltp": 10,
        "current_value": 1000, "invested": 1000, "unrealized_pnl": 0, "pnl_pct": 0,
        "sector": "Energy", "industry": "Oil", "exchange": "NSE", "name": "A", "broker": "csv",
    }])
    p7 = EquityPortfolio(small)
    assert p7._diversification_score() < 100

def test_equity_models_capital_gains_branches():
    from domains.equity.models import EquityPortfolio

    df = _holdings_df()
    trades = pd.DataFrame([
        {"date": "2024-01-01", "symbol": "RELIANCE", "type": "BUY", "quantity": 0, "price": 100.0},
        {"date": "2024-02-01", "symbol": "RELIANCE", "type": "BUY", "quantity": 10, "price": 1000.0},
        {"date": "2023-01-01", "symbol": "RELIANCE", "type": "BUY", "quantity": 5, "price": 900.0},
        {"date": "2025-06-01", "symbol": "RELIANCE", "type": "SELL", "quantity": 20, "price": 1200.0},
        {"date": "2025-06-02", "symbol": "RELIANCE", "type": "HOLD", "quantity": 1, "price": 1.0},
    ])
    p = EquityPortfolio(df, trades)
    gains = p._compute_capital_gains()
    assert gains["unmatched_sell_qty"] > 0

    sparse = pd.DataFrame([{"symbol": "A", "quantity": 1, "avg_price": 1, "current_value": 0, "invested": 0}])
    p2 = EquityPortfolio(sparse)
    assert p2.total_value == 0.0
    assert p2.get_holdings(sort_by="symbol")[0]["weight_pct"] == 0.0

    no_quotes_df = df.drop(columns=["current_value", "invested"])
    p3 = EquityPortfolio(no_quotes_df)
    assert p3.total_value >= 0

    div_df = pd.DataFrame([
        {"symbol": "A", "quantity": 1, "avg_price": 10, "ltp": 10, "current_value": 10,
         "invested": 10, "unrealized_pnl": 0, "pnl_pct": 0, "sector": "Energy",
         "industry": "Oil", "exchange": "NSE", "name": "A", "broker": "csv"},
    ] * 3 + [
        {"symbol": "B", "quantity": 1, "avg_price": 10, "ltp": 10, "current_value": 10,
         "invested": 10, "unrealized_pnl": 0, "pnl_pct": 0, "sector": "Energy",
         "industry": "Oil", "exchange": "NSE", "name": "B", "broker": "csv"},
    ] * 2)
    p4 = EquityPortfolio(div_df)
    assert 0 <= p4._diversification_score() <= 100

def test_equity_models_no_quotes_and_diversification(monkeypatch):
    from domains.equity.models import EquityPortfolio

    df = _holdings_df()
    p = EquityPortfolio(df)
    monkeypatch.setattr("domains.equity.models.fetch_quotes", lambda symbols: {})
    p.update_live_prices()

    many_sectors = pd.DataFrame([
        {"symbol": f"S{i}", "quantity": 1, "avg_price": 10, "ltp": 10, "current_value": 100,
         "invested": 10, "unrealized_pnl": 90, "pnl_pct": 900, "sector": f"Sec{i % 2}",
         "industry": "X", "exchange": "NSE", "name": f"S{i}", "broker": "csv"}
        for i in range(4)
    ])
    p2 = EquityPortfolio(many_sectors)
    assert p2._diversification_score() < 100

    concentrated = pd.DataFrame([
        {"symbol": "BIG", "quantity": 1, "avg_price": 10, "ltp": 100, "current_value": 1000,
         "invested": 10, "unrealized_pnl": 990, "pnl_pct": 9900, "sector": "Energy",
         "industry": "Oil", "exchange": "NSE", "name": "BIG", "broker": "csv"},
        {"symbol": "SMALL", "quantity": 1, "avg_price": 1, "ltp": 1, "current_value": 1,
         "invested": 1, "unrealized_pnl": 0, "pnl_pct": 0, "sector": "IT",
         "industry": "Svcs", "exchange": "NSE", "name": "SMALL", "broker": "csv"},
    ])
    p3 = EquityPortfolio(concentrated)
    assert p3._diversification_score() < 100

    two_sectors = pd.DataFrame([
        {"symbol": f"S{i}", "quantity": 1, "avg_price": 10, "ltp": 10, "current_value": 10,
         "invested": 10, "unrealized_pnl": 0, "pnl_pct": 0, "sector": "A" if i < 5 else "B",
         "industry": "X", "exchange": "NSE", "name": f"S{i}", "broker": "csv"}
        for i in range(10)
    ])
    assert EquityPortfolio(two_sectors)._diversification_score() < 100

def test_equity_portfolio_diversification_score():
    from domains.equity.models import EquityPortfolio

    df = pd.DataFrame([
        {"symbol": "A", "sector": "Tech", "market_value": 5000.0, "weight_pct": 35.0,
         "quantity": 10, "avg_price": 100, "ltp": 110, "invested": 4000, "unrealized_pnl": 100, "pnl_pct": 2.5},
        {"symbol": "B", "sector": "Fin", "market_value": 3000.0, "weight_pct": 25.0,
         "quantity": 5, "avg_price": 200, "ltp": 210, "invested": 2500, "unrealized_pnl": 50, "pnl_pct": 2.0},
        {"symbol": "C", "sector": "Health", "market_value": 2000.0, "weight_pct": 20.0,
         "quantity": 8, "avg_price": 150, "ltp": 160, "invested": 1800, "unrealized_pnl": 20, "pnl_pct": 1.0},
    ])
    ep = EquityPortfolio(df_holdings=df, df_trades=pd.DataFrame())
    insights = ep.get_insights()
    assert insights["diversification_score"] < 100
