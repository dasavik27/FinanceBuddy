"""
tests/test_mf_parser_full_coverage.py

Mocked unit tests for domains/mutual_funds/parser.py — no casparser / network required.
"""

from __future__ import annotations

import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.mutual_funds import parser as mf_parser


# ── _get helper ───────────────────────────────────────────────────────────────


class TestGetHelper:
    def test_dict_access(self):
        assert mf_parser._get({"a": 1, "b": None}, "a") == 1
        assert mf_parser._get({"a": None}, "a", "d") == "d"

    def test_object_access(self):
        obj = SimpleNamespace(x=42, y=None)
        assert mf_parser._get(obj, "x") == 42
        assert mf_parser._get(obj, "y", 0) == 0


# ── _estimate_invested FIFO ───────────────────────────────────────────────────


class TestEstimateInvested:
    def test_fifo_buy_sell(self):
        scheme = {
            "transactions": [
                {"date": "2024-01-01", "units": 100, "amount": 10000, "nav": 100},
                {"date": "2024-06-01", "units": -50, "amount": -6000, "nav": 120},
                {"date": "2024-09-01", "units": 20, "amount": 2400, "nav": 120},
            ]
        }
        assert mf_parser._estimate_invested(scheme) == pytest.approx(7400.0)

    def test_impute_amount_from_nav(self):
        scheme = {
            "transactions": [
                {"date": "2024-01-01", "units": 10, "amount": 0, "nav": 50},
            ]
        }
        assert mf_parser._estimate_invested(scheme) == pytest.approx(500.0)

    def test_no_transactions(self):
        assert mf_parser._estimate_invested({}) == 0.0


# ── parse_cas_file ────────────────────────────────────────────────────────────


def _scheme(
    name="HDFC Flexi Cap Fund",
    isin="INF179K01BB2",
    close=100.0,
    open_bal=0.0,
    nav=250.0,
    txs=None,
):
    return {
        "scheme": name,
        "isin": isin,
        "close": close,
        "open": open_bal,
        "valuation": {"nav": nav},
        "transactions": txs or [],
    }


def _folio(schemes, amc="HDFC Mutual Fund"):
    return {"amc": amc, "schemes": schemes}


def _cas_data(folios, statement_period=None):
    if statement_period is None:
        statement_period = SimpleNamespace(from_="01-Apr-2023", to="31-Mar-2024")
    return SimpleNamespace(folios=folios, statement_period=statement_period)


@pytest.fixture
def mock_casparser(monkeypatch):
    mod = MagicMock()
    monkeypatch.setitem(sys.modules, "casparser", mod)
    return mod


@pytest.fixture
def mock_live_navs(monkeypatch):
    monkeypatch.setattr(
        mf_parser,
        "fetch_live_navs",
        lambda: {"INF179K01BB2": 255.0, "INF000000001": 100.0},
    )


@pytest.fixture
def mock_categorization(monkeypatch):
    class CE:
        @staticmethod
        def detect_category(name, raw_cat="", raw_type=""):
            return raw_cat or "Equity"

        @staticmethod
        def detect_amc(name, raw_amc=""):
            return raw_amc or "HDFC"

        @staticmethod
        def detect_plan(name):
            return "Direct"

        @staticmethod
        def detect_cap_type(name, category, raw_cat=""):
            return "Large Cap"

    monkeypatch.setattr(mf_parser, "CategorizationEngine", CE)


class TestParseCasFile:
    def test_casparser_password_error(self, mock_casparser, mock_categorization):
        mock_casparser.read_cas_pdf.side_effect = ValueError("Incorrect password")
        df_h, df_t, df_s, err, partial, period = mf_parser.parse_cas_file(b"pdf", "wrong")
        assert df_h.empty
        assert "CASParser Error" in err
        assert partial is False

    def test_no_folios(self, mock_casparser, mock_categorization):
        mock_casparser.read_cas_pdf.return_value = _cas_data([])
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert "No folios" in err

    def test_empty_folios_attr(self, mock_casparser, mock_categorization):
        data = SimpleNamespace(folios=[])
        mock_casparser.read_cas_pdf.return_value = data
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert "No folios" in err

    def test_failed_folio_extraction(self, mock_casparser, mock_categorization):
        mock_casparser.read_cas_pdf.return_value = {"folios": None}
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert "Failed to extract folios" in err

    def test_success_with_holdings_and_sips(
        self, mock_casparser, mock_live_navs, mock_categorization, monkeypatch
    ):
        txs = [
            {"date": "2024-01-05", "amount": 5000, "units": 20, "nav": 250, "type": "PURCHASE", "balance": 20},
            {"date": "2024-02-05", "amount": 5000, "units": 20, "nav": 250, "type": "SIP", "balance": 40},
        ]
        folios = [_folio([_scheme(txs=txs)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, df_t, df_s, err, partial, period = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert partial is False
        assert period == "01-Apr-2023 to 31-Mar-2024"
        assert len(df_h) == 1
        assert df_h.iloc[0]["Fund"] == "HDFC Flexi Cap Fund"
        assert df_h.iloc[0]["Gain%"] == pytest.approx(
            (df_h.iloc[0]["Gain"] / df_h.iloc[0]["Invested"]) * 100, rel=0.01
        )
        assert len(df_t) == 2
        assert len(df_s) == 1

    def test_partial_statement_flag(self, mock_casparser, mock_live_navs, mock_categorization):
        folios = [_folio([_scheme(open_bal=10.0)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        _, _, _, err, partial, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert partial is True

    def test_balance_from_last_transaction(self, mock_casparser, mock_live_navs, mock_categorization):
        txs = [{"date": "2024-03-01", "amount": 5000, "units": 20, "nav": 250, "type": "PURCHASE", "balance": 15}]
        folios = [_folio([_scheme(close=0, txs=txs)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.iloc[0]["Units"] == pytest.approx(15.0)

    def test_stale_nav_yahoo_fallback(self, mock_casparser, mock_categorization, monkeypatch):
        monkeypatch.setattr(mf_parser, "fetch_live_navs", lambda: {"INF179K01BB2": 250.0})
        yahoo = MagicMock()
        yahoo.fetch_live_nav.return_value = 260.0
        monkeypatch.setattr(
            "shared.services.providers.yahoo.YahooMetadataProvider",
            lambda: yahoo,
        )
        folios = [_folio([_scheme(nav=250.0)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.iloc[0]["NAV"] == pytest.approx(260.0)

    def test_missing_isin_uses_cas_nav(self, mock_casparser, mock_categorization, monkeypatch):
        monkeypatch.setattr(mf_parser, "fetch_live_navs", lambda: (_ for _ in ()).throw(RuntimeError("amfi down")))
        yahoo = MagicMock()
        yahoo.fetch_live_nav.return_value = None
        monkeypatch.setattr(
            "shared.services.providers.yahoo.YahooMetadataProvider",
            lambda: yahoo,
        )
        folios = [_folio([_scheme(isin="UNKNOWN999", nav=123.45)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.iloc[0]["NAV"] == pytest.approx(123.45)

    def test_invested_fallback_when_fifo_zero(self, mock_casparser, mock_live_navs, mock_categorization):
        folios = [_folio([_scheme(close=10, nav=200.0, txs=[])])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.iloc[0]["Invested"] == pytest.approx(2000.0)

    def test_statement_period_variants(self, mock_casparser, mock_live_navs, mock_categorization):
        folios = [_folio([_scheme()])]

        # dict period
        mock_casparser.read_cas_pdf.return_value = _cas_data(
            folios, statement_period={"from": "Jan 2023", "to": "Dec 2023"}
        )
        _, _, _, err, _, period = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert period == "Jan 2023 to Dec 2023"

        # string period
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios, statement_period="FY 2023-24")
        _, _, _, err, _, period = mf_parser.parse_cas_file(b"pdf", "pw")
        assert period == "FY 2023-24"

        # __dict__ fallback
        sp = SimpleNamespace()
        sp.__dict__["from_"] = "A"
        sp.__dict__["to"] = "B"
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios, statement_period=sp)
        _, _, _, err, _, period = mf_parser.parse_cas_file(b"pdf", "pw")
        assert period == "A to B"

    def test_zerodha_shadow_sip_detection(self, mock_casparser, mock_live_navs, mock_categorization):
        txs = [
            {"date": "2024-01-05", "amount": 5000, "units": 20, "nav": 250, "type": "PURCHASE", "balance": 20},
            {"date": "2024-02-05", "amount": 5000, "units": 20, "nav": 250, "type": "TransactionType.PURCHASE", "balance": 40},
            {"date": "2024-03-05", "amount": 5000, "units": 20, "nav": 250, "type": "PURCHASE", "balance": 60},
        ]
        folios = [_folio([_scheme(txs=txs)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        _, df_t, df_s, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        auto = [t for t in df_t["Type"] if "Auto-Detected" in str(t)]
        assert len(auto) == 3
        assert len(df_s) >= 3

    def test_outer_exception(self, mock_casparser, mock_live_navs, mock_categorization, monkeypatch):
        mock_casparser.read_cas_pdf.return_value = _cas_data([_folio([_scheme()])])
        monkeypatch.setattr(mf_parser, "_estimate_invested", lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert df_h.empty
        assert "boom" in err

    def test_yahoo_adapter_exception(self, mock_casparser, mock_categorization, monkeypatch):
        monkeypatch.setattr(mf_parser, "fetch_live_navs", lambda: {"INF179K01BB2": 250.0})
        monkeypatch.setattr(
            "shared.services.providers.yahoo.YahooMetadataProvider",
            lambda: (_ for _ in ()).throw(RuntimeError("yahoo down")),
        )
        folios = [_folio([_scheme(nav=250.0)])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.iloc[0]["NAV"] == pytest.approx(250.0)

    def test_to_f_bad_numeric_and_partial_fifo_sell(self, mock_casparser, mock_live_navs, mock_categorization):
        scheme = _scheme(
            txs=[
                {"date": "2024-01-01", "units": 100, "amount": 10000, "nav": 100, "type": "PURCHASE", "balance": 100},
                {"date": "2024-02-01", "units": -30, "amount": -3600, "nav": 120, "type": "REDEEM", "balance": 70},
            ]
        )
        scheme["open"] = "not-a-number"
        folios = [_folio([scheme])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert len(df_h) == 1

    def test_temp_file_remove_failure_is_swallowed(self, mock_casparser, mock_categorization, monkeypatch):
        mock_casparser.read_cas_pdf.side_effect = ValueError("bad pdf")
        monkeypatch.setattr(mf_parser.os, "remove", lambda p: (_ for _ in ()).throw(OSError("locked")))
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert df_h.empty
        assert "CASParser Error" in err

    def test_fifo_partial_lot_reduction(self):
        scheme = {
            "transactions": [
                {"date": "2024-01-01", "units": 100, "amount": 10000, "nav": 100},
                {"date": "2024-02-01", "units": -30, "amount": -3600, "nav": 120},
            ]
        }
        assert mf_parser._estimate_invested(scheme) == pytest.approx(7000.0)

    def test_zero_balance_skips_holding(self, mock_casparser, mock_live_navs, mock_categorization):
        folios = [_folio([_scheme(close=0, nav=100, txs=[])])]
        mock_casparser.read_cas_pdf.return_value = _cas_data(folios)
        df_h, _, _, err, _, _ = mf_parser.parse_cas_file(b"pdf", "pw")
        assert err is None
        assert df_h.empty


def test_mf_parser_estimate_invested_fifo():
    from domains.mutual_funds import parser as mf_parser

    txs = [
        {"date": "2024-01-01", "units": 10, "amount": 1000},
        {"date": "2024-06-01", "units": -5, "amount": -600},
    ]
    scheme = MagicMock()
    scheme.transactions = txs
    cost = mf_parser._estimate_invested(scheme)
    assert cost >= 0

def test_mf_parser_period_dict_and_partial_sell(monkeypatch):
    import sys
    from domains.mutual_funds import parser as mf_parser

    class PeriodObj:
        def __init__(self):
            self.__dict__ = {"from_": "2024-01-01", "to": "2024-06-30"}

    class FakeData:
        folios = [{
            "schemes": [{
                "scheme": "Test Fund Direct Growth",
                "isin": "INF1234567890",
                "close": 100.0,
                "valuation": {"nav": 100.0},
                "transactions": [],
            }],
        }]
        statement_period = PeriodObj()

    fake_cas = MagicMock(read_cas_pdf=lambda path, pw: FakeData())
    monkeypatch.setitem(sys.modules, "casparser", fake_cas)
    monkeypatch.setattr(mf_parser, "fetch_live_navs", lambda: {})

    _, _, _, err, _, period = mf_parser.parse_cas_file(b"pdf", "pw")
    assert err is None
    assert "2024-01-01" in period

    txs = [{"date": "2024-01-01", "units": 10, "amount": 1000}, {"date": "2024-06-01", "units": -3, "amount": -400}]
    scheme = MagicMock()
    scheme.transactions = txs
    assert mf_parser._estimate_invested(scheme) > 0

