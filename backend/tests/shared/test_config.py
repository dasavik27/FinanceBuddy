"""
test_shared_config_full_coverage.py

Comprehensive unit tests for shared/config.py:
- _get_ttl_from_db & refresh_cache_ttl (DB hit, DB miss, DB exception, env var fallback)
- get_standard_category (Global, Hybrid, Debt, Equity, Other)
- classify_er (None, Low, Moderate, High, unknown category fallback)
"""

from unittest.mock import MagicMock
import pytest

from shared import config


def test_config_get_ttl_from_db(monkeypatch):
    from shared import db

    # 1. DB returns value
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = (120,)
    monkeypatch.setattr(db, "connect", lambda: mock_conn)
    assert config._get_ttl_from_db() == 120


    # 2. DB returns None -> env fallback
    mock_conn.execute.return_value.fetchone.return_value = None
    monkeypatch.setenv("FINANCEBUDDY_CACHE_TTL", "45")
    assert config._get_ttl_from_db() == 45

    # 3. DB raises Exception -> env fallback
    monkeypatch.setattr(db, "connect", MagicMock(side_effect=RuntimeError("DB Down")))
    monkeypatch.setenv("FINANCEBUDDY_CACHE_TTL", "30")
    assert config._get_ttl_from_db() == 30

    # 4. refresh_cache_ttl
    monkeypatch.setattr(config, "_get_ttl_from_db", lambda: 90)
    assert config.refresh_cache_ttl() == 90
    assert config.CACHE_TTL_MINUTES == 90


def test_config_get_standard_category():
    # Global
    assert config.get_standard_category("Motilal Oswal Nasdaq 100") == "Global"
    assert config.get_standard_category("Franklin Asian Equity Fund") == "Equity"
    assert config.get_standard_category("Franklin Templeton US Opportunities") == "Global"

    # Hybrid
    assert config.get_standard_category("ICICI Prudential Balanced Advantage") == "Hybrid"
    assert config.get_standard_category("HDFC Multi Asset Allocator Fund") == "Hybrid"

    # Debt
    assert config.get_standard_category("SBI Liquid Fund") == "Debt"
    assert config.get_standard_category("Nippon India Gilt Securities") == "Debt"

    # Equity
    assert config.get_standard_category("Mirae Asset Large Cap Fund") == "Equity"
    assert config.get_standard_category("Quant Small Cap Fund") == "Equity"
    assert config.get_standard_category("Axis ELSS Tax Saver") == "Equity"

    # Other
    assert config.get_standard_category("Something Unknown") == "Other"


def test_config_classify_er():
    assert config.classify_er(None, "Equity") == "Unknown"

    # Equity (0.50, 1.20)
    assert config.classify_er(0.30, "Equity") == "Low"
    assert config.classify_er(0.80, "Equity") == "Moderate"
    assert config.classify_er(1.50, "Equity") == "High"

    # Unknown category fallback (0.50, 1.20)
    assert config.classify_er(0.40, "Unlisted") == "Low"
    assert config.classify_er(0.90, "Unlisted") == "Moderate"
    assert config.classify_er(1.80, "Unlisted") == "High"
