"""
test_amfi_ingest_full_coverage.py

Full unit test coverage for shared.services.amfi_ingest:
- Helper functions: _portfolio_as_of, _amc_match_terms, _invalidate_market_caches
- Categorization & AMC extraction: _normalize_category, _extract_amc_name
- Feed fetching & error handling: fetch_amfi_master_schemes, AmfiFetchError
- Sync status DB queries: get_sync_status
"""

from unittest.mock import MagicMock
import pytest

from shared.services import amfi_ingest


def test_portfolio_as_of():
    dt = amfi_ingest._portfolio_as_of()
    assert dt is not None
    assert dt.day >= 28


def test_amc_match_terms():
    terms_ppfas = amfi_ingest._amc_match_terms("ppfas")
    assert "parag parikh" in terms_ppfas or "ppfas" in terms_ppfas

    terms_empty = amfi_ingest._amc_match_terms("")
    assert terms_empty == []


def test_invalidate_market_caches(monkeypatch):
    invalidated = []
    monkeypatch.setattr(amfi_ingest.MarketCache, "invalidate_all", lambda: invalidated.append(True))
    amfi_ingest._invalidate_market_caches()
    assert len(invalidated) >= 1


def test_normalize_category():
    assert amfi_ingest._normalize_category("Open Ended Equity", "Nippon Small Cap Fund") == "Small Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Equity", "Mirae Asset Large & Mid Cap") == "Large & Mid Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Equity", "Parag Parikh Flexi Cap Fund") == "Flexi Cap Fund"
    assert amfi_ingest._normalize_category("Open Ended Equity", "Mirae Asset ELSS Tax Saver") == "ELSS / Tax Saver"
    assert amfi_ingest._normalize_category("Open Ended Debt", "HDFC Liquid Fund") == "Debt / Liquid Fund"


def test_extract_amc_name():
    assert "HDFC" in amfi_ingest._extract_amc_name("HDFC Top 100 Fund", "")
    assert "SBI" in amfi_ingest._extract_amc_name("SBI Bluechip Fund", "")
    assert "Custom AMC" in amfi_ingest._extract_amc_name("Some Fund", "Custom AMC Mutual Fund")


def test_fetch_amfi_master_schemes_success(monkeypatch):
    mock_nav_text = (
        "Open Ended Schemes ( Equity Scheme - Large Cap Fund )\n"
        "HDFC Mutual Fund\n"
        "119551;INF209K01157;INF209K01165;HDFC Top 100 Fund - Direct Plan;340.50;05-Aug-2026\n"
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_nav_text.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    monkeypatch.setattr(amfi_ingest.urllib.request, "urlopen", lambda req, timeout=20: mock_resp)

    schemes = amfi_ingest.fetch_amfi_master_schemes()
    assert len(schemes) == 1
    assert schemes[0]["scheme_code"] == "119551"
    assert schemes[0]["isin"] == "INF209K01157"


def test_fetch_amfi_master_schemes_error(monkeypatch):
    monkeypatch.setattr(amfi_ingest.urllib.request, "urlopen", MagicMock(side_effect=Exception("Network down")))
    with pytest.raises(amfi_ingest.AmfiFetchError):
        amfi_ingest.fetch_amfi_master_schemes()


def test_get_sync_status(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.side_effect = [(150,), None]
    mock_conn.execute.return_value.fetchall.return_value = []
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_conn
    monkeypatch.setattr(amfi_ingest.db, "connect", lambda: mock_ctx)

    status = amfi_ingest.get_sync_status()
    assert status["total_schemes"] == 150
