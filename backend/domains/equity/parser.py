"""
domains/equity/parser.py

CSV parser for equity holdings and tradebook uploads.
Auto-detects broker format: Zerodha, Groww, NSDL, or generic.

Zerodha Holdings CSV columns:
  Tradingsymbol, Exchange, ISIN, T1 quantity, Realised quantity,
  Authorised quantity, Opening quantity, Collateral quantity,
  Collateral type, Discrepancy, Average price, Last price,
  Close price, PnL, Day change, Day change percentage

Zerodha Tradebook CSV columns:
  trade_date, exchange, tradingsymbol, transaction_type, quantity,
  average_price, trade_type, order_id, trade_id, series, symbol

Groww Holdings CSV columns:
  Stock Name, NSE Symbol, BSE/NSE, Quantity, Average Price,
  Current Price, Returns, Current Value, Total investment, %Returns
"""

import io
import json
import os
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Upload limits ──────────────────────────────────────────────────────────────
#
# The deployment target is a single uvicorn worker on ~512 MB of RAM, and the parse
# endpoint was unauthenticated with no limits at all: `file.file.read()` on an
# arbitrary body, then `pd.read_excel` with no row cap. An .xlsx is a zip container, so
# a few hundred KB declaring a huge used range decompresses into gigabytes - a
# single-request OOM. These are the guards.

# Largest upload we will read. A Zerodha holdings export for a 500-stock portfolio is
# well under 200 KB; 8 MB is generous for a multi-year tradebook with room to spare.
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# Rows we will parse. Beyond this the file is not a retail portfolio, and the row cap is
# what stops a bomb from being expanded in the first place. Applied as `nrows`, so
# pandas stops reading rather than reading everything and then being truncated.
MAX_ROWS = 20_000

# Extensions we accept, mapped to how they are read. The filename is attacker-supplied,
# so this is an allowlist that decides whether to parse at all - not, as before, a
# suffix test that only chose between two parsers and rejected nothing.
_CSV_EXTENSIONS = (".csv", ".txt")
_EXCEL_EXTENSIONS = (".xlsx", ".xls")


class UploadTooLarge(ValueError):
    """Raised when an upload exceeds MAX_UPLOAD_BYTES."""


class UnsupportedUploadType(ValueError):
    """Raised when a filename does not carry an accepted extension."""


def read_upload(file_obj, filename: str = "") -> bytes:
    """
    Read an upload with a hard byte ceiling.

    Reads MAX_UPLOAD_BYTES + 1 and rejects on overflow, so an oversized body is never
    fully materialised: `.read()` with no argument pulls the whole thing into memory
    before anyone can object to its size.
    """
    _require_supported_extension(filename)
    raw = file_obj.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadTooLarge(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
            "Export just your holdings or tradebook rather than a full account dump."
        )
    if not raw:
        raise UnsupportedUploadType("The uploaded file is empty.")
    return raw


def _require_supported_extension(filename: str) -> str:
    name = (filename or "").lower().strip()
    if name.endswith(_EXCEL_EXTENSIONS):
        return "excel"
    if name.endswith(_CSV_EXTENSIONS):
        return "csv"
    raise UnsupportedUploadType(
        "Unsupported file type. Upload a .csv or .xlsx export from your broker."
    )


def _read_tabular(raw: bytes, filename: str) -> pd.DataFrame:
    """
    Decode an upload into a DataFrame, row-capped.

    Reads from BytesIO rather than `raw.decode(...)` into a StringIO: the decode path
    held the bytes, a full str copy and StringIO's own copy alive simultaneously, ~3x
    the upload's size at peak, with up to 8 of those coexisting on the sync threadpool.
    pandas decodes incrementally from bytes.
    """
    kind = _require_supported_extension(filename)

    if kind == "excel":
        # nrows bounds what openpyxl materialises. Without it, a crafted sheet's
        # declared dimensions decide how much memory this call takes.
        df = pd.read_excel(io.BytesIO(raw), nrows=MAX_ROWS)
    else:
        df = pd.read_csv(
            io.BytesIO(raw),
            nrows=MAX_ROWS,
            encoding="utf-8",
            encoding_errors="replace",
        )

    if len(df) >= MAX_ROWS:
        logger.warning(
            "[equity/parser] upload hit the %d-row cap; extra rows were not read", MAX_ROWS
        )
    return df

# ── Column normalisation maps ──────────────────────────────────────────────────

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "broker_config.json")
try:
    with open(_CONFIG_PATH, "r") as f:
        _BROKER_CONFIG = json.load(f)
except Exception as e:
    logger.error("Failed to load broker_config.json: %s", e)
    _BROKER_CONFIG = {"zerodha": {}, "groww": {}, "generic": {}}

_ZERODHA_HOLDINGS_COLUMNS = _BROKER_CONFIG.get("zerodha", {})
_GROWW_HOLDINGS_COLUMNS = _BROKER_CONFIG.get("groww", {})
_GENERIC_COLUMNS = _BROKER_CONFIG.get("generic", {})
_ZERODHA_TRADEBOOK_COLUMNS = _BROKER_CONFIG.get("zerodha_tradebook", {})

def _clean_preface_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Removes junk header rows (e.g. Zerodha Console Excel exports)."""
    if df.empty:
        return df
    if any(str(c).startswith("Unnamed") for c in df.columns):
        for i in range(min(30, len(df))):
            row_vals = [str(x).lower().strip() for x in df.iloc[i].values]
            if "symbol" in row_vals or "tradingsymbol" in row_vals or "nse symbol" in row_vals:
                # De-duplicate the promoted header. A preface row with a repeated value
                # (or several blanks) otherwise produces duplicate column labels, and
                # `df["symbol"]` then returns a DataFrame instead of a Series - which
                # fails much later, somewhere unrelated.
                promoted = [str(c) for c in df.iloc[i].values]
                seen: dict[str, int] = {}
                unique: list[str] = []
                for name in promoted:
                    if name in seen:
                        seen[name] += 1
                        unique.append(f"{name}_{seen[name]}")
                    else:
                        seen[name] = 0
                        unique.append(name)
                df.columns = unique
                df = df.iloc[i + 1:].reset_index(drop=True)
                break
    return df

def _detect_broker(df: pd.DataFrame) -> str:
    """Auto-detect the broker format from column names."""
    cols = set(str(c).lower().strip() for c in df.columns)
    if ("tradingsymbol" in cols and "pnl" in cols) or ("symbol" in cols and "unrealized p&l" in cols):
        return "zerodha"
    if "stock name" in cols and "nse symbol" in cols:
        return "groww"
    if ("trade_date" in cols and "transaction_type" in cols) or ("trade_date" in cols and "trade_type" in cols):
        return "zerodha_tradebook"
    return "generic"


def _normalize_cols(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Rename columns using a case-insensitive map."""
    rename = {}
    for col in df.columns:
        key = str(col).lower().strip()
        if key in col_map:
            target = col_map[key]
            if target not in rename.values():  # avoid duplicate targets
                rename[col] = target
    return df.rename(columns=rename)


def parse_holdings_csv(raw: bytes, filename: str = "") -> tuple[pd.DataFrame, str | None]:
    """
    Parse a holdings CSV or XLSX from any supported broker.

    Returns (df_holdings, error_message).
    df_holdings columns (standardized):
      symbol, isin, quantity, avg_price, ltp, current_value,
      invested, unrealized_pnl, pnl_pct, day_change, day_change_pct,
      exchange, broker
    """
    try:
        df = _clean_preface_rows(_read_tabular(raw, filename))
    except (UploadTooLarge, UnsupportedUploadType) as e:
        return pd.DataFrame(), str(e)
    except Exception as e:
        # The message the user sees is fixed; the pandas internals go to the log. The
        # previous `f"Could not read CSV: {e}"` put raw parser internals in the response.
        logger.warning("[equity/parser] holdings read failed (%s): %s", filename, e)
        return pd.DataFrame(), (
            "Could not read that file. Check it is an unmodified holdings export "
            "from your broker."
        )

    if df.empty:
        return pd.DataFrame(), "The uploaded file has no rows."

    broker = _detect_broker(df)
    logger.info("[equity/parser] detected broker format: %s (%d rows)", broker, len(df))

    if broker == "zerodha":
        df = _normalize_cols(df, _ZERODHA_HOLDINGS_COLUMNS)
        # Zerodha uses "Realised quantity" for actual held qty if legacy
        if "quantity" not in df.columns and "authorised quantity" in df.columns:
            df = df.rename(columns={"authorised quantity": "quantity"})
    elif broker == "groww":
        df = _normalize_cols(df, _GROWW_HOLDINGS_COLUMNS)
    elif broker == "zerodha_tradebook":
        return pd.DataFrame(), "Please upload a Holdings CSV, not a Tradebook. Use the Tradebook slot for trade history."
    else:
        df = _normalize_cols(df, _GENERIC_COLUMNS)

    required = ["symbol", "quantity", "avg_price"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame(), f"CSV is missing required columns: {', '.join(missing)}. Detected format: {broker}."

    # ── Coerce numeric columns ───────────────────────────────────────────────
    # Only route through strings when the column is not already numeric. The
    # unconditional `.astype(str).str.replace(...)` boxed every value in an already-clean
    # float column into a Python string and back, per column, which was the dominant CPU
    # cost of parsing a large export.
    for col in ["quantity", "avg_price", "ltp", "current_value", "invested",
                "unrealized_pnl", "day_change", "day_change_pct"]:
        if col not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        cleaned = (
            df[col].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("₹", "", regex=False)
            .str.strip()
        )
        df[col] = pd.to_numeric(cleaned, errors="coerce")

    # ── Derive missing columns ───────────────────────────────────────────────
    if "invested" not in df.columns or df["invested"].isna().all():
        df["invested"] = df["quantity"] * df["avg_price"]

    if "current_value" not in df.columns or df["current_value"].isna().all():
        if "ltp" in df.columns:
            df["current_value"] = df["quantity"] * df["ltp"]
        else:
            df["current_value"] = df["invested"]

    if "ltp" not in df.columns or df["ltp"].isna().all():
        if "current_value" in df.columns and "quantity" in df.columns:
            df["ltp"] = df["current_value"] / df["quantity"].replace(0, float("nan"))

    if "unrealized_pnl" not in df.columns or df["unrealized_pnl"].isna().all():
        df["unrealized_pnl"] = df["current_value"] - df["invested"]

    df["pnl_pct"] = (df["unrealized_pnl"] / df["invested"].replace(0, float("nan")) * 100).round(2)

    if "isin" not in df.columns:
        df["isin"] = None

    if "exchange" not in df.columns:
        df["exchange"] = "NSE"

    if "name" not in df.columns:
        df["name"] = df["symbol"]

    # ── Clean up ─────────────────────────────────────────────────────────────
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip().str.replace("-EQ", "")
    df["broker"] = broker
    df = df.dropna(subset=["symbol", "quantity"]).reset_index(drop=True)
    df = df[df["quantity"] > 0].reset_index(drop=True)

    return df, None


def parse_tradebook_csv(raw: bytes, filename: str = "") -> tuple[pd.DataFrame, str | None]:
    """
    Parse a tradebook CSV or XLSX. Returns (df_trades, error_message).
    df_trades columns (standardized):
      date, symbol, type (buy/sell), quantity, price
    """
    try:
        df = _clean_preface_rows(_read_tabular(raw, filename))
    except (UploadTooLarge, UnsupportedUploadType) as e:
        return pd.DataFrame(), str(e)
    except Exception as e:
        logger.warning("[equity/parser] tradebook read failed (%s): %s", filename, e)
        return pd.DataFrame(), (
            "Could not read that tradebook. Check it is an unmodified export from "
            "your broker."
        )

    if df.empty:
        return pd.DataFrame(), "The uploaded tradebook has no rows."

    broker = _detect_broker(df)
    if broker != "zerodha_tradebook":
        return pd.DataFrame(), "This does not look like a Zerodha Tradebook. Expected columns: trade_date, symbol, trade_type."

    df = _normalize_cols(df, _ZERODHA_TRADEBOOK_COLUMNS)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip().str.replace("-EQ", "")
    df["amount"] = df["quantity"] * df["price"]
    df["type"] = df["type"].astype(str).str.upper().str.strip()

    df = df.dropna(subset=["date", "symbol"]).reset_index(drop=True)
    return df, None
