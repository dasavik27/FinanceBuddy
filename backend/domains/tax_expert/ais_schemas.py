from typing import List, Dict
import re
import pandas as pd

class AISStructureChangedError(Exception):
    """Raised when the AIS PDF table structure does not match expected Golden Schemas."""
    def __init__(self, message: str, diff: dict = None):
        super().__init__(message)
        self.diff = diff or {}

class AISUnknownCodeError(Exception):
    """Raised when an unknown Information Code is detected in the AIS."""
    def __init__(self, code: str, source: str = ""):
        super().__init__(f"New AIS Information Code Detected: {code}. Please contact support to add schema.")
        self.code = code
        self.source = source

# Golden Schemas for Validation
GOLDEN_SCHEMAS = {
    "salary_tds": [
        "SR. NO.", "QUARTER", "DATE OF PAYMENT/CREDIT",
        "AMOUNT PAID/CREDITED", "TDS DEDUCTED", "TDS DEPOSITED", "STATUS"
    ],
    "dividend_sft": [
        "SR. NO.", "REPORTED ON", "DIVIDEND AMOUNT", "STATUS"
    ],
    "salary_annexure": [
        "SR. NO.", "GROSS SALARY"
    ],
    "dividend_tds": [
        "SR. NO.", "QUARTER", "DATE OF PAYMENT/CREDIT",
        "AMOUNT PAID/CREDITED", "TDS DEDUCTED", "TDS DEPOSITED", "STATUS"
    ],
    "interest_sb": [
        "SR. NO.", "REPORTED ON", "ACCOUNT NUMBER",
        "ACCOUNT TYPE", "INTEREST AMOUNT", "STATUS"
    ],
    "interest_td": [
        "SR. NO.", "REPORTED ON", "ACCOUNT NUMBER",
        "ACCOUNT TYPE", "INTEREST AMOUNT", "STATUS"
    ],
    "capital_gains_equity": [
        "SR. NO.", "DATE OF SALE/ TRANSFER", "SECURITY NAME (SECURITY CODE)",
        "SECURITY CLASS", "DEBIT TYPE", "CREDIT TYPE", "ASSET TYPE", "QUANTITY",
        "SALE PRICE PER UNIT", "SALES CONSIDERATION", "COST OF ACQUISITION",
        "UNIT FMV", "FAIR MARKET VALUE", "INDEXED COST OF ACQUISITION", "STATUS"
    ],
    "capital_gains_mf": [
        "SR. NO.", "AMC NAME (CODE)", "DATE OF SALE/ TRANSFER", "SECURITY CLASS",
        "SECURITY NAME (SECURITY CODE)", "DEBIT TYPE", "CREDIT TYPE", "ASSET TYPE",
        "QUANTITY", "SALE PRICE PER UNIT", "SALES CONSIDERATION", "STT",
        "COST OF ACQUISITION", "UNIT FMV", "FAIR MARKET VALUE", "INDEXED COST OF ACQUISITION", "STATUS"
    ],
    "capital_gains_no_cost": [
        "SR. NO.", "DATE OF SALE/ TRANSFER", "SECURITY NAME (SECURITY CODE)",
        "SECURITY CLASS", "DEBIT TYPE", "CREDIT TYPE", "ASSET TYPE", "QUANTITY",
        "SALE PRICE PER UNIT", "SALES CONSIDERATION", "STATUS"
    ],
    "purchase_mf": [
        "SR. NO.", "QUARTER", "CLIENT ID", "AMC NAME (CODE)", "HOLDER FLAG",
        "TOTAL PURCHASE AMOUNT", "TOTAL SALES VALUE", "STATUS"
    ],
    "real_estate": [
        "SR. NO.", "DATE OF TRANSACTION", "PROPERTY DESCRIPTION", 
        "TRANSACTION VALUE", "STATUS"
    ],
    "tax_payments": [
        "SR. NO.", "FINANCIAL YEAR", "MAJOR HEAD", "MINOR HEAD", "TAX (A)", 
        "SURCHARGE (B)", "EDUCATION CESS (C)", "OTHERS (D)", "TOTAL (A+B+C+D)", 
        "BSR CODE", "DATE OF DEPOSIT", "CHALLAN SERIAL NUMBER", 
        "CHALLAN IDENTIFICATION NUMBER"
    ],
    "refunds": [
        "SR. NO.", "FINANCIAL YEAR", "MODE", "NATURE OF REFUND", 
        "REFUND AMOUNT", "DATE OF PAYMENT"
    ]
}

def clean_header(header: str) -> str:
    """Normalize headers by stripping all non-alphanumeric chars to handle PDF wrapping artifacts."""
    if pd.isna(header) or not str(header):
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(header).upper())

def validate_schema(table_name: str, extracted_headers: List[str]) -> bool:
    if table_name not in GOLDEN_SCHEMAS:
        return True 

    expected = [re.sub(r'[^A-Z0-9]', '', h.upper()) for h in GOLDEN_SCHEMAS[table_name]]
    actual = [clean_header(h) for h in extracted_headers]
    
    missing = [col for exp_idx, col in enumerate(GOLDEN_SCHEMAS[table_name]) if expected[exp_idx] not in actual]
    
    if missing:
        raise AISStructureChangedError(
            f"AIS Structure Changed! The Income Tax Department has modified the '{table_name}' table format.",
            diff={"missing_columns": missing, "found_columns": actual, "expected": expected}
        )
    return True
