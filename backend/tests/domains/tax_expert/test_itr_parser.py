"""ITR PDF parser and helper extraction utilities."""

import io
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from domains.tax_expert import itr_parser


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

def test_itr_find_value_max_and_find_str_form_prefix():
    text = "Form ITR-2\nAssessment Year: 2021-22"
    itr_type = itr_parser._find_str(text, r"(ITR[-\s]?[1-6U])", r"Form\s+(ITR-[0-9])")
    assert itr_type == "ITR-2"

def test_parse_itr_pdf_derives_deductions_and_slab_tax(monkeypatch):
    text = """
    ITR-1
    Assessment Year: 2024-25
    PAN: SLAB12345A
    Name: SLAB USER
    Gross Total Income 500,000
    Total Income 450,000
    Tax at normal rates 25,000
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    assert result["deductions"]["total"] == pytest.approx(50000.0)
    assert result["tax"]["tax_on_income"] == pytest.approx(25000.0)

def test_parse_itr_pdf_derives_total_tax_from_tds(monkeypatch):
    text = """
    ITR-2
    Assessment Year: 2022-23
    PAN: DERIV1234B
    Name: DERIVE TAX
    Gross Total Income 600,000
    Total Income 600,000
    Total Tax and Cess 115
    TDS 80,000
    Advance Tax 10,000
    Refund 5,000
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    # Parsed liability 115 is zeroed by guard; then derived from TDS + advance - refund
    assert result["tax"]["total_tax_liability"] == pytest.approx(85000.0)

def test_parse_itr_pdf_empty_pages(monkeypatch):
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    assert result["itr_type"] == "Unknown"
    assert result["assessment_year"] == "2025-26"
    assert result["income"]["gross_total"] == 0.0

def test_parse_itr_pdf_full_tax_computation(monkeypatch):
    """Exercise deduction derivation, rebate math, interest 234, refund/due branches."""
    text = """
    ITR-3
    Assessment Year: 2024-25
    PAN: XYZAB5678C
    Name: FULL COVERAGE TAXPAYER
    Income chargeable under the Head Salaries 2,000,000
    Income from House Property 50,000
    Profits and gains from business or profession 100,000
    Total Capital Gains 75,000
    Income from other sources 25,000
    Gross Total Income 2,250,000
    80C 150,000
    80D 25,000
    Total Deductions 175,000
    Total Income 2,075,000
    Tax at normal rates 300,000
    Tax at special rates 10,000
    Tax payable on total income 310,000
    Rebate u/s 87A 12,500
    Surcharge 5,000
    Health and Education Cess 12,000
    234A 1,000
    234B 2,000
    234C 500
    Aggregate liability (12+13e) 315,500
    TDS (total of column 4) 200,000
    Advance Tax (from column 6) 50,000
    Total Taxes Paid (15a+15b) 250,000
    Refund 0
    Balance Tax Payable 65,500
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF mock%")
    assert result["itr_type"] == "ITR-3"
    assert result["pan"] == "XYZAB5678C"
    assert result["income"]["salary"] == 2000000.0
    assert result["income"]["gross_total"] == 2250000.0
    assert result["deductions"]["sec_80c"] == 150000.0
    assert result["tax"]["taxable_income"] == 2075000.0
    assert result["tax"]["tax_at_slab_rates"] == 300000.0
    assert result["tax"]["interest_234_total"] == pytest.approx(3500.0)
    assert result["tax"]["total_tax_liability"] == 315500.0
    assert result["tax"]["refund_or_due"] == pytest.approx(-65500.0)

def test_parse_itr_pdf_itr_type_prefix_normalization(monkeypatch):
    text = "Form ITR-3\nAssessment Year: 2023-24\nPAN: ABCDE1234F\nName: X"
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    assert result["itr_type"] == "ITR-3"

def test_parse_itr_pdf_refund_path_and_guards(monkeypatch):
    text = """
    ITR-1
    A.Y.: 2023-24
    PAN: QWERT1234A
    Name: REFUND USER
    Gross Total Income 800,000
    Total Deductions 50,000
    Total Income 750,000
    Tax before rebate 50,000
    TDS 60,000
    Advance Tax 234
    Refund 15,000
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    assert result["itr_type"] == "ITR-1"
    assert result["tax"]["advance_tax"] == 0.0  # 234 guard
    assert result["tax"]["refund_or_due"] == 15000.0

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

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    # Lazy import inside parse_itr_pdf — inject via sys.modules, not attribute path.
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF-1.4 mock content")
    assert result["pan"] == "ABCDE1234F"
    assert result["assessment_year"] == "2025-26"
    assert result["itr_type"] == "ITR-2"

def test_parse_itr_pdf_taxable_income_from_gti_minus_deductions(monkeypatch):
    """When parsed Total Income >= GTI, code recomputes taxable income."""
    text = """
    ITR-2
    Assessment Year: 2025-26
    PAN: GTI0001234C
    Name: GTI TEST
    Gross Total Income 1,000,000
    Total Deductions 100,000
    Total Income 1,000,000
    """
    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_pdf.pages = [mock_page]

    import sys
    mock_pdfplumber = MagicMock()
    mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
    monkeypatch.setitem(sys.modules, "pdfplumber", mock_pdfplumber)

    result = itr_parser.parse_itr_pdf(b"%PDF%")
    assert result["tax"]["taxable_income"] == 900000.0



def test_itr_find_str_form_prefix():
    assert itr_parser._find_str("Form ITR2 here", r"Form\s+(ITR-[0-9])") is not None
