"""
Unit tests for AMFI ingest helpers (no DB / network required).
"""

import pytest

from shared.services.amfi_ingest import (
    AmfiFetchError,
    _amc_match_terms,
    _normalize_category,
    _portfolio_as_of,
    fetch_amfi_master_schemes,
)


def test_normalize_large_and_mid_cap_not_mid_cap():
    assert (
        _normalize_category("Open Ended Schemes", "Mirae Asset Large & Midcap Fund - Direct Plan - Growth")
        == "Large & Mid Cap Fund"
    )
    assert (
        _normalize_category("", "HDFC Large and Mid Cap Fund - Growth")
        == "Large & Mid Cap Fund"
    )


def test_normalize_plain_mid_and_large_cap():
    assert _normalize_category("", "Nippon India Mid Cap Fund") == "Mid Cap Fund"
    assert _normalize_category("", "HDFC Top 100 Fund") == "Large Cap Fund"
    assert _normalize_category("", "Parag Parikh Flexi Cap Fund") == "Flexi Cap Fund"


def test_amc_aliases_parag_ppfas_and_grow():
    assert "ppfas" in [t.lower() for t in _amc_match_terms("Parag Parikh")]
    assert "parag parikh" in [t.lower() for t in _amc_match_terms("PPFAS")]
    assert _amc_match_terms("grow") == ["groww"]
    assert _amc_match_terms("Groww") == ["groww"]


def test_portfolio_as_of_is_previous_month_end():
    as_of = _portfolio_as_of()
    # Must be the last calendar day of some month
    next_day = as_of.fromordinal(as_of.toordinal() + 1)
    assert next_day.day == 1


def test_fetch_amfi_raises_on_network_failure(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    with pytest.raises(AmfiFetchError, match="Failed to fetch"):
        fetch_amfi_master_schemes()
