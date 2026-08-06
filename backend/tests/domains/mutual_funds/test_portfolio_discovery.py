"""Live portfolio discovery and snapshot persistence."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.mutual_funds.portfolio_discovery import fetch_live_portfolio, _auto_persist_snapshot
from shared.cache import MarketCache


@pytest.fixture(autouse=True)
def _clear_caches():
    MarketCache.invalidate_all()
    yield
    MarketCache.invalidate_all()


def test_fetch_live_portfolio_cache_hit():
    cached = {"source": "cache", "holdings": [{"name": "HDFC"}], "sectors": [], "aum": "1 Cr"}
    MarketCache.set("portfolio_INF123_Test Fund", cached)
    result = fetch_live_portfolio("INF123", "Large Cap", "Test Fund", refresh=False)
    assert result["source"] == "cache"

def test_fetch_live_portfolio_amfi_tier(monkeypatch):
    class FakeAMFI:
        def fetch_insights(self, isin, fund_name, category):
            return {
                "source": "AMFI Official Disclosure",
                "holdings": [{"name": "Reliance"}],
                "sectors": [{"sector": "Energy", "weight": 10}],
                "aum": "10,000 Cr",
                "expense_ratio": "0.5%",
                "risk": "HIGH",
            }

    monkeypatch.setattr(
        "shared.services.providers.amfi_db.AMFIDatabaseProvider",
        lambda: FakeAMFI(),
    )
    monkeypatch.setattr(
        "domains.mutual_funds.portfolio_discovery._auto_persist_snapshot",
        lambda *a, **k: None,
    )
    result = fetch_live_portfolio("INF999", "Flexi Cap", "Test AMC Fund", refresh=True)
    assert "AMFI" in result["source"]
    assert len(result["holdings"]) == 1

def test_fetch_live_portfolio_yahoo_fallback(monkeypatch):
    class BrokenAMFI:
        def fetch_insights(self, *a, **k):
            raise RuntimeError("db down")

    class FakeYahoo:
        def fetch_insights(self, isin, fund_name, category):
            return {
                "source": "Yahoo Finance",
                "holdings": [],
                "sectors": [{"sector": "Tech", "weight": 5}],
                "aum": "500 Cr",
            }

    monkeypatch.setattr(
        "shared.services.providers.amfi_db.AMFIDatabaseProvider",
        lambda: BrokenAMFI(),
    )
    monkeypatch.setattr(
        "shared.services.providers.yahoo.YahooMetadataProvider",
        lambda: FakeYahoo(),
    )
    monkeypatch.setattr(
        "domains.mutual_funds.portfolio_discovery._auto_persist_snapshot",
        lambda *a, **k: None,
    )
    result = fetch_live_portfolio("INF888", "Index", "Global ETF", refresh=True)
    assert result["source"] == "Yahoo Finance"

def test_fetch_live_portfolio_yahoo_exception_stays_blank(monkeypatch):
    class BrokenAMFI:
        def fetch_insights(self, *a, **k):
            raise RuntimeError("db down")

    class BrokenYahoo:
        def fetch_insights(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        "shared.services.providers.amfi_db.AMFIDatabaseProvider",
        lambda: BrokenAMFI(),
    )
    monkeypatch.setattr(
        "shared.services.providers.yahoo.YahooMetadataProvider",
        lambda: BrokenYahoo(),
    )
    result = fetch_live_portfolio("INF000", "Debt", "Missing Fund", refresh=True)
    assert result["source"] is None
    assert result["holdings"] == []

def test_auto_persist_snapshot_skips_non_inf_and_persists(monkeypatch):
    _auto_persist_snapshot("US123", "Foreign", "Other", {"aum": "1 Cr"})
    _auto_persist_snapshot("", "No ISIN", "Other", {"aum": "1 Cr"})

    executed = []

    class FakeConn:
        def execute(self, sql, params):
            executed.append(params)
            return None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("shared.db.connect", lambda: FakeConn())
    _auto_persist_snapshot(
        "INF123456789",
        "Persist Me Fund",
        "Large Cap",
        {
            "source": "Yahoo Finance",
            "aum": "12,345.67 Cr",
            "expense_ratio": "0.85%",
            "risk": "MODERATE",
            "sectors": [{"sector": "Fin"}],
            "holdings": [{"name": "Bank"}],
        },
    )
    assert executed
    assert executed[0][0] == "INF123456789"

def test_auto_persist_snapshot_swallows_db_errors(monkeypatch):
    monkeypatch.setattr("shared.db.connect", MagicMock(side_effect=RuntimeError("no db")))
    _auto_persist_snapshot("INF111", "X", "Y", {"aum": "1 Cr", "sectors": [], "holdings": []})

