"""
tests/test_amfi_db_provider.py
Unit tests for Tier 1 AMFIDatabaseProvider and portfolio discovery.
"""

import datetime
import json
import pytest

from domains.mutual_funds.portfolio_discovery import fetch_live_portfolio
from shared import db
from shared.services.providers import amfi_db
from tests.helpers import FakeDbConn


def test_fetch_live_portfolio_unseeded_stays_blank():
    """Verify unseeded funds stay blank — no deterministic heuristic fill-in."""
    result = fetch_live_portfolio(
        isin="UNKNOWN_ISIN_999",
        category="Small Cap Fund",
        fund_name="Random Unindexed Fund",
        refresh=True,
    )
    assert result["aum_fallback"] is False
    assert result["risk_fallback"] is False
    assert result["risk"] is None
    assert result["aum"] is None
    assert result["expense_ratio"] is None
    assert result["sectors"] == []
    assert result["holdings"] == []


def test_amfi_db_fetch_insights_from_providers_suite(monkeypatch):
    """From test_amfi_and_market_providers_full."""
    conn = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn)
    now = datetime.datetime.now(datetime.timezone.utc)

    conn.queue_result(fetchone=(
        "INF179K01BE2",
        119062,
        "HDFC Top 100 Fund",
        50000.0,
        0.85,
        "VERY HIGH",
        "1%",
        json.dumps([{"sector": "Financial Services", "value": 35.0}]),
        json.dumps([{"name": "HDFC Bank", "pct": 9.5}]),
        "AMFI Official Disclosure",
        now,
    ))
    db_prov = amfi_db.AMFIDatabaseProvider()
    result = db_prov.fetch_insights(isin="INF179K01BE2")
    assert result["risk"] == "VERY HIGH"
    assert result["sectors"][0]["sector"] == "Financial Services"
    assert result["holdings"][0]["name"] == "HDFC Bank"

    empty = db_prov.fetch_insights(isin="", fund_name="")
    assert empty["sectors"] == []

    # ISIN miss → secondary ILIKE name lookup
    conn2 = FakeDbConn()
    monkeypatch.setattr(db, "connect", lambda **kw: conn2)
    conn2.queue_result(fetchone=None)  # ISIN miss
    conn2.queue_result(fetchone=(
        "INF179K01BE2",
        119062,
        "HDFC Top 100 Fund",
        34000.0,
        0.90,
        "HIGH",
        "1%",
        json.dumps([{"sector": "Banks", "value": 40.0}]),
        json.dumps([{"name": "HDFC Bank", "pct": 10.0}]),
        "AMFI Official Disclosure",
        now,
    ))
    by_name = db_prov.fetch_insights(isin="UNKNOWNISIN", fund_name="HDFC Top 100 Fund")
    assert by_name["risk"] == "HIGH"
    assert "HDFC" in by_name["holdings"][0]["name"]
