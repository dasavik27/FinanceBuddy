"""Unit tests for shared/services/providers/factory.py."""

import pytest

from shared.services.providers import factory, mfapi


def test_provider_factory_singleton():
    p1 = factory.get_provider()
    p2 = factory.get_provider()
    assert p1 is p2
    assert isinstance(p1, mfapi.MFApiProvider)


def test_provider_factory_unknown_name_fallback(monkeypatch):
    factory._PROVIDER_INSTANCE = None
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "unknown_provider")
    p = factory.get_provider()
    assert p is not None
    factory._PROVIDER_INSTANCE = None
