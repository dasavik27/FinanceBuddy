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
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Column normalisation maps ──────────────────────────────────────────────────

_ZERODHA_HOLDINGS_COLUMNS = {
    "tradingsymbol": "symbol",
    "isin": "isin",
    "realised quantity": "quantity",
    "authorised quantity": "quantity",
    "opening quantity": "quantity",
    "average price": "avg_price",
    "last price": "ltp",
    "close price": "close_price",
    "pnl": "unrealized_pnl",
    "day change": "day_change",
    "day change percentage": "day_change_pct",
    "exchange": "exchange",
}

_GROWW_HOLDINGS_COLUMNS = {
    "nse symbol": "symbol",
    "stock name": "name",
    "quantity": "quantity",
    "average price": "avg_price",
    "current price": "ltp",
    "current value": "current_value",
    "total investment": "invested",
    "bse/nse": "exchange",
}

_GENERIC_COLUMNS = {
    "symbol": "symbol",
    "stock": "symbol",
    "scrip": "symbol",
    "isin": "isin",
    "qty": "quantity",
    "quantity": "quantity",
    "shares": "quantity",
    "avg price": "avg_price",
    "avg. price": "avg_price",
    "average price": "avg_price",
    "ltp": "ltp",
    "current price": "ltp",
    "last price": "ltp",
    "invested": "invested",
    "invested value": "invested",
    "current value": "current_value",
    "p&l": "unrealized_pnl",
    "pnl": "unrealized_pnl",
    "gain/loss": "unrealized_pnl",
}


def _detect_broker(df: pd.DataFrame) -> str:
    """Auto-detect the broker format from column names."""
    cols = set(c.lower().strip() for c in df.columns)
    if "tradingsymbol" in cols and "pnl" in cols:
        return "zerodha"
    if "stock name" in cols and "nse symbol" in cols:
        return "groww"
    if "trade_date" in cols and "transaction_type" in cols:
        return "zerodha_tradebook"
    return "generic"


def _normalize_cols(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Rename columns using a case-insensitive map."""
    rename = {}
    for col in df.columns:
        key = col.lower().strip()
        if key in col_map:
            target = col_map[key]
            if target not in rename.values():  # avoid duplicate targets
                rename[col] = target
    return df.rename(columns=rename)


def parse_holdings_csv(raw: bytes) -> tuple[pd.DataFrame, str | None]:
    """
    Parse a holdings CSV from any supported broker.

    Returns (df_holdings, error_message).
    df_holdings columns (standardized):
      symbol, isin, quantity, avg_price, ltp, current_value,
      invested, unrealized_pnl, pnl_pct, day_change, day_change_pct,
      exchange, broker
    """
    try:
        text = raw.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        return pd.DataFrame(), f"Could not read CSV: {e}"

    if df.empty:
        return pd.DataFrame(), "The uploaded CSV is empty."

    broker = _detect_broker(df)
    logger.info("[equity/parser] detected broker format: %s (%d rows)", broker, len(df))

    if broker == "zerodha":
        df = _normalize_cols(df, _ZERODHA_HOLDINGS_COLUMNS)
        # Zerodha uses "Realised quantity" for actual held qty
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
    for col in ["quantity", "avg_price", "ltp", "current_value", "invested",
                "unrealized_pnl", "day_change", "day_change_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "").str.replace("₹", ""), errors="coerce")

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


def parse_tradebook_csv(raw: bytes) -> tuple[pd.DataFrame, str | None]:
    """
    Parse a Zerodha tradebook CSV for realized P&L and transaction history.

    Zerodha Tradebook columns:
      trade_date, exchange, tradingsymbol, transaction_type,
      quantity, average_price, trade_type, order_id, trade_id
    """
    try:
        text = raw.decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        return pd.DataFrame(), f"Could not read Tradebook CSV: {e}"

    if df.empty:
        return pd.DataFrame(), "Tradebook CSV is empty."

    cols = set(c.lower().strip() for c in df.columns)
    if "trade_date" not in cols and "tradingsymbol" not in cols:
        return pd.DataFrame(), "This does not look like a Zerodha Tradebook. Expected columns: trade_date, tradingsymbol, transaction_type."

    rename_map = {
        "trade_date": "date",
        "tradingsymbol": "symbol",
        "transaction_type": "type",
        "quantity": "quantity",
        "average_price": "price",
        "exchange": "exchange",
    }
    rename = {c: rename_map[c.lower().strip()] for c in df.columns if c.lower().strip() in rename_map}
    df = df.rename(columns=rename)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip().str.replace("-EQ", "")
    df["amount"] = df["quantity"] * df["price"]
    df["type"] = df["type"].astype(str).str.upper().str.strip()

    df = df.dropna(subset=["date", "symbol"]).reset_index(drop=True)
    return df, None
