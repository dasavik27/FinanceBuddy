"""Market data provider base classes."""

import pandas as pd
import pytest

from shared.services.providers.base import BaseMetadataProvider, MarketDataProvider


class _StubMetadataProvider(BaseMetadataProvider):
    name = "stub"

    def fetch_insights(self, isin, fund_name, category):
        out = self._get_empty_result()
        out["source"] = "stub"
        return out


class _StubMarketProvider(MarketDataProvider):
    name = "stub-market"

    def fetch_fund_meta(self, code):
        return {"name": code}

    def search_funds(self, query):
        return [{"code": query}]

    def fetch_nav_series(self, code, days):
        return pd.Series(dtype=float)


def test_base_metadata_provider_empty_result():
    provider = _StubMetadataProvider()
    empty = provider._get_empty_result()
    assert empty["source"] is None
    assert empty["sectors"] == []
    assert empty["aum_fallback"] is False

    insights = provider.fetch_insights("INF1", "Fund A", "Equity")
    assert insights["source"] == "stub"

def test_market_data_provider_concrete():
    provider = _StubMarketProvider()
    assert provider.fetch_fund_meta("120716")["name"] == "120716"
    assert provider.search_funds("HDFC") == [{"code": "HDFC"}]
    assert provider.fetch_nav_series("120716", 30).empty

def test_market_data_provider_is_abstract():
    with pytest.raises(TypeError):
        MarketDataProvider()

