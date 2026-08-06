"""
test_yahoo_provider_full_coverage.py

Full unit test coverage for shared.services.providers.yahoo:
- Symbol resolution via ISIN and fund name
- Live NAV fetching (fast info path & history path)
- Insights extraction (sectors, holdings, AUM, expense ratio)
"""

from unittest.mock import MagicMock
import pandas as pd
import pytest

from shared.services.providers.yahoo import YahooMetadataProvider


def test_resolve_yahoo_symbol(monkeypatch):
    provider = YahooMetadataProvider()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "quotes": [
            {"symbol": "0P0000XW12.BO", "typeDisp": "Mutual Fund"}
        ]
    }
    monkeypatch.setattr("requests.get", lambda url, headers, timeout: mock_resp)

    sym = provider.resolve_yahoo_symbol("INF209K01157", "HDFC Top 100")
    assert sym == "0P0000XW12.BO"


def test_fetch_live_nav(monkeypatch):
    provider = YahooMetadataProvider()
    monkeypatch.setattr(provider, "resolve_yahoo_symbol", lambda isin, fund_name: "0P0000XW12.BO")

    mock_ticker = MagicMock()
    mock_ticker.info = {"regularMarketPrice": 350.50}

    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", mock_yf)

    nav = provider.fetch_live_nav("INF209K01157")
    assert nav == 350.50


def test_fetch_insights(monkeypatch):
    provider = YahooMetadataProvider()
    monkeypatch.setattr(provider, "resolve_yahoo_symbol", lambda isin, fund_name: "0P0000XW12.BO")

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "sectorWeightings": [{"financial_services": 0.35}],
        "holdings": [{"holdingName": "HDFC Bank Ltd", "holdingPercent": 0.09}],
        "totalAssets": 50000000000,
        "annualReportExpenseRatio": 0.0085,
    }

    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", mock_yf)

    insights = provider.fetch_insights("INF209K01157", "HDFC Top 100", "Equity")
    assert "sectors" in insights
    assert len(insights["sectors"]) == 1
    assert insights["sectors"][0]["value"] == 35.0
    assert len(insights["holdings"]) == 1
    assert insights["holdings"][0]["name"] == "HDFC Bank Ltd"
    assert "5,000" in str(insights["aum"])


def test_resolve_yahoo_symbol_from_amfi_suite(monkeypatch):
    """From test_amfi_and_market_providers_full — MFApi companion coverage."""
    provider = YahooMetadataProvider()

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    monkeypatch.setattr(
        "requests.get",
        lambda url, **k: FakeResp(
            {"quotes": [{"symbol": "0P0000XWNE.BO", "typeDisp": "Mutual Fund"}]}
        ),
    )
    sym = provider.resolve_yahoo_symbol("INF179K01BE2", "HDFC Top 100")
    assert sym == "0P0000XWNE.BO"

    monkeypatch.setattr("requests.get", lambda url, **k: FakeResp({"quotes": []}))
    assert provider.resolve_yahoo_symbol("INVALID", "") is None

def test_yahoo_resolve_and_nav_fallbacks(monkeypatch):
    from shared.services.providers.yahoo import YahooMetadataProvider

    provider = YahooMetadataProvider()

    def mock_get(url, headers, timeout):
        if "INF123" in url:
            return MagicMock(json=lambda: {"quotes": [{"symbol": "X.BO", "typeDisp": "Equity"}]})
        if "HDFC" in url:
            return MagicMock(json=lambda: {"quotes": [{"symbol": "0P0001.BO", "typeDisp": "Mutual Fund"}]})
        return MagicMock(json=lambda: {"quotes": []})

    monkeypatch.setattr("requests.get", mock_get)
    assert provider.resolve_yahoo_symbol("INF123", "") is None
    sym = provider.resolve_yahoo_symbol("", "HDFC Top 100 Direct Growth")
    assert sym == "0P0001.BO"

    monkeypatch.setattr(provider, "resolve_yahoo_symbol", lambda *a: None)
    assert provider.fetch_live_nav("INF") is None

    monkeypatch.setattr(provider, "resolve_yahoo_symbol", lambda *a: "SYM")
    mock_ticker = MagicMock()
    mock_ticker.info = {}
    mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0]})
    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", mock_yf)
    assert provider.fetch_live_nav("INF", "Fund") == 100.0

def test_yahoo_isin_equity_and_name_exception(monkeypatch):
    from shared.services.providers.yahoo import YahooMetadataProvider

    provider = YahooMetadataProvider()

    def mock_get(url, headers, timeout):
        if "INF123" in url:
            return MagicMock(json=lambda: {"quotes": [{"symbol": "RELIANCE.NS", "typeDisp": "Equity"}]})
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.get", mock_get)
    assert provider.resolve_yahoo_symbol("INF123", "Some Fund Name") is None

def test_yahoo_nav_history_and_insights_branches(monkeypatch):
    from shared.services.providers.yahoo import YahooMetadataProvider

    provider = YahooMetadataProvider()
    monkeypatch.setattr(provider, "resolve_yahoo_symbol", lambda *a: "SYM.BO")

    mock_ticker = MagicMock()
    mock_ticker.info = {
        "totalAssets": 500_000_000,
        "morningStarRiskRating": 3,
        "sectorWeightings": [{"tech": 0.2}],
        "holdings": [{"holdingName": "ABC", "holdingPercent": 0.05}],
    }
    mock_ticker.history.return_value = pd.DataFrame({"Close": [99.5]})
    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    monkeypatch.setitem(__import__("sys").modules, "yfinance", mock_yf)

    nav = provider.fetch_live_nav("INF")
    assert nav == 99.5

    mock_ticker.info = {"totalAssets": 500_000_000, "morningStarRiskRating": 2}
    insights = provider.fetch_insights("INF", "Fund", "Equity")
    assert insights["risk"] == "MODERATE"
    assert "Cr" in insights["aum"]

    mock_ticker.info = {}
    mock_yf.Ticker.side_effect = RuntimeError("fail")
    assert provider.fetch_insights("INF", "Fund", "Equity")["source"] is None

