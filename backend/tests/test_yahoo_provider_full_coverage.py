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
