"""
Upload limits and parsing for the equity domain.

The /parse endpoint shipped unauthenticated with `file.file.read()` on an arbitrary
body and `pd.read_excel` with no row cap, on a deployment sized at ~512 MB. An .xlsx is
a zip container, so that combination is a single-request out-of-memory kill. These
tests pin the guards.
"""

import io

import pandas as pd
import pytest

from domains.equity.parser import (
    MAX_ROWS,
    MAX_UPLOAD_BYTES,
    UnsupportedUploadType,
    UploadTooLarge,
    parse_holdings_csv,
    parse_tradebook_csv,
    read_upload,
)


def _csv_bytes(rows: int = 3) -> bytes:
    body = "Tradingsymbol,Quantity Available,Average Price,Last Price,PnL\n"
    body += "".join(f"SYM{i},10,100.0,120.0,200.0\n" for i in range(rows))
    return body.encode()


# ── size ceiling ──────────────────────────────────────────────────────────────

def test_oversized_upload_is_rejected():
    oversized = io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1024))
    with pytest.raises(UploadTooLarge):
        read_upload(oversized, "holdings.csv")


def test_oversized_upload_is_not_fully_materialised():
    """
    The check must happen during the read, not after it. A `.read()` with no argument
    pulls the entire body into memory before anyone can object to its size, which is
    exactly the failure mode being guarded.
    """
    class CountingReader:
        def __init__(self):
            self.requested = None

        def read(self, size=-1):
            self.requested = size
            return b"x" * (MAX_UPLOAD_BYTES + 1)

    reader = CountingReader()
    with pytest.raises(UploadTooLarge):
        read_upload(reader, "holdings.csv")
    assert reader.requested is not None and reader.requested > 0, (
        "read() was called unbounded; an oversized body would be materialised in full"
    )


def test_upload_at_the_limit_is_accepted():
    body = b"a" * (MAX_UPLOAD_BYTES - 1)
    assert read_upload(io.BytesIO(body), "holdings.csv") == body


# ── type allowlist ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "holdings.exe", "holdings.pdf", "holdings", "holdings.csv.zip", "",
])
def test_unsupported_extensions_are_rejected(filename):
    with pytest.raises(UnsupportedUploadType):
        read_upload(io.BytesIO(b"anything"), filename)


@pytest.mark.parametrize("filename", ["h.csv", "H.CSV", "h.xlsx", "h.xls", "h.txt"])
def test_supported_extensions_are_accepted(filename):
    assert read_upload(io.BytesIO(b"col\n1\n"), filename)


def test_empty_upload_is_rejected():
    with pytest.raises(UnsupportedUploadType):
        read_upload(io.BytesIO(b""), "holdings.csv")


# ── row cap ───────────────────────────────────────────────────────────────────

def test_row_count_is_capped():
    df, err = parse_holdings_csv(_csv_bytes(rows=MAX_ROWS + 500), filename="h.csv")
    assert err is None
    assert len(df) <= MAX_ROWS, "the row cap did not apply"


# ── error messages do not leak internals ──────────────────────────────────────

def test_malformed_file_does_not_leak_parser_internals():
    """The message used to be f"Could not read CSV: {e}", exposing pandas internals."""
    df, err = parse_holdings_csv(b"\x00\x01\x02 not a csv at all", filename="h.xlsx")
    assert df.empty
    assert err
    for leak in ("Traceback", "pandas", "openpyxl", "zipfile", "codec"):
        assert leak.lower() not in err.lower(), f"error message leaks {leak!r}: {err}"


# ── parsing still works ───────────────────────────────────────────────────────

def test_zerodha_holdings_parse():
    df, err = parse_holdings_csv(_csv_bytes(rows=3), filename="holdings.csv")
    assert err is None
    assert len(df) == 3
    assert df["broker"].iloc[0] == "zerodha"
    assert set(["symbol", "quantity", "avg_price", "invested"]).issubset(df.columns)


def test_numeric_columns_survive_currency_formatting():
    body = (
        "Tradingsymbol,Quantity Available,Average Price,Last Price,PnL\n"
        "RELIANCE,\"1,000\",\"₹1,200.50\",\"₹1,300.00\",\"₹99,500.00\"\n"
    ).encode()
    df, err = parse_holdings_csv(body, filename="h.csv")
    assert err is None
    assert float(df["quantity"].iloc[0]) == 1000.0
    assert float(df["avg_price"].iloc[0]) == 1200.50


def test_already_numeric_columns_are_not_round_tripped_through_strings():
    """
    The coercion loop ran `.astype(str).str.replace(...)` unconditionally, boxing every
    value of an already-clean float column into a Python string and back. Correctness is
    unchanged either way, so this pins the dtype rather than the speed.
    """
    body = _csv_bytes(rows=5)
    df, err = parse_holdings_csv(body, filename="h.csv")
    assert err is None
    assert pd.api.types.is_numeric_dtype(df["quantity"])
    assert pd.api.types.is_numeric_dtype(df["avg_price"])


def test_duplicate_promoted_header_does_not_produce_duplicate_columns():
    """
    A preface row with repeated values made `df.columns` non-unique, after which
    `df["symbol"]` returns a DataFrame instead of a Series and fails somewhere unrelated.
    """
    body = (
        "Unnamed: 0,Unnamed: 1,Unnamed: 2,Unnamed: 3\n"
        "Zerodha Console Export,,,\n"
        "tradingsymbol,quantity,quantity,average price\n"
        "RELIANCE,10,10,100.0\n"
    ).encode()
    df, _err = parse_holdings_csv(body, filename="h.csv")
    assert df.columns.is_unique, f"duplicate columns: {list(df.columns)}"


def test_tradebook_rejects_a_holdings_file():
    df, err = parse_tradebook_csv(_csv_bytes(rows=2), filename="h.csv")
    assert df.empty
    assert err and "Tradebook" in err


def test_holdings_rejects_a_tradebook_file():
    body = (
        "trade_date,tradingsymbol,trade_type,quantity,price\n"
        "2025-06-10,RELIANCE,buy,10,100.0\n"
    ).encode()
    df, err = parse_holdings_csv(body, filename="t.csv")
    assert df.empty
    assert err and "Holdings" in err


def test_broker_config_load_failure(monkeypatch):
    import importlib
    import domains.equity.parser as ep

    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("broker_config.json"):
            raise OSError("missing config")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    importlib.reload(ep)
    assert ep._BROKER_CONFIG == {"zerodha": {}, "groww": {}, "generic": {}}
    monkeypatch.setattr("builtins.open", real_open)
    importlib.reload(ep)


def test_groww_holdings_parse():
    body = (
        "Stock Name,NSE Symbol,Quantity,Average Price,Current Price,Total investment\n"
        "Infosys Ltd,INFY,5,1500.00,1600.00,7500.00\n"
    ).encode()
    df, err = parse_holdings_csv(body, filename="groww.csv")
    assert err is None
    assert df.iloc[0]["symbol"] == "INFY"
    assert df.iloc[0]["broker"] in ("groww", "generic")


def test_generic_holdings_derive_columns():
    body = (
        "symbol,quantity,avg_price\n"
        "ABC,10,100\n"
    ).encode()
    df, err = parse_holdings_csv(body, filename="generic.csv")
    assert err is None
    assert float(df.iloc[0]["ltp"]) == pytest.approx(100.0)
    assert float(df.iloc[0]["invested"]) == pytest.approx(1000.0)


def test_zerodha_authorised_quantity_fallback():
    body = (
        "Tradingsymbol,Authorised quantity,Average Price,PnL\n"
        "RELIANCE,10,100.0,0.0\n"
    ).encode()
    df, err = parse_holdings_csv(body, filename="h.csv")
    assert err is None
    assert float(df.iloc[0]["quantity"]) == 10.0


def test_empty_holdings_file_message():
    body = b"Tradingsymbol,Quantity Available,Average Price\n"
    df, err = parse_holdings_csv(body, filename="h.csv")
    assert df.empty
    assert err == "The uploaded file has no rows."


def test_tradebook_parse_success():
    body = (
        "trade_date,tradingsymbol,transaction_type,quantity,average_price\n"
        "2025-06-10,RELIANCE,buy,10,100.0\n"
    ).encode()
    df, err = parse_tradebook_csv(body, filename="trades.csv")
    assert err is None
    assert df.iloc[0]["symbol"] == "RELIANCE"
    assert df.iloc[0]["type"] == "BUY"


def test_tradebook_read_failure_message():
    df, err = parse_tradebook_csv(b"\x00\x01\x02", filename="trades.xlsx")
    assert df.empty
    assert "Could not read that tradebook" in err


def test_holdings_upload_too_large(monkeypatch):
    import domains.equity.parser as ep

    def boom(raw, filename):
        raise ep.UploadTooLarge("File is larger than 8 MB.")

    monkeypatch.setattr(ep, "_read_tabular", boom)
    df, err = ep.parse_holdings_csv(b"ignored", filename="h.csv")
    assert df.empty
    assert "MB" in err


def test_tradebook_upload_too_large(monkeypatch):
    import domains.equity.parser as ep

    def boom(raw, filename):
        raise ep.UploadTooLarge("File is larger than 8 MB.")

    monkeypatch.setattr(ep, "_read_tabular", boom)
    df, err = ep.parse_tradebook_csv(b"ignored", filename="trades.csv")
    assert df.empty
    assert "MB" in err


def test_tradebook_empty_rows():
    body = b"trade_date,tradingsymbol,transaction_type,quantity,average_price\n"
    df, err = parse_tradebook_csv(body, filename="trades.csv")
    assert df.empty
    assert err == "The uploaded tradebook has no rows."

def test_equity_parser_zerodha_holdings_columns():
    import pandas as pd
    from domains.equity import parser as eq_parser

    zdf = pd.DataFrame([{
        "symbol": "RELIANCE",
        "authorised quantity": 10,
        "average price": 100.0,
        "unrealized p&l": 500.0,
    }])
    holdings, err = eq_parser.parse_holdings_csv(zdf.to_csv(index=False).encode(), "holdings.csv")
    assert err is None
    assert not holdings.empty
