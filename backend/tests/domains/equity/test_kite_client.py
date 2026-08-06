
"""Zerodha Kite Connect client."""

import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.equity.kite_client import KiteClient, holdings_to_dataframe


class _FakeKite:
    def __init__(self, api_key):
        self.api_key = api_key
        self.access_token = None

    def login_url(self):
        return "https://kite.example/login?api_key=test"

    def generate_session(self, request_token, api_secret):
        if request_token == "bad":
            raise RuntimeError("invalid token")
        return {"access_token": "tok123", "user_id": "AB1234"}

    def set_access_token(self, token):
        self.access_token = token

    def holdings(self):
        if self.access_token == "fail":
            raise RuntimeError("holdings down")
        return [
            {
                "tradingsymbol": "RELIANCE",
                "isin": "INE002A01018",
                "quantity": 10,
                "t1_quantity": 0,
                "average_price": 1000.0,
                "last_price": 1200.0,
                "pnl": 2000.0,
                "day_change": 50.0,
                "day_change_percentage": 0.5,
                "exchange": "NSE",
            },
            {"tradingsymbol": "ZERO", "quantity": 0, "t1_quantity": 0},
        ]

    def positions(self):
        if self.access_token == "fail":
            raise RuntimeError("positions down")
        return {"net": [], "day": []}

    def profile(self):
        if self.access_token == "fail":
            raise RuntimeError("profile down")
        return {"user_name": "Test User", "user_id": "AB1234"}

class TestKiteClient:
    def test_get_login_url_without_state(self, kite_client):
        assert kite_client.get_login_url() == "https://kite.example/login?api_key=test"

    def test_get_login_url_with_state(self, kite_client):
        url = kite_client.get_login_url(state="csrf-token")
        assert "state=csrf-token" in url

    def test_exchange_token_success(self, kite_client):
        session = kite_client.exchange_token("good-token")
        assert session["access_token"] == "tok123"

    def test_exchange_token_failure(self, kite_client):
        with pytest.raises(ValueError, match="Zerodha authentication failed"):
            kite_client.exchange_token("bad")

    def test_set_access_token(self, kite_client):
        kite_client.set_access_token("tok123")
        assert kite_client._get_kite().access_token == "tok123"

    def test_fetch_holdings_success(self, kite_client):
        rows = kite_client.fetch_holdings("tok123")
        assert len(rows) == 2

    def test_fetch_holdings_failure(self, kite_client):
        with pytest.raises(ValueError, match="Could not fetch holdings"):
            kite_client.fetch_holdings("fail")

    def test_fetch_positions_success(self, kite_client):
        assert kite_client.fetch_positions("tok123") == {"net": [], "day": []}

    def test_fetch_positions_failure(self, kite_client):
        with pytest.raises(ValueError, match="Could not fetch positions"):
            kite_client.fetch_positions("fail")

    def test_fetch_profile_success(self, kite_client):
        assert kite_client.fetch_profile("tok123")["user_name"] == "Test User"

    def test_fetch_profile_failure_returns_empty(self, kite_client):
        assert kite_client.fetch_profile("fail") == {}

    def test_import_error_when_kiteconnect_missing(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "kiteconnect", raising=False)
        client = KiteClient("k", "s")
        client._kite = None

        def fake_import(name, *args, **kwargs):
            if name == "kiteconnect":
                raise ImportError("no kiteconnect")
            return __import__(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        with pytest.raises(RuntimeError, match="kiteconnect is not installed"):
            client._get_kite()

class TestHoldingsToDataframe:
    def test_empty(self):
        assert holdings_to_dataframe([]).empty

    def test_normalizes_rows(self):
        df = holdings_to_dataframe([
            {
                "tradingsymbol": "reliance",
                "isin": "INE002A01018",
                "quantity": 10,
                "t1_quantity": 2,
                "average_price": 100.0,
                "last_price": 120.0,
                "pnl": 220.0,
                "day_change": 1.0,
                "day_change_percentage": 0.5,
                "exchange": "NSE",
            }
        ])
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "RELIANCE"
        assert df.iloc[0]["quantity"] == 12.0
        assert df.iloc[0]["pnl_pct"] == pytest.approx(18.33, abs=0.01)

