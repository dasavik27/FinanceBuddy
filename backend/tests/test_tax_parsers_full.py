"""
test_tax_parsers_full.py

Comprehensive tests for Tax Expert domain parsers:
- broker_parser (Zerodha tax P&L excel)
- itr_parser (ITR-1 / ITR-2 / ITR-3 PDF parser & helper extraction utilities)
- ais_parser & ais_schemas (cleaners, column maps, schema validation)
"""

import io
import pandas as pd
import pytest
from unittest.mock import MagicMock

from domains.tax_expert import broker_parser, itr_parser, ais_parser, ais_schemas


# ── 1. Broker Parser Tests (Zerodha Tax P&L) ──────────────────────────────────

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


def test_parse_zerodha_tax_pnl_empty_or_missing_sheets():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame([["Other Sheet"]]).to_excel(writer, sheet_name="Other", index=False)
    trades = broker_parser.parse_zerodha_tax_pnl(buffer.getvalue())
    assert trades == []


# ── 2. ITR Parser Tests ───────────────────────────────────────────────────────

def test_itr_clean_num_formatting():
    assert itr_parser._clean_num("1,23,456") == 123456.0
    assert itr_parser._clean_num("(50,000)") == -50000.0
    assert itr_parser._clean_num("  1000.50 ") == 1000.50
    assert itr_parser._clean_num("") == 0.0
    assert itr_parser._clean_num(None) == 0.0
    assert itr_parser._clean_num("invalid_number") == 0.0


def test_itr_find_value_and_find_str():
    sample_text = """
    Assessment Year: 2025-26
    PAN: ABCDE1234F
    Name: John Doe
    1 Salaries 1,500,000
    Total Income 2,000,000
    """
    pan = itr_parser._find_str(sample_text, r"PAN\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])")
    assert pan == "ABCDE1234F"

    ay = itr_parser._find_str(sample_text, r"Assessment\s+Year[:\s]+(\d{4}-\d{2,4})")
    assert ay == "2025-26"

    val = itr_parser._find_value(sample_text, r"Total Income\s*([\d,]+)")
    assert val == 2000000.0


def test_parse_itr_pdf_structure(monkeypatch):
    sample_page_text = """
    Form ITR-2
    Assessment Year: 2025-26
    PAN: ABCDE1234F
    Name: Test Taxpayer
    Income chargeable under the Head Salaries 1,200,000
    Total Income 1,500,000
    Total Tax Payable 180,000
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = sample_page_text
    mock_pdf.pages = [mock_page]

    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setattr("pdfplumber.open", mock_pdfplumber.open)

    result = itr_parser.parse_itr_pdf(b"%PDF-1.4 mock content")
    assert result["pan"] == "ABCDE1234F"
    assert result["assessment_year"] == "2025-26"
    assert result["itr_type"] == "ITR-2"


# ── 3. AIS Parser & Schema Cleaners ───────────────────────────────────────────

def test_ais_is_blank_and_clean_amount():
    assert ais_parser._is_blank(None) is True
    assert ais_parser._is_blank("") is True
    assert ais_parser._is_blank("   ") is True
    assert ais_parser._is_blank(float("nan")) is True
    assert ais_parser._is_blank("123") is False

    assert ais_parser._clean_amount(None) == 0.0
    assert ais_parser._clean_amount("  ₹ 50,000.00 ") == 50000.0
    assert ais_parser._clean_amount("1,25,000") == 125000.0


def test_ais_col_map_mapping():
    headers = ["Sr No", "Security Name", "Amount", "Amount"]
    cmap = ais_parser._col_map(headers)
    assert cmap["Sr No"] == 0
    assert cmap["Security Name"] == 1
    assert cmap["Amount"] == 2  # First occurrence wins


def test_ais_clean_header_and_validation():
    cleaned = ais_schemas.clean_header("  Total \n Amount (Rs.) ")
    assert "AMOUNT" in cleaned
    assert "\n" not in cleaned

    # Valid schema check for dividend_sft
    assert ais_schemas.validate_schema("dividend_sft", ["SR. NO.", "REPORTED ON", "DIVIDEND AMOUNT", "STATUS"]) is True

    # Missing column in golden schema raises AISStructureChangedError
    with pytest.raises(ais_schemas.AISStructureChangedError):
        ais_schemas.validate_schema("dividend_sft", ["SR. NO.", "STATUS"])
