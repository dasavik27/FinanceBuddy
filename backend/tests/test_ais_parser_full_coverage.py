"""
test_ais_parser_full_coverage.py

Full unit test coverage for domains.tax_expert.ais_parser:
- helper utilities (_is_blank, _col_map, _clean_amount, _parse_date, _safe_num)
- text extraction (_extract_personal, _extract_dividends_fallback)
- table processors (_process_salary_tds, _process_salary_annexure, _process_dividend_sft,
  _process_dividend_tds, _process_interest, _process_interest_tds, _process_cg_equity,
  _process_cg_mf, _process_real_estate, _process_tax_payments, _process_refunds)
- TDS consolidation (_finalise_tds_total)
- parse_ais_pdf end-to-end integration mock (all table dispatch branches & error handling)
"""

import sys
from unittest.mock import MagicMock
import pandas as pd
import pytest
from domains.tax_expert import ais_parser
from domains.tax_expert.ais_schemas import AISUnknownCodeError


def test_is_blank():
    assert ais_parser._is_blank(None) is True
    assert ais_parser._is_blank(float("nan")) is True
    assert ais_parser._is_blank("   ") is True
    assert ais_parser._is_blank("abc") is False
    assert ais_parser._is_blank(123) is False


def test_col_map():
    headers = ["A", "B", "A", "C"]
    cmap = ais_parser._col_map(headers)
    assert cmap == {"A": 0, "B": 1, "C": 3}


def test_clean_amount():
    assert ais_parser._clean_amount("₹ 1,50,000.50") == 150000.50
    assert ais_parser._clean_amount("") == 0.0
    assert ais_parser._clean_amount("invalid") == 0.0
    assert ais_parser._clean_amount(500) == 500.0


def test_parse_date():
    assert ais_parser._parse_date("15/08/2024") == "2024-08-15"
    assert ais_parser._parse_date("2024-08-15") == "2024-08-15"
    assert ais_parser._parse_date("") == ""
    assert ais_parser._parse_date("invalid-date") == "invalid-date"


def test_safe_num():
    assert ais_parser._safe_num(100) == 100.0
    assert ais_parser._safe_num("250.5") == 250.5
    assert ais_parser._safe_num("bad") == 0.0
    assert ais_parser._safe_num(None) == 0.0


def test_extract_personal():
    sample_text = (
        "Income Tax Department\n"
        "Permanent Account Number (PAN)\n"
        "ABCDE1234F\n"
        "Name of Assessee\n"
        "XXXX 1234 JOHN DOE\n"
        "Date of Birth\n"
        "01/01/1990\n"
        "test.user@example.com\n"
        "9876543210\n"
        "Financial Year 2024-25\n"
    )
    res = ais_parser._extract_personal(sample_text)
    assert res.get("pan") == "ABCDE1234F"
    assert "JOHN DOE" in res.get("name", "")
    assert res.get("dob") == "01/01/1990"
    assert res.get("email") == "test.user@example.com"
    assert res.get("mobile") == "9876543210"
    assert res.get("fy") == "2024-25"


def test_process_salary_tds():
    df = pd.DataFrame([
        ["SRNO", "AMOUNTPAIDCREDITED", "TDSDEDUCTED", "TDSDEPOSITED", "QUARTER", "DATEOFPAYMENTCREDIT"],
        ["1", "1,00,000", "10,000", "10,000", "Q1", "30/06/2024"],
        ["2", "1,20,000", "12,000", "12,000", "Q2", "30/09/2024"],
    ])
    headers = ["SRNO", "AMOUNTPAIDCREDITED", "TDSDEDUCTED", "TDSDEPOSITED", "QUARTER", "DATEOFPAYMENTCREDIT"]
    result = {"salary": {"gross": 0, "tds_deducted": 0, "employer": "", "quarterly": []}}

    ais_parser._process_salary_tds(df, headers, result, source="Acme Corp")
    assert result["salary"]["employer"] == "Acme Corp"
    assert result["salary"]["gross"] == 220000.0
    assert result["salary"]["tds_deducted"] == 22000.0
    assert len(result["salary"]["quarterly"]) == 2


def test_process_salary_annexure():
    df = pd.DataFrame([
        ["GROSSSALARY", "VALUEOFPERQUISITES", "PROFITINLIEU"],
        ["12,00,000", "50,000", "20,000"],
    ])
    headers = ["GROSSSALARY", "VALUEOFPERQUISITES", "PROFITINLIEU"]
    result = {"salary_annexure": {"gross_salary": 0, "perquisites": 0, "profits_lieu": 0}}

    ais_parser._process_salary_annexure(df, headers, result)
    assert result["salary_annexure"]["gross_salary"] == 1200000.0
    assert result["salary_annexure"]["perquisites"] == 50000.0
    assert result["salary_annexure"]["profits_lieu"] == 20000.0


def test_process_dividends_sft_and_tds():
    df_sft = pd.DataFrame([
        ["DIVIDENDAMOUNT"],
        ["5,000"],
    ])
    headers_sft = ["DIVIDENDAMOUNT"]
    result = {"dividends": []}
    ais_parser._process_dividend_sft(df_sft, headers_sft, result)
    assert len(result["dividends"]) == 1
    assert result["dividends"][0]["amount"] == 5000.0

    df_tds = pd.DataFrame([
        ["AMOUNTPAIDCREDITED", "TDSDEDUCTED"],
        ["10,000", "1,000"],
    ])
    headers_tds = ["AMOUNTPAIDCREDITED", "TDSDEDUCTED"]
    ais_parser._process_dividend_tds(df_tds, headers_tds, result)
    assert len(result["dividends"]) == 2
    assert result["dividends"][1]["tds_deducted"] == 1000.0


def test_process_interest_and_tds():
    df_int = pd.DataFrame([
        ["INTERESTAMOUNT", "ACCOUNTTYPE"],
        ["4,000", "Savings Account"],
        ["40,000", "Term Deposit"],
    ])
    headers_int = ["INTERESTAMOUNT", "ACCOUNTTYPE"]
    result = {"interest_savings": [], "interest_deposits": []}
    ais_parser._process_interest(df_int, headers_int, result)
    assert len(result["interest_savings"]) == 1
    assert len(result["interest_deposits"]) == 1

    df_tds = pd.DataFrame([
        ["AMOUNTPAIDCREDITED", "TDSDEDUCTED"],
        ["50,000", "5,000"],
    ])
    headers_tds = ["AMOUNTPAIDCREDITED", "TDSDEDUCTED"]
    ais_parser._process_interest_tds(df_tds, headers_tds, result)
    assert len(result["interest_deposits"]) == 2
    assert result["interest_deposits"][1]["tds_deducted"] == 5000.0


def test_process_capital_gains_equity_and_mf():
    df_eq = pd.DataFrame([
        ["STATUS", "ASSETTYPE", "SALESCONSIDERATION", "COSTOFACQUISITION", "SECURITYNAMESECURITYCODE", "SECURITYCLASS", "SALEPRICEPERUNIT", "QUANTITY", "FAIRMARKETVALUE", "DATEOFSALETRANSFER"],
        ["Active", "Short Term", "1,50,000", "1,00,000", "RELIANCE", "Listed Equity", "2500", "60", "0", "10/05/2024"],
        ["Active", "Long Term", "2,00,000", "1,00,000", "STARTUP PRIVATE LTD", "Unlisted Shares", "200", "1000", "0", "10/06/2024"],
        ["Active", "Long Term", "50,000", "40,000", "SGB 2025", "Gold Bond", "5000", "10", "0", "10/07/2024"],
    ])
    headers_eq = ["STATUS", "ASSETTYPE", "SALESCONSIDERATION", "COSTOFACQUISITION", "SECURITYNAMESECURITYCODE", "SECURITYCLASS", "SALEPRICEPERUNIT", "QUANTITY", "FAIRMARKETVALUE", "DATEOFSALETRANSFER"]
    result = {
        "capital_gains_equity": [],
        "capital_gains_mf_equity": [],
        "capital_gains_mf_other": [],
        "cg_unlisted": [],
        "cg_bonds_gold": [],
    }
    ais_parser._process_cg_equity(df_eq, headers_eq, result)
    assert len(result["capital_gains_equity"]) == 1
    assert len(result["cg_unlisted"]) == 1
    assert len(result["cg_bonds_gold"]) == 1

    df_mf = pd.DataFrame([
        ["STATUS", "ASSETTYPE", "SALESCONSIDERATION", "COSTOFACQUISITION", "AMCNAMECODE", "SECURITYNAMESECURITYCODE", "SECURITYCLASS", "SALEPRICEPERUNIT", "QUANTITY", "FAIRMARKETVALUE", "DATEOFSALETRANSFER"],
        ["Active", "Long Term", "1,00,000", "70,000", "HDFC AMC", "HDFC Top 100 Fund", "Equity", "100", "1000", "0", "15/05/2024"],
        ["Active", "Short Term", "50,000", "48,000", "ICICI AMC", "ICICI Liquid Fund", "Debt", "1000", "50", "0", "20/05/2024"],
    ])
    headers_mf = ["STATUS", "ASSETTYPE", "SALESCONSIDERATION", "COSTOFACQUISITION", "AMCNAMECODE", "SECURITYNAMESECURITYCODE", "SECURITYCLASS", "SALEPRICEPERUNIT", "QUANTITY", "FAIRMARKETVALUE", "DATEOFSALETRANSFER"]
    ais_parser._process_cg_mf(df_mf, headers_mf, result)
    assert len(result["capital_gains_mf_equity"]) == 1
    assert len(result["capital_gains_mf_other"]) == 1


def test_process_real_estate_tax_payments_and_refunds():
    df_re = pd.DataFrame([
        ["STATUS", "TRANSACTIONVALUE", "PROPERTYDESCRIPTION"],
        ["Active", "75,00,000", "Flat 402, Green Valley Apartments"],
    ])
    headers_re = ["STATUS", "TRANSACTIONVALUE", "PROPERTYDESCRIPTION"]
    result = {"cg_real_estate": [], "tax_payments": [], "refunds": []}
    ais_parser._process_real_estate(df_re, headers_re, result)
    assert len(result["cg_real_estate"]) == 1
    assert result["cg_real_estate"][0]["consideration"] == 7500000.0
    assert result["cg_real_estate"][0]["cost_unknown"] is True

    df_tax = pd.DataFrame([
        ["TOTALABCD", "FINANCIALYEAR", "TAXA", "SURCHARGEB", "EDUCATIONCESSC", "DATEOFDEPOSIT"],
        ["1,04,000", "2024-25", "1,00,000", "0", "4,000", "15/12/2024"],
    ])
    headers_tax = ["TOTALABCD", "FINANCIALYEAR", "TAXA", "SURCHARGEB", "EDUCATIONCESSC", "DATEOFDEPOSIT"]
    ais_parser._process_tax_payments(df_tax, headers_tax, result)
    assert len(result["tax_payments"]) == 1
    assert result["tax_payments"][0]["total"] == 104000.0

    df_ref = pd.DataFrame([
        ["REFUNDAMOUNT", "FINANCIALYEAR", "DATEOFPAYMENT"],
        ["12,500", "2023-24", "10/08/2024"],
    ])
    headers_ref = ["REFUNDAMOUNT", "FINANCIALYEAR", "DATEOFPAYMENT"]
    ais_parser._process_refunds(df_ref, headers_ref, result)
    assert len(result["refunds"]) == 1
    assert result["refunds"][0]["amount"] == 12500.0


def test_finalise_tds_total():
    result = {
        "salary": {"quarterly": [{"tds_deducted": 20000.0}, {"tds_deducted": 30000.0}]},
        "dividends": [{"tds_deducted": 1000.0}],
        "interest_deposits": [{"tds_deducted": 5000.0}],
        "interest_savings": [],
        "rent_received": [{"tds_deducted": 2500.0}],
        "tds_total": 0.0,
    }
    ais_parser._finalise_tds_total(result)
    assert result["tds_total"] == 58500.0


def test_extract_dividends_fallback():
    text = "Information Section Dividend income from Indian Companies 12,450 paid during the year"
    divs = ais_parser._extract_dividends_fallback(text)
    assert len(divs) == 1
    assert divs[0]["amount"] == 12450.0


def test_parse_ais_pdf_dispatch(monkeypatch):
    mock_camelot = MagicMock()
    mock_pypdf = MagicMock()

    monkeypatch.setitem(sys.modules, "camelot", mock_camelot)
    monkeypatch.setitem(sys.modules, "pypdf", mock_pypdf)

    page_mock = MagicMock()
    page_mock.extract_text.return_value = (
        "Permanent Account Number (PAN)\nABCDE1234F\nName of Assessee\nJOHN DOE\nDate of Birth\n01/01/1990\nFinancial Year 2024-25\n"
    )
    reader_mock = MagicMock()
    reader_mock.pages = [page_mock]
    mock_pypdf.PdfReader.return_value = reader_mock

    # Create mock table objects matching GOLDEN_SCHEMAS
    t1 = MagicMock()
    t1.df = pd.DataFrame([
        ["SR. NO.", "FINANCIAL YEAR", "MAJOR HEAD", "MINOR HEAD", "TAX (A)", "SURCHARGE (B)", "EDUCATION CESS (C)", "OTHERS (D)", "TOTAL (A+B+C+D)", "BSR CODE", "DATE OF DEPOSIT", "CHALLAN SERIAL NUMBER", "CHALLAN IDENTIFICATION NUMBER"],
        ["1", "2024-25", "0020", "200", "10,000", "0", "0", "0", "10,000", "0002134", "10/05/2024", "12345", "00021341005202412345"],
    ])

    t2 = MagicMock()
    t2.df = pd.DataFrame([
        ["SR. NO.", "FINANCIAL YEAR", "MODE", "NATURE OF REFUND", "REFUND AMOUNT", "DATE OF PAYMENT"],
        ["1", "2023-24", "NECS", "Income Tax", "5,000", "10/05/2024"],
    ])

    t3_summary = MagicMock()
    t3_summary.df = pd.DataFrame([
        ["INFORMATION CODE", "INFORMATION SOURCE"],
        ["SFT-015 Dividend", "ABC LTD"],
    ])

    t3_child = MagicMock()
    t3_child.df = pd.DataFrame([
        ["SR. NO.", "REPORTED ON", "DIVIDEND AMOUNT", "STATUS"],
        ["1", "15/06/2024", "2,500", "Active"],
    ])

    mock_camelot.read_pdf.return_value = [t1, t2, t3_summary, t3_child]

    parsed = ais_parser.parse_ais_pdf(b"%PDF-1.4 test")
    assert parsed["personal"]["pan"] == "ABCDE1234F"
    assert len(parsed["tax_payments"]) == 1
    assert len(parsed["refunds"]) == 1
    assert len(parsed["dividends"]) == 1


def test_parse_ais_pdf_all_codes_dispatch(monkeypatch):
    mock_camelot = MagicMock()
    mock_pypdf = MagicMock()

    monkeypatch.setitem(sys.modules, "camelot", mock_camelot)
    monkeypatch.setitem(sys.modules, "pypdf", mock_pypdf)

    page_mock = MagicMock()
    page_mock.extract_text.return_value = (
        "Permanent Account Number (PAN)\nABCDE1234F\nName of Assessee\nJOHN DOE\nDate of Birth\n01/01/1990\nFinancial Year 2024-25\n"
    )
    reader_mock = MagicMock()
    reader_mock.pages = [page_mock]
    mock_pypdf.PdfReader.return_value = reader_mock

    # TDS-194 Dividend
    t_div_sum = MagicMock()
    t_div_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["TDS-194 Dividend", "XYZ AMC"]])
    t_div_ch = MagicMock()
    t_div_ch.df = pd.DataFrame([
        ["SR. NO.", "QUARTER", "DATE OF PAYMENT/CREDIT", "AMOUNT PAID/CREDITED", "TDS DEDUCTED", "TDS DEPOSITED", "STATUS"],
        ["1", "Q1", "15/06/2024", "10,000", "1,000", "1,000", "Active"],
    ])

    # TDS-192 Salary
    t_sal_sum = MagicMock()
    t_sal_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["TDS-192 Salary", "Google India"]])
    t_sal_ch = MagicMock()
    t_sal_ch.df = pd.DataFrame([
        ["SR. NO.", "QUARTER", "DATE OF PAYMENT/CREDIT", "AMOUNT PAID/CREDITED", "TDS DEDUCTED", "TDS DEPOSITED", "STATUS"],
        ["1", "Q1", "30/04/2024", "2,00,000", "20,000", "20,000", "Active"],
    ])

    # TDS-ANN Annexure
    t_ann_sum = MagicMock()
    t_ann_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["TDS-ANN Salary Annexure", "Google India"]])
    t_ann_ch = MagicMock()
    t_ann_ch.df = pd.DataFrame([
        ["SR. NO.", "GROSS SALARY", "VALUE OF PERQUISITES", "PROFIT IN LIEU OF SALARY"],
        ["1", "24,00,000", "1,00,000", "50,000"],
    ])

    # SFT-016 Interest SB
    t_sb_sum = MagicMock()
    t_sb_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["SFT-016 Savings Interest", "HDFC Bank"]])
    t_sb_ch = MagicMock()
    t_sb_ch.df = pd.DataFrame([
        ["SR. NO.", "REPORTED ON", "ACCOUNT NUMBER", "ACCOUNT TYPE", "INTEREST AMOUNT", "STATUS"],
        ["1", "10/05/2024", "123456", "SAVINGS", "5,000", "Active"],
    ])

    # TDS-194A Interest TD
    t_td_sum = MagicMock()
    t_td_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["TDS-194A Term Deposit Interest", "HDFC Bank"]])
    t_td_ch = MagicMock()
    t_td_ch.df = pd.DataFrame([
        ["SR. NO.", "QUARTER", "DATE OF PAYMENT/CREDIT", "AMOUNT PAID/CREDITED", "TDS DEDUCTED", "TDS DEPOSITED", "STATUS"],
        ["1", "Q1", "10/05/2024", "50,000", "5,000", "5,000", "Active"],
    ])

    # SFT-17-LES Equity
    t_eq_sum = MagicMock()
    t_eq_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["SFT-17-LES Equity Shares", "NSE"]])
    t_eq_ch = MagicMock()
    t_eq_ch.df = pd.DataFrame([
        ["SR. NO.", "DATE OF SALE/ TRANSFER", "SECURITY NAME (SECURITY CODE)", "SECURITY CLASS", "DEBIT TYPE", "CREDIT TYPE", "ASSET TYPE", "QUANTITY", "SALE PRICE PER UNIT", "SALES CONSIDERATION", "COST OF ACQUISITION", "UNIT FMV", "FAIR MARKET VALUE", "INDEXED COST OF ACQUISITION", "STATUS"],
        ["1", "15/06/2024", "INFOSYS", "Listed Equity", "DR", "CR", "LTCG", "100", "1500", "1,50,000", "1,00,000", "0", "0", "0", "Active"],
    ])

    # SFT-18-EMF MF
    t_mf_sum = MagicMock()
    t_mf_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["SFT-18-EMF Mutual Funds", "CAMS"]])
    t_mf_ch = MagicMock()
    t_mf_ch.df = pd.DataFrame([
        ["SR. NO.", "AMC NAME (CODE)", "DATE OF SALE/ TRANSFER", "SECURITY CLASS", "SECURITY NAME (SECURITY CODE)", "DEBIT TYPE", "CREDIT TYPE", "ASSET TYPE", "QUANTITY", "SALE PRICE PER UNIT", "SALES CONSIDERATION", "STT", "COST OF ACQUISITION", "UNIT FMV", "FAIR MARKET VALUE", "INDEXED COST OF ACQUISITION", "STATUS"],
        ["1", "SBI AMC", "15/06/2024", "Equity", "SBI Bluechip", "DR", "CR", "LTCG", "500", "100", "50,000", "50", "35,000", "0", "0", "0", "Active"],
    ])

    # SFT-12 Real Estate
    t_re_sum = MagicMock()
    t_re_sum.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["SFT-12 Immovable Property", "Sub-Registrar"]])
    t_re_ch = MagicMock()
    t_re_ch.df = pd.DataFrame([
        ["SR. NO.", "DATE OF TRANSACTION", "PROPERTY DESCRIPTION", "TRANSACTION VALUE", "STATUS"],
        ["1", "15/06/2024", "Flat 101", "50,00,000", "Active"],
    ])

    mock_camelot.read_pdf.return_value = [
        t_div_sum, t_div_ch,
        t_sal_sum, t_sal_ch,
        t_ann_sum, t_ann_ch,
        t_sb_sum, t_sb_ch,
        t_td_sum, t_td_ch,
        t_eq_sum, t_eq_ch,
        t_mf_sum, t_mf_ch,
        t_re_sum, t_re_ch,
    ]

    parsed = ais_parser.parse_ais_pdf(b"%PDF-1.4 test")
    assert parsed["salary"]["gross"] == 200000.0
    assert len(parsed["dividends"]) == 1
    assert len(parsed["interest_savings"]) == 1
    assert len(parsed["interest_deposits"]) == 1
    assert len(parsed["capital_gains_equity"]) == 1
    assert len(parsed["capital_gains_mf_equity"]) == 1
    assert len(parsed["cg_real_estate"]) == 1
    assert parsed["tds_total"] > 0


def test_parse_ais_pdf_no_camelot(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "camelot":
            raise ImportError("No module named camelot")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    res = ais_parser.parse_ais_pdf(b"%PDF-1.4 test")
    assert "error" in res


def test_parse_ais_pdf_unknown_code_and_fallback(monkeypatch):
    mock_camelot = MagicMock()
    mock_pypdf = MagicMock()

    monkeypatch.setitem(sys.modules, "camelot", mock_camelot)
    monkeypatch.setitem(sys.modules, "pypdf", mock_pypdf)

    page_mock = MagicMock()
    page_mock.extract_text.return_value = (
        "Permanent Account Number (PAN)\nABCDE1234F\nName of Assessee\nJOHN DOE\nDate of Birth\n01/01/1990\nFinancial Year 2024-25\n"
        "Dividend income 5000\n"
    )
    reader_mock = MagicMock()
    reader_mock.pages = [page_mock]
    mock_pypdf.PdfReader.return_value = reader_mock

    # Empty tables triggering text fallback for dividends
    mock_camelot.read_pdf.return_value = []
    res = ais_parser.parse_ais_pdf(b"%PDF-1.4 test")
    assert len(res["dividends"]) == 1
    assert res["dividends"][0]["amount"] == 5000.0

    # Unknown code
    t_unknown = MagicMock()
    t_unknown.df = pd.DataFrame([["INFORMATION CODE", "INFORMATION SOURCE"], ["UNKNOWN-CODE-99", "Some Source"]])
    t_child = MagicMock()
    t_child.df = pd.DataFrame([["C1", "C2"], ["v1", "v2"]])
    mock_camelot.read_pdf.return_value = [t_unknown, t_child]

    with pytest.raises(AISUnknownCodeError):
        ais_parser.parse_ais_pdf(b"%PDF-1.4 test")
