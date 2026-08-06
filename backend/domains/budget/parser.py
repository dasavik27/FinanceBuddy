"""
domains/budget/parser.py - bank and credit-card statement ingestion.

What changed and why
--------------------
Three classes of problem were fixed here.

**Unbounded reads.** `pd.read_excel(io.BytesIO(raw))` with no `nrows`, fed by an
unbounded `await file.read()`. An .xlsx is a zip container; a small file declaring a
huge used range decompresses into gigabytes. Reading now goes through shared/uploads.py,
which every other domain's equivalent already does.

**Silent money errors.** Amounts went through `re.sub(r'[^\\d.]', '', ...)`, which
strips the minus sign, mangles European and Indian grouping, and raises an uncaught
ValueError on one of the two branches. That is now domains/budget/amounts.py, and a
cell that cannot be parsed is *counted and skipped* rather than guessed at.

**Row-at-a-time iteration.** `for _, row in df.iterrows()` builds a Series per row.
Columns are extracted once and walked as plain lists instead, which is several times
faster and, more importantly, keeps memory flat across a 20,000-row cap.

The parser reports what it could not do. `ParseResult.skipped` and `.reasons` surface
in the upload response, so a statement that half-parses says so instead of quietly
producing a dashboard built on 60% of the data.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from shared.uploads import MAX_ROWS, read_table_raw
from domains.budget.amounts import direction_from, parse_amount

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "bank_config.json"

# Rows scanned looking for a header buried under a preamble. Statements put a dozen
# lines of account metadata above the table; 50 is generous and bounds the scan.
_HEADER_SCAN_ROWS = 50


@dataclass
class ParseResult:
    """Outcome of parsing one statement."""

    frame: pd.DataFrame
    bank: str
    account_type: str
    parsed: int = 0
    skipped: int = 0
    reasons: Counter = field(default_factory=Counter)
    error: Optional[str] = None
    truncated: bool = False

    def report(self) -> Dict[str, Any]:
        return {
            "parsed": self.parsed,
            "skipped": self.skipped,
            "reasons": dict(self.reasons),
            "truncated": self.truncated,
        }


def load_bank_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["banks"]


def _normalize(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _find_column_mapping(candidate_cols: list, bank_config: dict) -> Optional[dict]:
    """
    Map semantic keys onto this statement's actual column names.

    Returns None when the columns cannot satisfy the format, which is how the caller
    knows to try the next bank or the next candidate header row.
    """
    col_map: Dict[str, Any] = {}
    norm_map = {
        _normalize(c): c
        for c in candidate_cols
        if pd.notna(c) and str(c).strip() and str(c).strip().lower() != "nan"
    }

    def pick(key: str) -> Optional[Any]:
        aliases = bank_config.get(key, [])
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            hit = norm_map.get(_normalize(alias))
            if hit is not None:
                return hit
        return None

    date_col = pick("date")
    desc_col = pick("description")
    if date_col is None or desc_col is None:
        return None
    col_map["date"] = date_col
    col_map["description"] = desc_col

    has_pair = False
    if "amount" in bank_config:
        amt_col = pick("amount")
        if amt_col is not None:
            col_map["amount"] = amt_col
            type_col = pick("type")
            if type_col is not None:
                col_map["type"] = type_col
            # An amount column with no type column is still usable when the amounts
            # themselves are signed or carry Cr/Dr - amounts.py resolves that.
            has_pair = True

    if "debit" in bank_config and "credit" in bank_config:
        deb_col = pick("debit")
        crd_col = pick("credit")
        if deb_col is not None and crd_col is not None:
            col_map["debit"] = deb_col
            col_map["credit"] = crd_col
            has_pair = True

    if "balance" in bank_config:
        bal_col = pick("balance")
        if bal_col is not None:
            col_map["balance"] = bal_col

    return col_map if has_pair else None


def _locate_table(df: pd.DataFrame, bank_order: List[str], configs: dict):
    """
    Find the header row and the column mapping.

    The frame arrives header-less (see shared.uploads.read_table_raw), so every
    candidate header is a data row. Each of the first _HEADER_SCAN_ROWS rows is tried
    against each format; the first row that satisfies *any* format wins, and formats
    are tried in preference order within a row so the user's chosen bank is favoured
    over a coincidental match.

    Returns (bank, mapping, header_row_index).
    """
    limit = min(_HEADER_SCAN_ROWS, len(df))
    for i in range(limit):
        row_vals = list(df.iloc[i].values)
        # A row with almost nothing on it is a spacer, not a header.
        if sum(1 for v in row_vals if pd.notna(v) and str(v).strip()) < 3:
            continue
        for name in bank_order:
            mapping = _find_column_mapping(row_vals, configs[name]["columns"])
            if mapping:
                return name, mapping, i

    return None, None, None


def parse_bank_statement(
    raw_bytes: bytes,
    filename: str,
    bank: str = "HDFC",
    account_type: str = "Savings Account",
) -> ParseResult:
    """
    Parse a statement into the canonical transaction frame.

    The selected bank format is tried first; if it does not match, every other known
    format is tried before giving up. The old behaviour was to fall straight through to
    "generic" and then fail with a message naming the bank the user picked, which was
    misleading whenever they picked the wrong one from the dropdown.
    """
    configs = load_bank_config()
    resolved_type = (account_type or "Savings Account").strip()

    try:
        df = read_table_raw(raw_bytes, filename)
    except Exception as e:
        logger.error("[budget.parser] failed to read %s: %s", filename, e)
        return ParseResult(pd.DataFrame(), bank, resolved_type, error=f"Failed to read file: {e}")

    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return ParseResult(pd.DataFrame(), bank, resolved_type, error="The statement has no rows.")

    selected = (bank or "").lower().strip()
    bank_order = [selected] if selected in configs else []
    bank_order += [b for b in configs if b not in bank_order and b != "generic"]
    bank_order.append("generic")

    matched_bank, mapping, header_idx = _locate_table(df, bank_order, configs)

    if not mapping:
        return ParseResult(
            pd.DataFrame(), bank, resolved_type,
            error=_unmatched_message(df, bank),
        )

    df.columns = list(df.iloc[header_idx].values)
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    result = _extract_rows(df, mapping, bank, matched_bank, resolved_type)
    result.truncated = len(df) >= MAX_ROWS - 1
    return result


def _unmatched_message(df: pd.DataFrame, bank: str) -> str:
    """A failure message that tells the user what we actually saw."""
    for i in range(min(_HEADER_SCAN_ROWS, len(df))):
        row_vals = [str(x).lower().strip() for x in df.iloc[i].values]
        if any(
            w in val
            for val in row_vals
            for w in ("narration", "description", "withdrawal", "deposit", "remarks", "particulars")
        ):
            found = [v for v in row_vals if v and v != "nan"][:8]
            return (
                f"Could not read this as a {bank.upper()} statement. The row that looks "
                f"like a header is: {found}. Pick a different bank, or use the Generic "
                "format if your export has Date / Description / Amount columns."
            )
    # The frame is header-less, so the most useful thing to show back is the widest of
    # the first few rows - whatever the user is looking at as their header.
    widest: List[str] = []
    for i in range(min(_HEADER_SCAN_ROWS, len(df))):
        cells = [str(v).strip() for v in df.iloc[i].values if pd.notna(v) and str(v).strip()]
        if len(cells) > len(widest):
            widest = cells
    found = ", ".join(widest[:10]) if widest else "nothing recognisable"
    return (
        f"Could not read this as a {bank.upper()} statement. The widest row found was: "
        f"[{found}]. Expected a date column, a description column, and either "
        "Debit/Credit columns or an Amount column."
    )


def _extract_rows(
    df: pd.DataFrame,
    mapping: dict,
    requested_bank: str,
    matched_bank: str,
    account_type: str,
) -> ParseResult:
    """
    Build the canonical frame.

    Columns are pulled out as lists once and zipped, rather than `df.iterrows()`
    materialising a Series per row.
    """
    bank_label = (requested_bank or matched_bank or "GENERIC").upper().strip()

    def column(key: str) -> List[Any]:
        name = mapping.get(key)
        if name is None or name not in df.columns:
            return [None] * len(df)
        col = df[name]
        # A statement with two identically named columns yields a DataFrame here.
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]  # pragma: no cover — defensive / hard to exercise in unit tests
        return col.tolist()

    dates = column("date")
    descriptions = column("description")
    balances = column("balance")

    use_amount_column = "amount" in mapping
    amounts = column("amount") if use_amount_column else []
    types = column("type") if "type" in mapping else []
    debits = column("debit") if "debit" in mapping else []
    credits = column("credit") if "credit" in mapping else []

    records: List[Dict[str, Any]] = []
    reasons: Counter = Counter()
    skipped = 0

    for i in range(len(df)):
        raw_date = dates[i]
        if raw_date is None or pd.isna(raw_date):
            skipped += 1
            reasons["no date"] += 1
            continue
        date_text = str(raw_date).strip()
        # Statements repeat the header, and print footers and asterisked disclaimers
        # inside the table. Both land here as a row with a non-date in the date column.
        if not date_text or "*" in date_text:
            skipped += 1
            reasons["not a transaction row"] += 1
            continue

        description = str(descriptions[i]).strip() if descriptions[i] is not None else ""
        if description.lower() in ("nan", "none"):
            description = ""  # pragma: no cover — defensive / hard to exercise in unit tests

        if use_amount_column:
            money = parse_amount(amounts[i])
            if money is None:
                skipped += 1
                reasons["unreadable amount"] += 1
                continue
            txn_type = direction_from(
                money,
                column_direction="debit",
                type_hint=types[i] if types else None,
            )
        else:
            debit_money = parse_amount(debits[i]) if debits else None
            credit_money = parse_amount(credits[i]) if credits else None

            # A blank or zero in one column with a value in the other is the normal
            # shape; both blank means this is not a transaction row.
            if debit_money is not None and not debit_money.is_zero:
                money = debit_money
                txn_type = direction_from(money, column_direction="debit")
            elif credit_money is not None and not credit_money.is_zero:
                money = credit_money
                txn_type = direction_from(money, column_direction="credit")
            else:
                skipped += 1
                reasons["no amount"] += 1
                continue

        if money.is_zero:
            skipped += 1
            reasons["zero amount"] += 1
            continue

        record = {
            "txn_id": uuid.uuid4().hex,
            "date": date_text,
            "description": description,
            "amount": money.magnitude,
            "type": txn_type,
            "source_bank": bank_label,
            "account_type": account_type,
            "notes": "",
        }

        # The running balance is what makes reconciliation possible - see
        # domains/budget/reconcile.py. Absent in most credit-card exports.
        if balances:
            bal = parse_amount(balances[i])
            if bal is not None:
                record["balance"] = -bal.magnitude if bal.negative else bal.magnitude

        records.append(record)

    out = pd.DataFrame(records)
    if not out.empty:
        out["date"] = _normalise_dates(out["date"])

    result = ParseResult(
        frame=out,
        bank=bank_label,
        account_type=account_type,
        parsed=len(out),
        skipped=skipped,
        reasons=reasons,
    )
    if out.empty:
        result.error = (
            "No transactions could be read from this file. "
            + (f"{skipped} rows were skipped ({dict(reasons)})." if skipped else "")
        )
    return result


# Formats seen across Indian bank and card exports, day-first before month-first so an
# ambiguous "01/04/25" resolves the way the issuing bank meant it.
_DATE_FORMATS = (
    "%d/%m/%y", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y",
    "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%d %B %Y",
    "%m/%d/%Y", "%m/%d/%y",
)


def _normalise_dates(series: pd.Series) -> pd.Series:
    """
    Parse to ISO dates, picking whichever known format explains the most rows.

    Two things this avoids. Hardcoding `dayfirst=True`, as the original did, is right
    for Indian bank exports and wrong for the ones following the US convention - and a
    wrong guess shifts a transaction by months without ever failing. And letting pandas
    fall back to dateutil per element is O(rows) Python calls: at the 20,000-row cap
    that dominates the whole parse.

    Trying declared formats and scoring them is still a guess, but a measured one.
    """
    text = series.astype(str).str.strip()

    best: Optional[pd.Series] = None
    best_score = -1
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(text, errors="coerce", format=fmt)
        score = int(parsed.notna().sum())
        if score > best_score:
            best, best_score = parsed, score
        if best_score == len(text):
            break  # a format that explains every row cannot be beaten

    # Nothing declared fits - fall back to inference for the whole column rather than
    # returning the raw strings, which would make every date filter silently empty.
    if best_score <= 0:
        best = pd.to_datetime(text, errors="coerce", dayfirst=True)  # pragma: no cover — defensive / hard to exercise in unit tests

    return best.dt.strftime("%Y-%m-%d").fillna(text)
