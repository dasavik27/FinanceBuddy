"""Unit tests for shared/services/providers/mfapi.py."""

from unittest.mock import MagicMock

import pytest

from shared.services.providers import mfapi


def test_mfapi_nav_series_and_meta(monkeypatch):
    provider = mfapi.MFApiProvider()

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    nav_json = {
        "meta": {
            "scheme_name": "Test Fund",
            "fund_house": "Test AMC",
            "scheme_type": "Open Ended",
            "scheme_category": "Large Cap",
        },
        "data": [
            {"date": "01-01-2026", "nav": "100.50"},
            {"date": "02-01-2026", "nav": "101.20"},
            {"date": "02-01-2026", "nav": "101.20"},
            {"date": "invalid-date", "nav": "102.00"},
        ],
    }
    monkeypatch.setattr(provider.session, "get", lambda *a, **k: FakeResp(nav_json))

    s = provider.fetch_nav_series("119062", days=30)
    assert len(s) == 2
    assert s.iloc[-1] == 101.20

    meta = provider.fetch_fund_meta("119062")
    assert meta["scheme_name"] == "Test Fund"
    assert meta["fund_house"] == "Test AMC"

    monkeypatch.setattr(
        provider.session,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("network down")),
    )
    s_err = provider.fetch_nav_series("bad", days=30)
    assert s_err.empty
    meta_err = provider.fetch_fund_meta("bad")
    assert meta_err == {}


def test_mfapi_empty_nav_series(monkeypatch):
    provider = mfapi.MFApiProvider()
    monkeypatch.setattr(
        provider.session,
        "get",
        lambda url, timeout=10: MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {"data": [{"date": "bad-date", "nav": "nan"}]},
        ),
    )
    assert provider.fetch_nav_series("123456", days=30).empty

def test_mfapi_search_error_and_empty_nav(monkeypatch):
    from shared.services.providers.mfapi import MFApiProvider

    provider = MFApiProvider()
    monkeypatch.setattr(provider.session, "get", MagicMock(side_effect=RuntimeError("down")))
    assert provider.search_funds("hdfc") == []

