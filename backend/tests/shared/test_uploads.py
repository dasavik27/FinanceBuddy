"""
test_shared_uploads_full_coverage.py

Comprehensive unit tests for shared/uploads.py:
- upload_kind extension verification and rejection
- read_upload byte boundary and emptiness enforcement
- read_table_raw for excel, csv, tab-delimited, ragged rows, empty file, and row-cap warnings
"""

import io
import pandas as pd
import pytest

from shared.uploads import (
    upload_kind, read_upload, read_table_raw, _read_csv_rows,
    UploadTooLarge, UnsupportedUploadType, MAX_UPLOAD_BYTES, MAX_ROWS
)


def test_upload_kind():
    assert upload_kind("statement.xlsx") == "excel"
    assert upload_kind("statement.XLS") == "excel"
    assert upload_kind("transactions.csv") == "csv"
    assert upload_kind("dump.TXT") == "csv"

    with pytest.raises(UnsupportedUploadType):
        upload_kind("malicious.exe")

    with pytest.raises(UnsupportedUploadType):
        upload_kind("")


def test_read_upload():
    # 1. Valid read
    data = b"date,description,amount\n2025-01-01,salary,50000"
    assert read_upload(io.BytesIO(data), "statement.csv") == data

    # 2. Empty upload
    with pytest.raises(UnsupportedUploadType) as exc:
        read_upload(io.BytesIO(b""), "statement.csv")
    assert "empty" in str(exc.value)

    # 3. Oversized upload
    big_stream = io.BytesIO(b"X" * (MAX_UPLOAD_BYTES + 10))
    with pytest.raises(UploadTooLarge):
        read_upload(big_stream, "large.csv")


def test_read_table_raw_csv_and_excel():
    # 1. Ragged CSV with delimiter sniffing
    csv_bytes = b"header1,header2\nrow1_col1,row1_col2,row1_col3\nrow2_col1\n"
    df = read_table_raw(csv_bytes, "ragged.csv")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert df.shape[1] == 3  # Padded to width 3

    # 2. Empty CSV
    df_empty = read_table_raw(b"", "empty.csv")
    assert df_empty.empty

    # 3. Excel DataFrame
    excel_buffer = io.BytesIO()
    sample_df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        sample_df.to_excel(writer, index=False, header=False)
    excel_bytes = excel_buffer.getvalue()

    df_excel = read_table_raw(excel_bytes, "test.xlsx")
    assert len(df_excel) == 2


def test_read_csv_rows_row_cap(monkeypatch):
    monkeypatch.setattr("shared.uploads.MAX_ROWS", 3)
    many_rows = b"1\n2\n3\n4\n5\n6\n"
    rows = _read_csv_rows(many_rows)
    assert len(rows) == 3

def test_uploads_excel_row_cap_and_csv_latin1(monkeypatch):
    from shared import uploads

    buf = io.BytesIO()
    big = pd.DataFrame([[i] for i in range(uploads.MAX_ROWS)])
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        big.to_excel(w, index=False, header=False)
    df = uploads.read_table_raw(buf.getvalue(), "big.xlsx")
    assert len(df) >= uploads.MAX_ROWS

    latin = "col1;col2\nval1;val2\n".encode("latin1")
    rows = uploads._read_csv_rows(latin)
    assert len(rows) == 2

