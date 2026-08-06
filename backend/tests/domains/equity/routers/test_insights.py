"""Equity insights router."""


from __future__ import annotations

import io
import time
from datetime import datetime

import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse

from domains.equity import sessions as eq_sessions
from domains.equity.stock_analyzer import UnknownSymbol
from shared.identity import Caller, identity_scope

CALLER = Caller(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")


def _holdings_df():
    return pd.DataFrame([
        {
            "symbol": "RELIANCE", "quantity": 10.0, "avg_price": 1000.0, "ltp": 1200.0,
            "current_value": 12000.0, "invested": 10000.0, "unrealized_pnl": 2000.0,
            "pnl_pct": 20.0, "day_change": 50.0, "day_change_pct": 0.5,
            "exchange": "NSE", "name": "Reliance", "isin": "INE002A01018", "broker": "zerodha",
            "sector": "Energy", "industry": "Oil & Gas",
        },
        {
            "symbol": "TCS", "quantity": 5.0, "avg_price": 3000.0, "ltp": 3500.0,
            "current_value": 17500.0, "invested": 15000.0, "unrealized_pnl": 2500.0,
            "pnl_pct": 16.67, "day_change": 20.0, "day_change_pct": 0.3,
            "exchange": "NSE", "name": "TCS", "isin": "INE467B01029", "broker": "zerodha",
            "sector": "Information Technology", "industry": "IT Services",
        },
    ])


from domains.equity.routers import insights

class TestInsightsRouter:
    def test_get_insights(self, equity_session):
        sid, _ = equity_session
        resp = insights.get_insights(sid)
        assert resp.status_code == 200
        assert b"score" in resp.body or b"nudges" in resp.body or b"insights" in resp.body

