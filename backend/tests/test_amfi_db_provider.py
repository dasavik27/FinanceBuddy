"""
tests/test_amfi_db_provider.py
Unit tests for Tier 1 AMFIDatabaseProvider, multi-tier discovery cascade, and ingestion engine.
"""

import pytest
from domains.mutual_funds.portfolio_discovery import fetch_live_portfolio
from shared.services.amfi_ingest import (
    get_sync_status,
    get_synced_amc_list,
    purge_snapshots,
    search_synced_schemes,
    trigger_amfi_sync,
)
from shared.services.providers.amfi_db import AMFIDatabaseProvider
from tests.conftest import requires_db


@requires_db
def test_amfi_db_provider_seeded_isin(db_schema):
    """Verify that AMFIDatabaseProvider returns 100% accurate official disclosures for seeded funds."""
    provider = AMFIDatabaseProvider()
    insights = provider.fetch_insights(isin="INF879O01027", fund_name="Parag Parikh Flexi Cap Fund", category="Flexi Cap Fund")
    
    assert insights["source"] is not None
    assert "AMFI Official Disclosure" in insights["source"]
    assert len(insights["holdings"]) == 10
    assert any("HDFC Bank" in h["name"] for h in insights["holdings"])
    assert any("ITC" in h["name"] for h in insights["holdings"])
    assert len(insights["sectors"]) >= 5
    assert any(s["sector"] == "Financial Services" for s in insights["sectors"])
    assert "₹78,450 Cr" in insights["aum"]
    assert insights["risk"] == "VERY HIGH"
    assert insights["aum_fallback"] is False
    assert insights["risk_fallback"] is False


@requires_db
def test_amfi_db_provider_name_fallback_matching(db_schema):
    """Verify that AMFIDatabaseProvider resolves schemes by name if ISIN is omitted."""
    provider = AMFIDatabaseProvider()
    insights = provider.fetch_insights(isin="", fund_name="HDFC Top 100 Fund", category="Large Cap Fund")
    
    assert insights["source"] is not None
    assert len(insights["holdings"]) == 10
    assert any("HDFC Bank" in h["name"] for h in insights["holdings"])
    assert "₹34,890 Cr" in insights["aum"]
    assert insights["aum_fallback"] is False


@requires_db
def test_fetch_live_portfolio_tier1_cascade(db_schema):
    """Verify fetch_live_portfolio seamlessly uses Tier 1 AMFI DB as primary source."""
    result = fetch_live_portfolio(
        isin="INF109K012R0",
        category="Large Cap Fund",
        fund_name="ICICI Prudential Bluechip Fund",
        refresh=True,
    )
    assert result["source"] is not None
    assert "AMFI" in result["source"]
    assert result["aum"] == "₹58,200 Cr"
    assert result["aum_fallback"] is False
    assert len(result["holdings"]) == 10
    assert len(result["sectors"]) >= 5


def test_fetch_live_portfolio_unseeded_fallback_heuristics():
    """Verify fetch_live_portfolio falls back to deterministic heuristics for unseeded funds."""
    result = fetch_live_portfolio(
        isin="UNKNOWN_ISIN_999",
        category="Small Cap Fund",
        fund_name="Random Unindexed Fund",
        refresh=True,
    )
    assert result["aum_fallback"] is True
    assert result["risk_fallback"] is True
    assert result["risk"] is not None
    assert result["aum"] is not None


@requires_db
def test_amfi_sync_and_search(db_schema):
    """Verify status query, scheme search, selective sync, and purge operations."""
    status = get_sync_status()
    assert status["total_schemes"] >= 8
    assert "2026" in status["latest_portfolio_month"]

    search_res = search_synced_schemes(query="Parag", limit=10, offset=0)
    assert search_res["total"] >= 1
    assert any("Parag Parikh" in s["scheme_name"] for s in search_res["schemes"])

    # Test selective sync with top5 preset
    sync_res = trigger_amfi_sync(admin_email="admin@financebuddy.app", preset="top5")
    assert sync_res["status"] == "completed"
    assert sync_res["schemes_updated"] >= 1
    assert sync_res["duration_seconds"] >= 0.0

    # Test distinct AMC list
    amcs = get_synced_amc_list()
    assert len(amcs) >= 1

    # Test purge by AMC
    purge_res = purge_snapshots(amc="Quant", purge_all=False, admin_email="admin@financebuddy.app")
    assert purge_res["status"] == "success"

    # Test purge all
    purge_all_res = purge_snapshots(purge_all=True, admin_email="admin@financebuddy.app")
    assert purge_all_res["status"] == "success"

