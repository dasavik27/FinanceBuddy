
"""NSE master symbol list and equity quote API client."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from domains.equity.nse_client import NSEClient


def test_nse_client_master_search_and_quote(monkeypatch):
    client = NSEClient()
    csv_text = "SYMBOL,NAME OF COMPANY, ISIN NUMBER, SERIES\nRELIANCE,Reliance Industries,INE002A01018,EQ\n"
    monkeypatch.setattr(
        "domains.equity.nse_client.requests.get",
        lambda url, **k: MagicMock(status_code=200, text=csv_text),
    )
    master = client.load_master_symbols()
    assert any(m["symbol"] == "RELIANCE" for m in master)
    assert client.is_listed("RELIANCE")
    assert client.symbol_for_isin("INE002A01018") == "RELIANCE"
    assert client.name_for("RELIANCE")
    hits = client.search("REL", limit=5)
    assert hits

    client.QUOTE_API_ENABLED = True
    monkeypatch.setattr(client, "_refresh_session_cookies", lambda: None)
    monkeypatch.setattr(
        client._session,
        "get",
        lambda url, **k: MagicMock(
            status_code=200,
            json=lambda: {
                "info": {"companyName": "Reliance", "isin": "INE002A01018"},
                "priceInfo": {"lastPrice": 2500, "previousClose": 2480, "change": 20, "pChange": 0.8},
                "metadata": {"pdSymbolPe": 25.5, "series": "EQ"},
                "securityInfo": {"issuedSize": 1000000000},
                "tradeInfo": {"deliveryPosition": {"deliveryToTradedQuantity": 45.0}},
            },
        ),
    )
    quote = client.get_equity_quote("RELIANCE")
    assert quote["current_price"] == 2500
    assert quote["delivery_pct"] == 45.0

def test_nse_client_fallback_and_failures(monkeypatch):
    client = NSEClient()
    monkeypatch.setattr(
        "domains.equity.nse_client.requests.get",
        MagicMock(side_effect=RuntimeError("network")),
    )
    fallback = client.load_master_symbols()
    assert len(fallback) >= 10
    assert client.search("") == []

def test_nse_client_search_and_quote_errors(monkeypatch):
    client = NSEClient()
    client._master = [{"symbol": "RELIANCE", "name": "Reliance", "isin": "INE002A01018"}]

    assert client.is_listed("MISSING") is False
    assert client.symbol_for_isin("BAD") is None
    assert client.name_for("MISSING") is None

    client.QUOTE_API_ENABLED = True
    monkeypatch.setattr(client, "_refresh_session_cookies", lambda: None)
    monkeypatch.setattr(
        client._session, "get",
        lambda url, **k: MagicMock(status_code=403, json=lambda: {}),
    )
    assert client.get_equity_quote("RELIANCE") is None

    monkeypatch.setattr(
        client._session, "get",
        lambda url, **k: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    assert client.get_equity_quote("RELIANCE") is None

def test_nse_client_empty_index_and_cookies(monkeypatch):
    client = NSEClient()
    monkeypatch.setattr(client, "load_master_symbols", lambda: [])
    assert client.is_listed("ANY") is True
    assert client.symbol_for_isin("") is None
    assert client.symbol_for_isin(None) is None

    client._cookie_timestamp = 0
    monkeypatch.setattr(
        client._session, "get",
        lambda url, **k: (_ for _ in ()).throw(RuntimeError("cookie fail")),
    )
    client._refresh_session_cookies()

    client._cookie_timestamp = 0
    ok = MagicMock(status_code=200)
    monkeypatch.setattr(client._session, "get", lambda url, **k: ok)
    client._refresh_session_cookies()
    assert client._cookie_timestamp > 0

    client._cookie_timestamp = datetime.now().timestamp()
    client._refresh_session_cookies()

def test_nse_client_search_branches(monkeypatch):
    client = NSEClient()
    master = [
        {"symbol": "RELIANCE", "name": "Reliance Industries", "isin": "INE002A01018"},
        {"symbol": "RELINFRA", "name": "Reliance Infrastructure", "isin": "INEXXX"},
        {"symbol": "TCS", "name": "Tata Consultancy", "isin": "INE467B01029"},
    ]
    monkeypatch.setattr(client, "load_master_symbols", lambda: master)
    client._name_index = {}
    client._isin_index = {}
    exact = client.search("RELIANCE", limit=1)
    assert len(exact) == 1
    assert exact[0]["symbol"] == "RELIANCE"
    by_name = client.search("INFRASTRUCTURE", limit=5)
    assert any(h["symbol"] == "RELINFRA" for h in by_name)

def test_nse_client_parse_quote_bad_numbers():
    client = NSEClient()
    data = {
        "info": {"companyName": "X"},
        "priceInfo": {"lastPrice": 100, "previousClose": 99, "vwap": "bad", "weekHighLow": {}},
        "metadata": {"pdSymbolPe": "n/a", "pdSectorPe": {}},
        "securityInfo": {"issuedSize": "not-a-number"},
        "tradeInfo": {"deliveryPosition": {"deliveryToTradedQuantity": "oops"}},
    }
    out = client._parse_nse_quote("X", data)
    assert out["pe_ratio"] is None
    assert out["sector_pe"] is None
    assert out["market_cap_cr"] is None
    assert out["vwap"] is None
    assert out["delivery_pct"] is None

def test_nse_client_quote_disabled():
    client = NSEClient()
    assert client.get_equity_quote("RELIANCE") is None

