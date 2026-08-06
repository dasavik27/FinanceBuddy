"""Equity performance router."""


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


from domains.equity.routers import performance

class TestPerformanceRouter:
    def test_empty_holdings(self):
        from domains.equity.models import EquityPortfolio

        sid = "eq_empty_perf"
        eq_sessions._SESSIONS[sid] = {
            "portfolio": EquityPortfolio(pd.DataFrame(), pd.DataFrame()),
            "owner": None,
            "created_at": datetime.now(),
            "last_accessed": datetime.now(),
        }
        resp = performance.get_performance(sid, period="1Y", benchmark="Nifty 50")
        assert resp.status_code == 200
        assert b'"dates":[]' in resp.body.replace(b" ", b"")

    def test_success_with_benchmark(self, equity_session, monkeypatch):
        sid, _ = equity_session
        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        closes = pd.DataFrame(
            {"RELIANCE": [1000, 1010, 1020, 1030, 1040], "TCS": [3000, 3010, 3020, 3030, 3040]},
            index=dates,
        )
        bench = pd.Series([100, 101, 102, 103, 104], index=dates)
        monkeypatch.setattr(performance, "fetch_close_history", lambda symbols, days: closes)
        monkeypatch.setattr(performance, "fetch_benchmark_series", lambda ticker, days: bench)
        resp = performance.get_performance(sid, period="1M", benchmark="Nifty 50")
        assert resp.status_code == 200
        assert b'"portfolio"' in resp.body

    def test_benchmark_fetch_failure_still_returns_portfolio(self, equity_session, monkeypatch):
        sid, _ = equity_session
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        closes = pd.DataFrame({"RELIANCE": [1000, 1010, 1020]}, index=dates)

        def boom(ticker, days):
            raise RuntimeError("bench down")

        monkeypatch.setattr(performance, "fetch_close_history", lambda symbols, days: closes)
        monkeypatch.setattr(performance, "fetch_benchmark_series", boom)
        resp = performance.get_performance(sid, period="1W", benchmark="Nifty 50")
        assert resp.status_code == 200

    def test_upstream_failure_returns_502(self, equity_session, monkeypatch):
        sid, _ = equity_session
        monkeypatch.setattr(
            performance, "fetch_close_history", lambda symbols, days: (_ for _ in ()).throw(RuntimeError("down"))
        )
        resp = performance.get_performance(sid, period="1Y", benchmark="Nifty 50")
        assert resp.status_code == 502

class TestPerformanceRouterExtra:
    def test_empty_history_response(self, equity_session, monkeypatch):
        sid, _ = equity_session
        monkeypatch.setattr(performance, "fetch_close_history", lambda symbols, days: pd.DataFrame())
        resp = performance.get_performance(sid, period="1M", benchmark="Nifty 50")
        assert resp.status_code == 200
        assert b'"dates":[]' in resp.body.replace(b" ", b"")

    def test_history_columns_not_in_holdings(self, equity_session, monkeypatch):
        sid, _ = equity_session
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        closes = pd.DataFrame({"UNKNOWN": [1, 2, 3]}, index=dates)
        monkeypatch.setattr(performance, "fetch_close_history", lambda symbols, days: closes)
        resp = performance.get_performance(sid, period="1W", benchmark="Nifty 50")
        assert resp.status_code == 200
        assert b'"dates":[]' in resp.body.replace(b" ", b"")

