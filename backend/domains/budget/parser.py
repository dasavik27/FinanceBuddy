import json
import logging
import re
from pathlib import Path
import pandas as pd
import io
import uuid

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "bank_config.json"

def load_bank_config():
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)["banks"]

def _normalize(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(s).lower())

def _find_column_mapping(candidate_cols: list, bank_config: dict) -> dict | None:
    """
    Given a list of column names from the statement and a bank configuration,
    returns a dictionary mapping semantic keys ('date', 'description', 'debit', 'credit', 'amount', 'type')
    to the actual column names in the file, or None if the columns don't satisfy the requirements.
    """
    col_map = {}
    norm_map = {_normalize(c): c for c in candidate_cols if pd.notna(c) and str(c).strip() and str(c).lower() != 'nan'}
    
    # 1. Date
    date_aliases = bank_config.get("date", [])
    if isinstance(date_aliases, str):
        date_aliases = [date_aliases]
    date_col = next((norm_map[_normalize(alias)] for alias in date_aliases if _normalize(alias) in norm_map), None)
    if not date_col:
        return None
    col_map["date"] = date_col

    # 2. Description
    desc_aliases = bank_config.get("description", [])
    if isinstance(desc_aliases, str):
        desc_aliases = [desc_aliases]
    desc_col = next((norm_map[_normalize(alias)] for alias in desc_aliases if _normalize(alias) in norm_map), None)
    if not desc_col:
        return None
    col_map["description"] = desc_col

    # 3. Amounts (debit/credit or amount/type)
    has_amount_type = False
    has_debit_credit = False

    if "amount" in bank_config:
        amt_aliases = bank_config["amount"]
        if isinstance(amt_aliases, str):
            amt_aliases = [amt_aliases]
        amt_col = next((norm_map[_normalize(alias)] for alias in amt_aliases if _normalize(alias) in norm_map), None)
        if amt_col:
            col_map["amount"] = amt_col
            type_aliases = bank_config.get("type", [])
            if isinstance(type_aliases, str):
                type_aliases = [type_aliases]
            type_col = next((norm_map[_normalize(alias)] for alias in type_aliases if _normalize(alias) in norm_map), None)
            if type_col:
                col_map["type"] = type_col
                has_amount_type = True

    if "debit" in bank_config and "credit" in bank_config:
        deb_aliases = bank_config["debit"]
        if isinstance(deb_aliases, str):
            deb_aliases = [deb_aliases]
        crd_aliases = bank_config["credit"]
        if isinstance(crd_aliases, str):
            crd_aliases = [crd_aliases]
            
        deb_col = next((norm_map[_normalize(alias)] for alias in deb_aliases if _normalize(alias) in norm_map), None)
        crd_col = next((norm_map[_normalize(alias)] for alias in crd_aliases if _normalize(alias) in norm_map), None)
        
        if deb_col and crd_col:
            col_map["debit"] = deb_col
            col_map["credit"] = crd_col
            has_debit_credit = True

    if not (has_debit_credit or has_amount_type):
        return None

    return col_map

def parse_bank_statement(raw_bytes: bytes, filename: str, bank: str = "HDFC", account_type: str = "Savings Account") -> tuple[pd.DataFrame, str | None]:
    try:
        if filename.lower().endswith(".csv"):
            try:
                df = pd.read_csv(io.BytesIO(raw_bytes))
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(raw_bytes), encoding="latin1")
        elif filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls"):
            df = pd.read_excel(io.BytesIO(raw_bytes))
        else:
            return pd.DataFrame(), "Unsupported file format. Please upload CSV, XLSX, or XLS."
    except Exception as e:
        logger.error(f"[budget.parser] failed to read file: {e}")
        return pd.DataFrame(), f"Failed to parse file: {e}"

    df = df.dropna(how="all").dropna(axis=1, how="all")
    
    bank_configs = load_bank_config()
    
    # Use explicitly selected bank format; fallback to generic if custom bank name
    bank_key = bank.lower().strip()
    if bank_key in bank_configs:
        bank_order = [bank_key]
    else:
        bank_order = ["generic"]

    matched_bank = None
    matched_mapping = None
    header_idx = None

    # 1. Check if top-level columns already match
    top_cols = list(df.columns)
    for b_name in bank_order:
        mapping = _find_column_mapping(top_cols, bank_configs[b_name]["columns"])
        if mapping:
            matched_bank = b_name
            matched_mapping = mapping
            break

    # 2. Scan rows for metadata/disclaimer lines preceding headers
    if not matched_bank:
        for i in range(min(50, len(df))):
            row_vals = list(df.iloc[i].values)
            for b_name in bank_order:
                mapping = _find_column_mapping(row_vals, bank_configs[b_name]["columns"])
                if mapping:
                    matched_bank = b_name
                    matched_mapping = mapping
                    header_idx = i
                    break
            if matched_bank:
                break

    if matched_bank and header_idx is not None:
        df.columns = list(df.iloc[header_idx].values)
        df = df.iloc[header_idx + 1:].reset_index(drop=True)

    if not matched_bank or not matched_mapping:
        date_row = None
        for i in range(min(50, len(df))):
            row_vals = [str(x).lower().strip() for x in df.iloc[i].values]
            if any(w in val for val in row_vals for w in ["narration", "description", "withdrawal", "deposit", "remarks"]):
                date_row = [v for v in row_vals if v and v != "nan"]
                break
        
        found_cols = ", ".join(str(c) for c in df.columns[:10])
        if date_row:
            msg = f"Could not parse using {bank.upper()} format. Found potential header row: {date_row}"
        else:
            msg = f"Could not parse using {bank.upper()} format. Found columns: [{found_cols}]."
        return pd.DataFrame(), msg

    # Use explicit bank name and account type
    final_bank = bank.upper().strip() if bank else matched_bank.upper()
    resolved_account_type = account_type.strip() if account_type else "Savings Account"

    result = []
    for _, row in df.iterrows():
        date_val = row.get(matched_mapping["date"])
        if pd.isna(date_val) or str(date_val).strip() == "" or "*" in str(date_val):
            continue
            
        date = str(date_val).strip()
        description = str(row.get(matched_mapping["description"], "")).strip()
        
        amount = 0.0
        txn_type = "debit"
        
        if "amount" in matched_mapping and "type" in matched_mapping:
            amt_val = row.get(matched_mapping["amount"])
            if pd.notna(amt_val):
                clean_str = re.sub(r'[^\d.]', '', str(amt_val))
                if clean_str:
                    amount = float(clean_str)
            type_val = str(row.get(matched_mapping["type"])).lower().strip()
            txn_type = "credit" if "cr" in type_val else "debit"
        else:
            debit_val = row.get(matched_mapping.get("debit", ""))
            credit_val = row.get(matched_mapping.get("credit", ""))
            
            try:
                if not pd.isna(debit_val) and str(debit_val).strip() and str(debit_val).strip() != "0":
                    val_str = re.sub(r'[^\d.]', '', str(debit_val))
                    if val_str:
                        amount = float(val_str)
                        txn_type = "debit"
                elif not pd.isna(credit_val) and str(credit_val).strip() and str(credit_val).strip() != "0":
                    val_str = re.sub(r'[^\d.]', '', str(credit_val))
                    if val_str:
                        amount = float(val_str)
                        txn_type = "credit"
            except ValueError:
                continue
            
        if amount == 0:
            continue
                
        result.append({
            "txn_id": uuid.uuid4().hex,
            "date": date,
            "description": description,
            "amount": amount,
            "type": txn_type,
            "source_bank": final_bank,
            "account_type": resolved_account_type,
            "notes": ""
        })
        
    out_df = pd.DataFrame(result)
    
    if not out_df.empty:
        try:
            out_df["date"] = pd.to_datetime(out_df["date"], dayfirst=True)
            out_df["date"] = out_df["date"].dt.strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"[budget.parser] failed to parse dates: {e}")
        
    return out_df, None
