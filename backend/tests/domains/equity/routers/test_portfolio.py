"""Equity portfolio router."""


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


from domains.equity.routers import portfolio

class TestPortfolioRouter:
    def test_parse_requires_auth(self):
        f = UploadFile(filename="holdings.csv", file=io.BytesIO(b"a,b\n"))
        with identity_scope(None), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=f, tradebook=None)
        assert exc.value.status_code == 401

    def test_parse_upload_too_large(self, monkeypatch):
        from domains.equity.parser import UploadTooLarge

        monkeypatch.setattr(
            portfolio, "read_upload", lambda stream, name: (_ for _ in ()).throw(UploadTooLarge("too big"))
        )
        f = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=f, tradebook=None)
        assert exc.value.status_code == 422

    def test_parse_empty_holdings(self, monkeypatch):
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: b"csv")
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (pd.DataFrame(), None)
        )
        f = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=f, tradebook=None)
        assert exc.value.status_code == 422

    def test_parse_success(self, monkeypatch):
        df = _holdings_df()
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: b"csv")
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (df, None)
        )
        monkeypatch.setattr(eq_sessions, "create_session", lambda *a, **k: "new_sid")
        f = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        with identity_scope(CALLER):
            result = portfolio.parse_equity_csv(file=f, tradebook=None)
        assert result["session_id"] == "new_sid"
        assert result["stock_count"] == len(df)

    def test_kite_login_url_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_login_url()
        assert exc.value.status_code == 400

    def test_kite_login_url_success(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        with identity_scope(CALLER):
            result = portfolio.kite_login_url()
        assert "login_url" in result
        assert "state" in result

    def test_kite_connect_bad_state(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="tok", state="wrong-state")
        assert exc.value.status_code == 400

    def test_kite_connect_success(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        monkeypatch.setattr(eq_sessions, "create_session", lambda *a, **k: "kite_sid")

        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
            result = portfolio.kite_connect(
                request_token="good-token", state=login["state"]
            )
        assert result["session_id"] == "kite_sid"
        assert result["broker"] == "zerodha_kite"

    def test_kite_connect_token_exchange_failure(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="bad", state=login["state"])
        assert exc.value.status_code == 400

    def test_kite_connect_holdings_failure(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)

        original_fetch = kite_client.fetch_holdings

        def fail_fetch(token):
            if token == "tok123":
                raise ValueError("holdings down")
            return original_fetch(token)

        monkeypatch.setattr(kite_client, "fetch_holdings", fail_fetch)

        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="good-token", state=login["state"])
        assert exc.value.status_code == 502

    def test_kite_state_expired(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        portfolio._kite_states[login["state"]] = (CALLER.user_id, time.time() - 1)
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="good-token", state=login["state"])
        assert exc.value.status_code == 400

    def test_sync_equity(self, equity_session, monkeypatch):
        sid, p = equity_session
        monkeypatch.setattr(p, "update_live_prices", lambda: None)
        result = portfolio.sync_equity(sid)
        assert result["status"] == "ok"
        assert result["stock_count"] == len(p.df_holdings)

class TestPortfolioRouterExtra:
    def test_parse_with_tradebook(self, monkeypatch):
        df = _holdings_df()
        trades = pd.DataFrame([{
            "date": pd.Timestamp("2025-01-01"), "symbol": "RELIANCE",
            "type": "BUY", "quantity": 1, "price": 100.0, "amount": 100.0,
        }])
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: b"raw")
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (df, None)
        )
        monkeypatch.setattr(
            portfolio, "parse_tradebook_csv", lambda raw, filename: (trades, None)
        )
        monkeypatch.setattr(eq_sessions, "create_session", lambda *a, **k: "sid-trades")
        holdings_file = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        tradebook_file = UploadFile(filename="trades.csv", file=io.BytesIO(b"y"))
        with identity_scope(CALLER):
            result = portfolio.parse_equity_csv(file=holdings_file, tradebook=tradebook_file)
        assert result["has_tradebook"] is True

    def test_parse_holdings_error(self, monkeypatch):
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: b"raw")
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (pd.DataFrame(), "bad csv")
        )
        f = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=f, tradebook=None)
        assert exc.value.status_code == 422

    def test_parse_tradebook_upload_error(self, monkeypatch):
        from domains.equity.parser import UploadTooLarge

        df = _holdings_df()
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: (
            (_ for _ in ()).throw(UploadTooLarge("too big")) if "trade" in name else b"raw"
        ))
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (df, None)
        )
        holdings_file = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        tradebook_file = UploadFile(filename="tradebook.csv", file=io.BytesIO(b"y"))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=holdings_file, tradebook=tradebook_file)
        assert "Tradebook" in exc.value.detail

    def test_kite_login_url_build_failure(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        monkeypatch.setattr(
            kite_client, "get_login_url",
            lambda state=None: (_ for _ in ()).throw(RuntimeError("kite down")),
        )
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_login_url()
        assert exc.value.status_code == 502

    def test_kite_connect_no_access_token(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        monkeypatch.setattr(
            kite_client, "exchange_token", lambda token: {"access_token": ""},
        )
        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="good-token", state=login["state"])
        assert exc.value.status_code == 400

    def test_kite_connect_empty_holdings(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        monkeypatch.setattr(kite_client, "fetch_holdings", lambda token: [])
        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.kite_connect(request_token="good-token", state=login["state"])
        assert exc.value.status_code == 422

    def test_kite_state_sweep(self, monkeypatch, kite_client):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setattr(portfolio, "_get_kite_client", lambda: kite_client)
        portfolio._kite_states["stale"] = (CALLER.user_id, time.time() - 1)
        with identity_scope(CALLER):
            login = portfolio.kite_login_url()
        assert "state" in login

    def test_get_kite_client_direct(self, monkeypatch):
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.setenv("ZERODHA_API_SECRET", "test_secret")
        client = portfolio._get_kite_client()
        assert client.api_key == "test_key"

    def test_parse_tradebook_parse_error(self, monkeypatch):
        df = _holdings_df()
        monkeypatch.setattr(portfolio, "read_upload", lambda stream, name: b"raw")
        monkeypatch.setattr(
            portfolio, "parse_holdings_csv", lambda raw, filename: (df, None)
        )
        monkeypatch.setattr(
            portfolio, "parse_tradebook_csv", lambda raw, filename: (pd.DataFrame(), "bad tradebook")
        )
        holdings_file = UploadFile(filename="holdings.csv", file=io.BytesIO(b"x"))
        tradebook_file = UploadFile(filename="tradebook.csv", file=io.BytesIO(b"y"))
        with identity_scope(CALLER), pytest.raises(HTTPException) as exc:
            portfolio.parse_equity_csv(file=holdings_file, tradebook=tradebook_file)
        assert "Tradebook" in exc.value.detail

