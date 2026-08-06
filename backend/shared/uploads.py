"""
shared/uploads.py - bounded reading of user-supplied spreadsheet uploads.

Why this is shared rather than per-domain
-----------------------------------------
domains/equity/parser.py grew these guards first, after an unauthenticated parse
endpoint was found calling `file.read()` on an arbitrary body and then
`pd.read_excel` with no row cap. The budget domain then landed with the same two
lines and none of the guards, which is the failure mode a per-domain copy invites:
the next domain copies the *shape* of the code and not its protections.

The reasoning, restated because it is the whole point of the module:

- An `.xlsx` is a zip container. A few hundred KB declaring a huge used range
  decompresses into gigabytes, so the byte ceiling alone does not bound memory -
  the row cap does, and it has to be applied as `nrows` so pandas stops reading
  rather than reading everything and then being truncated.
- `.read()` with no argument materialises the whole body before anyone can object
  to its size, so the ceiling is enforced by reading `limit + 1` and checking.
- The filename is attacker-supplied. The extension check is an allowlist deciding
  whether to parse at all, not a switch choosing between two parsers.

Equity keeps its own copy of these constants for now; this module is the one new
code should use. The behaviour is deliberately identical so the two can be merged
without a semantic change.
"""

from __future__ import annotations

import csv
import io
import logging

import pandas as pd

# Bank CSVs can carry a very long merged description cell. The default limit is 128 KB
# and a hit raises mid-parse; the cap here is still far below the upload ceiling.
csv.field_size_limit(1_000_000)

logger = logging.getLogger(__name__)

# Largest upload we will read. A year of bank statements for one account is a few
# hundred KB of CSV; 8 MB matches the ceiling every other domain already enforces.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# Rows we will parse. Beyond this it is not a retail bank statement. This is the
# cap that actually bounds memory for a zip bomb, because it stops the expansion.
MAX_ROWS = 20_000

_CSV_EXTENSIONS = (".csv", ".txt")
_EXCEL_EXTENSIONS = (".xlsx", ".xls")


class UploadTooLarge(ValueError):
    """Raised when an upload exceeds MAX_UPLOAD_BYTES."""


class UnsupportedUploadType(ValueError):
    """Raised when a filename does not carry an accepted extension."""


def upload_kind(filename: str) -> str:
    """
    "excel" or "csv" for an accepted filename; raises otherwise.

    Checked before reading a single byte, so an unsupported upload costs nothing.
    """
    name = (filename or "").lower().strip()
    if name.endswith(_EXCEL_EXTENSIONS):
        return "excel"
    if name.endswith(_CSV_EXTENSIONS):
        return "csv"
    raise UnsupportedUploadType(
        "Unsupported file type. Upload a .csv, .xls or .xlsx statement "
        "exported from your bank."
    )


def read_upload(file_obj, filename: str = "") -> bytes:
    """
    Read an upload with a hard byte ceiling, rejecting unsupported types first.

    `file_obj` is anything with a blocking `.read(n)` - `UploadFile.file`, an open
    file, a BytesIO. Note this is the *sync* handle: `await UploadFile.read()` has
    no size argument and so cannot be bounded.
    """
    upload_kind(filename)
    raw = file_obj.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadTooLarge(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            "Export a single account's statement rather than a full account dump."
        )
    if not raw:
        raise UnsupportedUploadType("The uploaded file is empty.")
    return raw


def read_table_raw(raw: bytes, filename: str) -> pd.DataFrame:
    """
    Decode an upload into a row-capped, *header-less* DataFrame with integer columns.

    Every cell comes back as read; nothing is promoted to a header and no dtype is
    inferred from a row that might be a preamble. Locating the real header is the
    caller's job, because only the caller knows which column names to look for.

    Why not `pd.read_csv(header=0)`
    -------------------------------
    Bank CSVs routinely carry a preamble - "Statement of account", an account number,
    a blank line - above the transaction table, and those lines have a different field
    count than the table does. `header=0` then takes the preamble's first line as the
    header, and pandas treats every wider data row as malformed: with `on_bad_lines`
    raising it fails outright, and with it set to "skip" it silently discards the
    entire transaction table and returns the preamble. That second failure mode is the
    one worth spelling out - it produces an empty parse with no error.

    Reading through a TextIOWrapper over BytesIO rather than `raw.decode()` keeps the
    decode incremental: the decode-first path holds the bytes, a full str copy and
    StringIO's own copy alive at once, roughly 3x the upload at peak, with up to
    FINANCEBUDDY_SYNC_CONCURRENCY of those coexisting on the threadpool.
    """
    kind = upload_kind(filename)

    if kind == "excel":
        # nrows bounds what openpyxl materialises. Without it, a crafted sheet's
        # declared dimensions decide how much memory this call takes.
        df = pd.read_excel(io.BytesIO(raw), nrows=MAX_ROWS, header=None)
        if len(df) >= MAX_ROWS:
            logger.warning("[uploads] %s hit the %d-row cap", filename, MAX_ROWS)
        return df

    rows = _read_csv_rows(raw)
    if not rows:
        return pd.DataFrame()

    width = max(len(r) for r in rows)
    padded = [r + [None] * (width - len(r)) for r in rows]
    return pd.DataFrame(padded, columns=list(range(width)))


def _read_csv_rows(raw: bytes) -> "list[list]":
    """
    Row-capped CSV rows, tolerating ragged lines and an unknown delimiter.

    The stdlib csv reader is used rather than pandas precisely because ragged rows are
    normal here and it simply returns them at their own length.
    """
    for encoding in ("utf-8", "latin1"):
        stream = io.TextIOWrapper(io.BytesIO(raw), encoding=encoding, errors="replace", newline="")
        try:
            sample = stream.read(8192)
            stream.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel  # a single-column file sniffs as nothing

            rows: "list[list]" = []
            for i, row in enumerate(csv.reader(stream, dialect)):
                if i >= MAX_ROWS:
                    logger.warning("[uploads] CSV hit the %d-row cap", MAX_ROWS)
                    break
                rows.append(row)
            return rows
        except UnicodeDecodeError:  # pragma: no cover — defensive / hard to exercise in unit tests
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        finally:
            stream.detach()
    return []  # pragma: no cover — defensive / hard to exercise in unit tests
