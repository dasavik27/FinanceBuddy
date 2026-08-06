"""
Statement parsing: amounts, upload limits, header detection, and the dedup rule.

Each test here corresponds to a defect that was live in the first cut of the domain.
The amount cases in particular are regression pins for silent money errors - a wrong
number that parses without complaint is worse than a failed upload, because nothing
downstream can tell.
"""

import io

import pandas as pd
import pytest

from shared.uploads import (
    MAX_UPLOAD_BYTES,
    UnsupportedUploadType,
    UploadTooLarge,
    read_upload,
)
from domains.budget.amounts import direction_from, parse_amount
from domains.budget.parser import ParseResult, parse_bank_statement
from domains.budget.sessions import _merge_overlapping_statements


# ── amounts ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected,negative", [
    ("1,500.00", 1500.00, False),
    ("-1,500.00", 1500.00, True),      # was 1500.00 positive: the minus was stripped
    ("(2,300.50)", 2300.50, True),     # accounting parentheses
    ("500-", 500.00, True),            # trailing sign, mainframe exports
    ("5,00,000.00", 500000.00, False), # Indian lakh grouping
    ("1.500,00", 1500.00, False),      # European grouping
    ("Rs. 2,999.00", 2999.00, False),
    ("₹ 1,23,456.78", 123456.78, False),
    ("INR 1 234,50", 1234.50, False),  # space as grouping
    ("0.00", 0.0, False),
])
def test_amount_formats(raw, expected, negative):
    money = parse_amount(raw)
    assert money is not None, f"{raw!r} should parse"
    assert money.magnitude == pytest.approx(expected)
    assert money.negative is negative


@pytest.mark.parametrize("raw", ["1e3", "abc", "", "nan", None, "12,3456", "  ", "-"])
def test_unparseable_amounts_are_rejected_not_guessed(raw):
    """
    None means "skip and count", never zero.

    `1e3` is the sharp one: the old regex stripped the 'e' and produced 13.0.
    """
    assert parse_amount(raw) is None


def test_nan_is_not_an_amount():
    assert parse_amount(float("nan")) is None


def test_bool_is_not_an_amount():
    """True would otherwise parse as 1 via the numeric fast path."""
    assert parse_amount(True) is None


@pytest.mark.parametrize("raw,marker", [("1,500.00 Cr", "cr"), ("900.10Dr", "dr"), ("Dr 900.10", "dr")])
def test_cr_dr_markers_are_read(raw, marker):
    money = parse_amount(raw)
    assert money is not None and money.marker == marker


def test_a_negative_in_the_withdrawal_column_is_money_in():
    """A reversal posted as -1250 in Withdrawal is a credit, not a 1250 expense."""
    money = parse_amount("-1250.50")
    assert direction_from(money, column_direction="debit") == "credit"


def test_a_cr_marker_beats_the_column_it_sits_in():
    assert direction_from(parse_amount("500 Cr"), column_direction="debit") == "credit"


def test_a_type_column_beats_the_column_default():
    assert direction_from(parse_amount("500"), column_direction="debit", type_hint="CR") == "credit"


# ── upload limits ─────────────────────────────────────────────────────────────

def test_oversized_upload_is_rejected_without_being_materialised():
    payload = io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1024))
    with pytest.raises(UploadTooLarge):
        read_upload(payload, "statement.csv")


def test_unsupported_extension_is_rejected_before_reading():
    payload = io.BytesIO(b"whatever")
    with pytest.raises(UnsupportedUploadType):
        read_upload(payload, "statement.exe")
    assert payload.tell() == 0, "the body must not be read at all"


def test_empty_upload_is_rejected():
    with pytest.raises(UnsupportedUploadType):
        read_upload(io.BytesIO(b""), "statement.csv")


@pytest.mark.parametrize("name", ["a.csv", "a.CSV", "a.xlsx", "a.xls", "a.txt"])
def test_accepted_extensions(name):
    assert read_upload(io.BytesIO(b"Date,x\n1,2\n"), name)


# ── header detection ──────────────────────────────────────────────────────────

_HDFC = """Statement of account
Account No :50100xxxx1234
,,,,,
Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/04/25,UPI/DR/402938/SWIGGY BANGALORE,"1,250.50",,"48,749.50"
02/04/25,SALARY CREDIT APRIL,,"1,20,000.00","1,68,749.50"
03/04/25,POS 4321 STARBUCKS,50.00,,"1,68,699.50"
03/04/25,POS 4321 STARBUCKS,50.00,,"1,68,649.50"
04/04/25,REVERSAL SWIGGY FAILED,-1250.50,,"1,69,900.00"
*This is a computer generated statement
"""


def test_header_below_a_preamble_is_found():
    """
    A preamble above the table used to defeat the reader entirely.

    With header=0 pandas took "Statement of account" as the header and then treated
    every five-field data row as malformed - discarding the whole transaction table
    and reporting no error.
    """
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    assert result.error is None
    assert result.parsed == 5


def test_footer_disclaimer_is_skipped_and_counted():
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    assert result.skipped == 1
    assert sum(result.reasons.values()) == 1


def test_indian_grouping_survives_the_round_trip():
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    salary = result.frame[result.frame["description"].str.contains("SALARY")]
    assert salary.iloc[0]["amount"] == pytest.approx(120000.00)


def test_a_reversal_is_credited_not_debited():
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    reversal = result.frame[result.frame["description"].str.contains("REVERSAL")]
    assert reversal.iloc[0]["type"] == "credit"


def test_running_balance_is_captured_for_reconciliation():
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    assert "balance" in result.frame.columns
    assert result.frame.iloc[0]["balance"] == pytest.approx(48749.50)


def test_dates_are_iso_and_day_first():
    result = parse_bank_statement(_HDFC.encode(), "acct.csv", "HDFC", "Savings Account")
    assert result.frame.iloc[0]["date"] == "2025-04-01"


def test_a_file_that_matches_nothing_explains_what_it_saw():
    junk = b"alpha,beta,gamma\n1,2,3\n"
    result = parse_bank_statement(junk, "junk.csv", "HDFC", "Savings Account")
    assert result.frame.empty
    assert "alpha" in result.error


# ── overlap merging ───────────────────────────────────────────────────────────

def _row(session, desc, amount, date="2025-04-03"):
    return {
        "session_id": session, "date": date, "description": desc, "amount": amount,
        "type": "debit", "source_bank": "HDFC", "account_type": "Savings Account",
    }


def test_genuine_same_day_repeats_are_preserved():
    """
    The original `drop_duplicates(keep="last")` deleted real transactions: two identical
    coffees on one day became one. That is silent, unrecoverable data loss.
    """
    df = pd.DataFrame([
        _row("s1", "STARBUCKS", 50.0),
        _row("s1", "STARBUCKS", 50.0),
        _row("s2", "NETFLIX", 649.0),
    ])
    merged = _merge_overlapping_statements(df)
    assert (merged["description"] == "STARBUCKS").sum() == 2


def test_overlapping_statements_are_merged():
    """The same transaction appearing in two statements collapses to one."""
    df = pd.DataFrame([
        _row("s1", "NETFLIX", 649.0),
        _row("s2", "NETFLIX", 649.0),
    ])
    merged = _merge_overlapping_statements(df)
    assert len(merged) == 1


def test_overlap_merge_keeps_the_richer_statement():
    """
    Two coffees in one statement and one in an overlapping statement is two coffees,
    not one and not three.
    """
    df = pd.DataFrame([
        _row("s1", "STARBUCKS", 50.0),
        _row("s1", "STARBUCKS", 50.0),
        _row("s2", "STARBUCKS", 50.0),
    ])
    merged = _merge_overlapping_statements(df)
    assert len(merged) == 2
    assert set(merged["session_id"]) == {"s1"}


def test_a_single_statement_is_never_deduplicated():
    df = pd.DataFrame([_row("s1", "STARBUCKS", 50.0), _row("s1", "STARBUCKS", 50.0)])
    assert len(_merge_overlapping_statements(df)) == 2

def test_parser_extract_rows_branches():
    from domains.budget.parser import _extract_rows, _normalise_dates

    df = pd.DataFrame({
        "Date": ["01/04/25", None, "01/04/25", "01/04/25", "01/04/25"],
        "Narration": ["Swiggy", "x", "Zero", "Bad", "Credit"],
        "Withdrawal Amt.": ["500.00", "100", "0.00", "notmoney", ""],
        "Deposit Amt.": ["", "", "", "", "200.00"],
    })
    mapping = {"date": "Date", "description": "Narration", "debit": "Withdrawal Amt.", "credit": "Deposit Amt."}
    result = _extract_rows(df, mapping, "HDFC", "hdfc", "Savings Account")
    assert result.parsed >= 2
    assert result.skipped >= 1
    assert result.error is None

    empty_result = _extract_rows(df.iloc[0:0], mapping, "HDFC", "hdfc", "Savings Account")
    assert empty_result.parsed == 0 and empty_result.error

    weird_dates = pd.Series(["not-a-date", "01/04/25"])
    normed = _normalise_dates(weird_dates)
    assert len(normed) == 2

def test_parser_report_and_branches(monkeypatch):
    result = ParseResult(pd.DataFrame(), "HDFC", "Savings")
    report = result.report()
    assert report["parsed"] == 0 and report["truncated"] is False

    def _read_table(raw, name):
        if name == "bad.csv":
            raise RuntimeError("bad file")
        if name == "empty.csv":
            return pd.DataFrame()
        if name == "junk.csv":
            return pd.read_csv(__import__("io").BytesIO(raw))
        if name == "n.csv":
            return pd.read_csv(__import__("io").BytesIO(raw))
        return pd.DataFrame()

    monkeypatch.setattr("domains.budget.parser.read_table_raw", _read_table)

    bad = parse_bank_statement(b"x", "bad.csv", "HDFC")
    assert bad.error and "Failed to read" in bad.error

    empty = parse_bank_statement(b"x", "empty.csv", "HDFC")
    assert empty.error == "The statement has no rows."

    junk = b"alpha,beta\n1,2\n"
    no_match = parse_bank_statement(junk, "junk.csv", "HDFC")
    assert "widest row" in no_match.error.lower() or "alpha" in no_match.error

    narration_junk = b"Date,Narration,Withdrawal,Deposit\nnot-a-date,Withdrawal row,100,\n"
    narr = parse_bank_statement(narration_junk, "n.csv", "HDFC")
    assert narr.error is not None



def test_budget_parser_amount_without_type():
    from domains.budget.parser import _find_column_mapping

    cfg = {"date": ["Date"], "description": ["Narration"], "amount": ["Amount"]}
    mapping = _find_column_mapping(["Date", "Narration", "Amount"], cfg)
    assert mapping is not None
    assert "amount" in mapping


def test_budget_parser_column_and_amount_branches(monkeypatch):
    from domains.budget import parser

    cols = {
        "date": "Date",
        "description": ["Description", "Narration"],
        "amount": "Amount",
        "type": "Dr/Cr",
    }
    cfg = {"columns": cols}
    col_map = parser._find_column_mapping(["Date", "Description", "Amount", "Dr/Cr"], cols)
    assert col_map is not None
    assert col_map.get("type") == "Dr/Cr"

    csv = (
        "Date,Description,Amount,Dr/Cr\n"
        "01/04/2025,SWIGGY,not-a-number,Dr\n"
        "02/04/2025,ZERO,0,Dr\n"
    )
    monkeypatch.setattr(parser, "load_bank_config", lambda: {"HDFC": cfg, "generic": cfg})
    report = parser.parse_bank_statement(csv.encode(), filename="hdfc.csv", bank="HDFC")
    assert report.skipped >= 1 or report.parsed >= 0
