
"""BSE scrip map and VWAP client."""

from unittest.mock import MagicMock

import pytest

from domains.equity.bse_client import BSEClient


def _mock_response(status_code: int, json_data=None, raise_on_json=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_on_json:
        resp.json.side_effect = ValueError("bad json")
    else:
        resp.json.return_value = json_data
    return resp


class TestBSEClient:
    def test_load_scrip_map_success(self, monkeypatch):
        table = [
            {"scripcd": "500325", "NSEID": "RELIANCE"},
            {"scripcd": "532540", "SYMBOL": "tcs"},
            {"scripcd": "", "NSEID": "SKIP"},
            "not-a-dict",
        ]
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, {"Table": table}),
        )
        client = BSEClient()
        mapping = client._load_scrip_map()
        assert mapping["RELIANCE"] == "500325"
        assert mapping["TCS"] == "532540"

    def test_load_scrip_map_http_failure(self, monkeypatch):
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(503),
        )
        assert BSEClient()._load_scrip_map() == {}

    def test_load_scrip_map_invalid_payload(self, monkeypatch):
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, []),
        )
        assert BSEClient()._load_scrip_map() == {}

    def test_load_scrip_map_request_exception(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("offline")

        monkeypatch.setattr("domains.equity.bse_client.requests.get", boom)
        assert BSEClient()._load_scrip_map() == {}

    def test_resolve_scrip_code(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        assert client.resolve_scrip_code("reliance-eq") == "500325"
        assert client.resolve_scrip_code("UNKNOWN") is None

    def test_get_vwap_success(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, {"WAP": "1,234.56"}),
        )
        assert client.get_vwap("RELIANCE") == 1234.56

    def test_get_vwap_unmapped_symbol(self):
        client = BSEClient()
        client._scrip_map = {}
        assert client.get_vwap("RELIANCE") is None

    def test_resolve_scrip_code_lazy_load(self, monkeypatch):
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, {"Table": [{"scripcd": "500325", "NSEID": "RELIANCE"}]}),
        )
        client = BSEClient()
        assert client.resolve_scrip_code("RELIANCE") == "500325"

    def test_get_vwap_http_failure(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(500),
        )
        assert client.get_vwap("RELIANCE") is None

    def test_get_vwap_invalid_wap_values(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}

        def fake_get(url, **kwargs):
            if "StockTrading" in url:
                return _mock_response(200, {"WAP": "-"})
            return _mock_response(200, {"Table": []})

        monkeypatch.setattr("domains.equity.bse_client.requests.get", fake_get)
        assert client.get_vwap("RELIANCE") is None

    def test_get_vwap_json_exception(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, raise_on_json=True),
        )
        assert client.get_vwap("RELIANCE") is None

class TestBSEClientExtra:
    def test_scrip_map_table_not_list(self, monkeypatch):
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, {"Table": "not-a-list"}),
        )
        assert BSEClient()._load_scrip_map() == {}

    def test_get_vwap_non_dict_json(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, []),
        )
        assert client.get_vwap("RELIANCE") is None

    def test_get_vwap_empty_wap(self, monkeypatch):
        client = BSEClient()
        client._scrip_map = {"RELIANCE": "500325"}
        monkeypatch.setattr(
            "domains.equity.bse_client.requests.get",
            lambda *a, **k: _mock_response(200, {"WAP": ""}),
        )
        assert client.get_vwap("RELIANCE") is None

