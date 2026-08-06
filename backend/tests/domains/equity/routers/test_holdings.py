"""Equity holdings router."""


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


from domains.equity.routers import holdings

class TestHoldingsRouter:
    def test_invalid_sort_column(self, equity_session):
        sid, _ = equity_session
        with pytest.raises(HTTPException) as exc:
            holdings.get_holdings(sid, sort_by="not_a_column")
        assert exc.value.status_code == 422

    def test_get_holdings_and_pnl(self, equity_session):
        sid, _ = equity_session
        resp_h = holdings.get_holdings(sid, sort_by="current_value", ascending=False)
        assert resp_h.status_code == 200
        body = resp_h.body.decode()
        assert "RELIANCE" in body

        resp_p = holdings.get_pnl(sid)
        assert resp_p.status_code == 200

