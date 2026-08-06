"""Zerodha tax P&L broker parser."""

import io

import pandas as pd
import pytest
from unittest.mock import MagicMock

from domains.tax_expert import broker_parser


def test_parse_zerodha_tax_pnl_empty_or_missing_sheets():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame([["Other Sheet"]]).to_excel(writer, sheet_name="Other", index=False)
    trades = broker_parser.parse_zerodha_tax_pnl(buffer.getvalue())
    assert trades == []

def test_parse_zerodha_tax_pnl_extracts_trades():
    # Construct an in-memory Excel workbook simulating Zerodha P&L
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_equity = pd.DataFrame([
            ["Header Row", "Col1", "Col2", "Col3", "Col4", "Col5"],
            ["Short Term Trades", "", "", "", "", ""],
            ["RELIANCE", "10", "10000", "12000", "2000", "0"],
            ["TCS", "5", "15000", "14000", "-1000", "0"],
            ["Long Term Trades", "", "", "", "", ""],
            ["INFY", "20", "20000", "30000", "10000", "0"],
            ["Debt (Purchased on/after 2023-04-01)", "", "", "", "", ""],
            ["HDFC DEBT", "100", "100000", "110000", "10000", "0"],
        ])
        df_equity.to_excel(writer, sheet_name="Equity and Non Equity", index=False, header=False)

    raw_bytes = buffer.getvalue()
    trades = broker_parser.parse_zerodha_tax_pnl(raw_bytes)

    assert len(trades) == 4
    stcg = [t for t in trades if t["type"] == "STCG"]
    ltcg = [t for t in trades if t["type"] == "LTCG"]
    slab = [t for t in trades if t["slab_taxed"]]

    assert len(stcg) == 2
    assert stcg[0]["security"] == "RELIANCE"
    assert stcg[0]["gain"] == 2000.0

    assert len(ltcg) == 1
    assert ltcg[0]["security"] == "INFY"
    assert ltcg[0]["gain"] == 10000.0

    assert len(slab) == 1
    assert slab[0]["security"] == "HDFC DEBT"
    assert slab[0]["gain"] == 10000.0

def test_broker_parser_non_equity_and_bad_row(monkeypatch):
    from domains.tax_expert import broker_parser

    sheet_df = pd.DataFrame([
        ["Non Equity Trades"],
        ["Symbol", "Qty", "Buy", "Sell", "PnL"],
        ["", "", "", "", ""],
        ["GOLD", "5", "bad", "300", "50"],
        ["Short Term Trades"],
        ["Symbol", "Qty", "Buy", "Sell", "PnL"],
        ["TCS", "10", "1000", "1200", "200"],
    ])

    class FakeXLS:
        sheet_names = ["Equity and Non Equity"]

    monkeypatch.setattr(pd, "ExcelFile", lambda raw: FakeXLS())
    monkeypatch.setattr(pd, "read_excel", lambda xls, sheet_name: sheet_df)
    trades = broker_parser.parse_zerodha_tax_pnl(b"fake")
    assert any(t["security"] == "TCS" for t in trades)

def test_broker_parser_zerodha_sections(monkeypatch):
    from domains.tax_expert import broker_parser

    sheet_df = pd.DataFrame([
        ["Short Term Trades"],
        ["Symbol", "Qty", "Buy", "Sell", "PnL"],
        ["RELIANCE", "10", "1000", "1200", "200"],
    ])

    class FakeXLS:
        sheet_names = ["Equity and Non Equity"]

    monkeypatch.setattr(pd, "ExcelFile", lambda raw: FakeXLS())
    monkeypatch.setattr(pd, "read_excel", lambda xls, sheet_name: sheet_df)
    trades = broker_parser.parse_zerodha_tax_pnl(b"fake")
    assert trades[0]["security"] == "RELIANCE"

