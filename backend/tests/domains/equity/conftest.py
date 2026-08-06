
"""Shared fixtures for equity domain tests."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.equity import sessions as eq_sessions
from domains.equity.kite_client import KiteClient
from shared.identity import Caller
from shared.services.cache import MARKET_CACHE

CALLER = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")


@pytest.fixture(autouse=True)
def _clear_equity_caches():
    MARKET_CACHE.clear()
    eq_sessions.clear_all()
    yield
    MARKET_CACHE.clear()
    eq_sessions.clear_all()




def _holdings_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "symbol": "RELIANCE",
            "quantity": 10.0,
            "avg_price": 1000.0,
            "ltp": 1200.0,
            "current_value": 12000.0,
            "invested": 10000.0,
            "unrealized_pnl": 2000.0,
            "pnl_pct": 20.0,
            "day_change": 50.0,
            "day_change_pct": 0.5,
            "exchange": "NSE",
            "name": "Reliance",
            "isin": "INE002A01018",
            "broker": "zerodha",
            "sector": "Energy",
            "industry": "Oil & Gas",
        },
        {
            "symbol": "TCS",
            "quantity": 5.0,
            "avg_price": 3000.0,
            "ltp": 3500.0,
            "current_value": 17500.0,
            "invested": 15000.0,
            "unrealized_pnl": 2500.0,
            "pnl_pct": 16.67,
            "day_change": 20.0,
            "day_change_pct": 0.3,
            "exchange": "NSE",
            "name": "TCS",
            "isin": "INE467B01029",
            "broker": "zerodha",
            "sector": "Information Technology",
            "industry": "IT Services",
        },
    ])


@pytest.fixture
def equity_session():
    from domains.equity.models import EquityPortfolio

    sid = "eq_test_session_001"
    p = EquityPortfolio(_holdings_df(), pd.DataFrame(), source="zerodha")
    eq_sessions._SESSIONS[sid] = {
        "portfolio": p,
        "owner": None,
        "created_at": datetime.now(),
        "last_accessed": datetime.now(),
    }
    return sid, p


def _mock_response(status_code: int, json_data=None, raise_on_json=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_on_json:
        resp.json.side_effect = ValueError("bad json")
    else:
        resp.json.return_value = json_data
    return resp


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


@pytest.fixture
def kite_client(monkeypatch):
    fake_module = MagicMock()
    fake_module.KiteConnect = _FakeKite
    monkeypatch.setitem(sys.modules, "kiteconnect", fake_module)
    return KiteClient(api_key="test_key", api_secret="test_secret")
