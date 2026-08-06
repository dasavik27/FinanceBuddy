"""Equity analyzer router."""


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


from domains.equity.routers import analyzer

class TestAnalyzerRouter:
    def test_market_indices(self, monkeypatch):
        monkeypatch.setattr(
            analyzer, "get_market_indices", lambda: [{"name": "NIFTY 50", "value": 22000.0}]
        )
        assert analyzer.market_indices() == {"indices": [{"name": "NIFTY 50", "value": 22000.0}]}

    def test_search(self, monkeypatch):
        monkeypatch.setattr(analyzer, "search_stocks", lambda q, limit=10: [{"symbol": "TCS"}])
        assert analyzer.search("tcs") == {"results": [{"symbol": "TCS"}]}

    def test_analyze_requires_auth(self):
        with identity_scope(None), pytest.raises(HTTPException) as exc:
            analyzer.analyze("RELIANCE")
        assert exc.value.status_code == 401

    def test_analyze_success(self, monkeypatch):
        monkeypatch.setattr(analyzer, "analyze_stock", lambda sym: {"symbol": sym, "pe": 25.0})
        with identity_scope(CALLER):
            resp = analyzer.analyze("RELIANCE")
        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 200

    def test_analyze_unknown_symbol(self, monkeypatch):
        def boom(sym):
            raise UnknownSymbol(sym)

        monkeypatch.setattr(analyzer, "analyze_stock", boom)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            analyzer.analyze("BADSYM")
        assert exc.value.status_code == 404

    def test_analyze_upstream_failure(self, monkeypatch):
        monkeypatch.setattr(analyzer, "analyze_stock", lambda sym: (_ for _ in ()).throw(RuntimeError("down")))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            analyzer.analyze("RELIANCE")
        assert exc.value.status_code == 502

    def test_corporate_invalid_symbol(self):
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            analyzer.corporate("!!!")
        assert exc.value.status_code == 404

    def test_corporate_success(self, monkeypatch):
        monkeypatch.setattr(analyzer, "is_valid_symbol", lambda s: True)
        monkeypatch.setattr(analyzer.nse_corporate, "corporate_actions", lambda s: [{"type": "dividend"}])
        monkeypatch.setattr(analyzer.nse_corporate, "event_calendar", lambda s: [])
        monkeypatch.setattr(analyzer.nse_corporate, "announcements", lambda s, limit=10: [])
        monkeypatch.setattr(analyzer.nse_corporate, "adjustment_factor", lambda actions: 1.0)
        with identity_scope(CALLER):
            resp = analyzer.corporate("RELIANCE")
        assert resp.status_code == 200

    def test_portfolio_impact_without_session(self, monkeypatch):
        monkeypatch.setattr(
            analyzer,
            "compute_portfolio_impact",
            lambda **kwargs: {"symbol": kwargs["symbol"], "amount": kwargs["amount"]},
        )
        req = analyzer.ImpactRequest(symbol="RELIANCE", amount=5000.0)
        with identity_scope(CALLER):
            resp = analyzer.portfolio_impact(req)
        assert resp.status_code == 200

    def test_portfolio_impact_with_session(self, equity_session, monkeypatch):
        sid, _ = equity_session
        monkeypatch.setattr(
            analyzer,
            "compute_portfolio_impact",
            lambda **kwargs: {"holdings": len(kwargs["current_holdings"])},
        )
        req = analyzer.ImpactRequest(symbol="RELIANCE", amount=5000.0, session_id=sid)
        with identity_scope(CALLER):
            resp = analyzer.portfolio_impact(req)
        assert resp.status_code == 200

    def test_portfolio_impact_unknown_symbol(self, monkeypatch):
        def boom(**kwargs):
            raise UnknownSymbol(kwargs["symbol"])

        monkeypatch.setattr(analyzer, "compute_portfolio_impact", boom)
        req = analyzer.ImpactRequest(symbol="BAD", amount=1000.0)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            analyzer.portfolio_impact(req)
        assert exc.value.status_code == 404

class TestAnalyzerRouterExtra:
    def test_portfolio_impact_upstream_failure(self, monkeypatch):
        monkeypatch.setattr(
            analyzer, "compute_portfolio_impact",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sim fail")),
        )
        req = analyzer.ImpactRequest(symbol="RELIANCE", amount=5000.0)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            analyzer.portfolio_impact(req)
        assert exc.value.status_code == 502

