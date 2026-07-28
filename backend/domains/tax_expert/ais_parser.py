"""
core/ais_parser.py

Annual Information Statement (AIS) PDF Parser
=============================================
Extracts structured financial data from the Income Tax Department's AIS PDF.
This version uses camelot-py (Lattice mode) for strict table extraction and schema validation.
"""

import os
import re
import logging
import tempfile
import pandas as pd
from datetime import datetime

# Optional imports for PDF processing
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import camelot
except ImportError:
    camelot = None

from .ais_schemas import validate_schema, AISStructureChangedError, AISUnknownCodeError, clean_header

logger = logging.getLogger(__name__)


def _clean_amount(val) -> float:
    if pd.isna(val) or not str(val).strip():
        return 0.0
    val_str = str(val).strip().replace(',', '').replace('₹', '').replace(' ', '')
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def _parse_date(val) -> str:
    if pd.isna(val) or not str(val).strip():
        return ""
    val_str = str(val).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val_str


def parse_ais_pdf(raw_bytes: bytes) -> dict:
    """
    Parse an AIS PDF and return structured financial data using Camelot for tables.
    """
    if not camelot:
        return {"error": "AIS PDF parsing not available - install camelot-py and pdfplumber"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        import pypdf
        full_text = ""
        with open(tmp_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                full_text += (page.extract_text() or "") + "\n"

        personal = _extract_personal(full_text)

        # Extract all tables using Camelot Lattice mode
        tables = camelot.read_pdf(tmp_path, pages='all', flavor='lattice')
        
        result = {
            "personal": personal,
            "salary": {"gross": 0, "tds_deducted": 0, "employer": "", "quarterly": []},
            "dividends": [],
            "interest_savings": [],
            "interest_deposits": [],
            "interest_others": [],
            "capital_gains_equity": [],
            "capital_gains_mf_equity": [],
            "capital_gains_mf_other": [],
            "cg_real_estate": [],
            "cg_unlisted": [],
            "cg_bonds_gold": [],
            "misc_income": [],
            "tax_payments": [],
            "refunds": [],
            "salary_annexure": {"gross_salary": 0, "perquisites": 0, "profits_lieu": 0},
            "tds_total": 0.0,
            "fy": personal.get("fy", "2025-26")
        }

        current_info_code = None
        current_info_source = ""

        for table in tables:
            df = table.df
            if df.empty or len(df.columns) < 2:
                continue
            
            # The first row is usually the header in Camelot lattice
            raw_headers = df.iloc[0].astype(str).tolist()
            headers = [clean_header(h) for h in raw_headers]
            
            # 0. Check for standalone tables that don't have SFT codes (Tax Payments, Refunds)
            if "TOTALABCD" in headers and "CHALLANSERIALNUMBER" in headers:
                validate_schema("tax_payments", raw_headers)
                _process_tax_payments(df, headers, result)
                current_info_code = None
                continue
            elif "NATUREOFREFUND" in headers and "REFUNDAMOUNT" in headers:
                validate_schema("refunds", raw_headers)
                _process_refunds(df, headers, result)
                current_info_code = None
                continue
                
            # 1. Check if this is a Summary Table containing the Information Code
            if "INFORMATIONCODE" in headers:
                code_raw = str(df.iloc[1][df.columns[headers.index("INFORMATIONCODE")]]).strip()
                source_raw = str(df.iloc[1][df.columns[headers.index("INFORMATIONSOURCE")]]).strip() if "INFORMATIONSOURCE" in headers else ""
                
                match = re.search(r'(SFT-\d+(?:-[A-Z]+(?:\([A-Z]\))?)?|TDS-\d+[A-Z]?)', code_raw, re.IGNORECASE)
                if match:
                    current_info_code = match.group(1).upper()
                else:
                    current_info_code = code_raw.split()[0].upper() if code_raw else None
                    
                current_info_source = source_raw
                
                # Check if this table ALSO contains the child table (merged by Camelot)
                if len(df) > 2:
                    child_raw_headers = df.iloc[2].astype(str).tolist()
                    child_headers = [clean_header(h) for h in child_raw_headers]
                    # We can slice df so that it looks exactly like a standalone child table
                    df = df.iloc[2:].reset_index(drop=True)
                    headers = child_headers
                    raw_headers = child_raw_headers
                    # DO NOT continue. Let it fall through to "2. If we have a stored Information Code..."
                else:
                    continue # Move to the next table which is the child
            
            # 2. If we have a stored Information Code, process this Child Table
            if current_info_code:
                code = current_info_code
                # We intentionally DO NOT reset current_info_code here. 
                # This allows multi-page child tables to continue using the same code 
                # until a new Summary Table or Standalone Table explicitly overwrites it.
                
                if code.startswith("SFT-015"):
                    if "DIVIDENDAMOUNT" not in headers: current_info_code = None; continue
                    validate_schema("dividend_sft", raw_headers)
                    _process_dividend_sft(df, headers, result)
                elif code.startswith("TDS-194") and not code.startswith("TDS-194A") and not code.startswith("TDS-194IA"):
                    if "AMOUNTPAIDCREDITED" not in headers: current_info_code = None; continue
                    validate_schema("dividend_tds", raw_headers)
                    _process_dividend_tds(df, headers, result)
                elif code.startswith("TDS-192"):
                    if "AMOUNTPAIDCREDITED" not in headers and "TDSDEDUCTED" not in headers: current_info_code = None; continue
                    validate_schema("salary_tds", raw_headers)
                    _process_salary_tds(df, headers, result, current_info_source)
                elif code.startswith("TDS-ANN.II-SAL") or code.startswith("TDS-ANN"):
                    if "GROSSSALARY" not in headers: current_info_code = None; continue
                    validate_schema("salary_annexure", raw_headers)
                    _process_salary_annexure(df, headers, result)
                elif code.startswith("SFT-016") or code.startswith("TDS-194A"):
                    if "INTERESTAMOUNT" not in headers: current_info_code = None; continue
                    validate_schema("interest_sb", raw_headers)
                    _process_interest(df, headers, result)
                elif code.startswith("SFT-17-LES"):
                    if "SALESCONSIDERATION" not in headers: current_info_code = None; continue
                    if "COSTOFACQUISITION" in headers:
                        validate_schema("capital_gains_equity", raw_headers)
                    else:
                        validate_schema("capital_gains_no_cost", raw_headers)
                    _process_cg_equity(df, headers, result)
                elif code.startswith("SFT-18-EMF"):
                    if "SALESCONSIDERATION" not in headers: current_info_code = None; continue
                    validate_schema("capital_gains_mf", raw_headers)
                    _process_cg_mf(df, headers, result)
                elif code.startswith("SFT-17") or code.startswith("SFT-18"):
                    if "SALESCONSIDERATION" not in headers: current_info_code = None; continue
                    if "AMCNAMECODE" in headers:
                        validate_schema("capital_gains_mf", raw_headers)
                        _process_cg_mf(df, headers, result)
                    else:
                        if "COSTOFACQUISITION" in headers:
                            validate_schema("capital_gains_equity", raw_headers)
                        else:
                            validate_schema("capital_gains_no_cost", raw_headers)
                        _process_cg_equity(df, headers, result)
                elif code.startswith("SFT-12") or code.startswith("TDS-194IA"):
                    if "TRANSACTIONVALUE" not in headers: current_info_code = None; continue
                    validate_schema("real_estate", raw_headers)
                    _process_real_estate(df, headers, result)
                else:
                    # It's an unknown code! Throw the strict error!
                    raise AISUnknownCodeError(code=code, source=current_info_source)

        # Fallback raw text parsers for anything not captured cleanly in tables
        if not result["dividends"]:
            result["dividends"] = _extract_dividends_fallback(full_text)
            
        salary_tds = sum(q["tds_deducted"] for q in result["salary"]["quarterly"])
        dividend_tds = sum(d.get("tds_deducted", 0.0) for d in result["dividends"])
        result["tds_total"] = salary_tds + dividend_tds

    finally:
        os.remove(tmp_path)

    return result

def _extract_personal(text: str) -> dict:
    personal = {}
    pan_match = re.search(r'Permanent Account Number \(PAN\).*?\n([A-Z]{5}\d{4}[A-Z])', text, re.DOTALL)
    if pan_match: personal["pan"] = pan_match.group(1)
    
    name_match = re.search(r'Name of Assessee\s*\n.*?(?:XXXX\s*\d{4}\s+)?([A-Z\s]+?)(?=\s*\n)', text)
    if not name_match: # Fallback in case of different formatting
        name_match = re.search(r'([A-Z\s]+)(?=\s*\nDate of Birth)', text)
    if name_match: personal["name"] = name_match.group(1).strip()
    
    dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if dob_match: personal["dob"] = dob_match.group(1)
    
    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if email_match: personal["email"] = email_match.group(1)
    
    mobile_match = re.search(r'(\d{10})', text)
    if mobile_match: personal["mobile"] = mobile_match.group(1)
    
    fy_match = re.search(r'Financial Year\s+(\d{4}-\d{2,4})', text)
    if fy_match: personal["fy"] = fy_match.group(1)
    return personal

def _process_salary_tds(df, headers, result, source=""):
    # Set employer from the Information Source of the current summary table.
    if source and (not result["salary"].get("employer")):
        result["salary"]["employer"] = source

    # Map row data to result["salary"]["quarterly"]
    for idx, row in df.iloc[1:].iterrows():
        try:
            amt = _clean_amount(row[headers.index("AMOUNTPAIDCREDITED")])
            tds = _clean_amount(row[headers.index("TDSDEDUCTED")])
            if amt > 0 or tds > 0:
                result["salary"]["quarterly"].append({
                    "sr": _clean_amount(row[headers.index("SRNO")]) if "SRNO" in headers else len(result["salary"]["quarterly"]) + 1,
                    "quarter": str(row[headers.index("QUARTER")]).strip() if "QUARTER" in headers else "",
                    "date": _parse_date(row[headers.index("DATEOFPAYMENTCREDIT")]) if "DATEOFPAYMENTCREDIT" in headers else "",
                    "amount_paid": amt,
                    "tds_deducted": tds,
                    "tds_deposited": _clean_amount(row[headers.index("TDSDEPOSITED")]) if "TDSDEPOSITED" in headers else 0,
                })
                result["salary"]["gross"] += amt
                result["salary"]["tds_deducted"] += tds
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_salary_annexure(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            gross = _clean_amount(row[headers.index("GROSSSALARY")])
            perq_col = next((h for h in headers if "PERQUISITE" in h), None)
            prof_col = next((h for h in headers if "PROFIT" in h and "LIEU" in h), None)
            
            perq = _clean_amount(row[headers.index(perq_col)]) if perq_col else 0
            prof = _clean_amount(row[headers.index(prof_col)]) if prof_col else 0
            if gross > 0:
                result["salary_annexure"]["gross_salary"] += gross
                result["salary_annexure"]["perquisites"] += perq
                result["salary_annexure"]["profits_lieu"] += prof
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_dividend_sft(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            amt = _clean_amount(row[headers.index("DIVIDENDAMOUNT")])
            if amt > 0:
                result["dividends"].append({"amount": amt, "source": "SFT-015", "type": "SFT-015"})
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_dividend_tds(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            amt = _clean_amount(row[headers.index("AMOUNTPAIDCREDITED")])
            tds = _clean_amount(row[headers.index("TDSDEDUCTED")]) if "TDSDEDUCTED" in headers else 0.0
            if amt > 0:
                result["dividends"].append({
                    "amount": amt,
                    "source": "TDS-194",
                    "type": "TDS-194",
                    "tds_deducted": tds
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_interest(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            amt = _clean_amount(row[headers.index("INTERESTAMOUNT")])
            if amt > 0:
                acc_type = str(row[headers.index("ACCOUNTTYPE")]).lower()
                if "saving" in acc_type:
                    result["interest_savings"].append({"amount": amt, "type": "savings"})
                else:
                    result["interest_deposits"].append({"amount": amt, "type": "term_deposit"})
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_cg_equity(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            if "STATUS" in headers and "inactive" in str(row[headers.index("STATUS")]).lower():
                continue
            term = str(row[headers.index("ASSETTYPE")]).lower() if "ASSETTYPE" in headers else ""
            term_type = "LTCG" if "long" in term else "STCG"
            cons = _clean_amount(row[headers.index("SALESCONSIDERATION")])
            cost = _clean_amount(row[headers.index("COSTOFACQUISITION")]) if "COSTOFACQUISITION" in headers else 0
            if cons > 0:
                sec_name = str(row[headers.index("SECURITYNAMESECURITYCODE")]).replace('\n', ' ')
                sec_class = str(row[headers.index("SECURITYCLASS")]).lower() if "SECURITYCLASS" in headers else ""
                
                item = {
                    "security": sec_name,
                    "type": term_type,
                    "sale_price": _clean_amount(row[headers.index("SALEPRICEPERUNIT")]) if "SALEPRICEPERUNIT" in headers else 0,
                    "quantity": _clean_amount(row[headers.index("QUANTITY")]) if "QUANTITY" in headers else 0,
                    "consideration": cons,
                    "cost": cost,
                    "gain": cons - cost,
                    # 31-Jan-2018 grandfathering FMV (Section 112A); the engine only applies it
                    # when the acquisition date is known to precede the cut-off.
                    "fmv_31jan2018": _clean_amount(row[headers.index("FAIRMARKETVALUE")]) if "FAIRMARKETVALUE" in headers else 0,
                    "sale_date": _parse_date(row[headers.index("DATEOFSALETRANSFER")]) if "DATEOFSALETRANSFER" in headers else "",
                }

                # Dynamic Routing based on Security Class
                if "unlisted" in sec_class or "foreign" in sec_class:
                    result["cg_unlisted"].append(item)
                elif "bond" in sec_class or "debenture" in sec_class or "gold" in sec_class or "bullion" in sec_class:
                    result["cg_bonds_gold"].append(item)
                elif "other" in sec_class:
                    item["fund"] = sec_name
                    item["amc"] = "Depository"
                    result["capital_gains_mf_other"].append(item)
                else:
                    result["capital_gains_equity"].append(item)
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_cg_mf(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            if "STATUS" in headers and "inactive" in str(row[headers.index("STATUS")]).lower():
                continue
            term = str(row[headers.index("ASSETTYPE")]).lower()
            term_type = "LTCG" if "long" in term else "STCG"
            cons = _clean_amount(row[headers.index("SALESCONSIDERATION")])
            cost = _clean_amount(row[headers.index("COSTOFACQUISITION")])
            if cons > 0:
                amc = str(row[headers.index("AMCNAMECODE")]).replace('\n', ' ')
                fund = str(row[headers.index("SECURITYNAMESECURITYCODE")]).replace('\n', ' ')
                sec_class = str(row[headers.index("SECURITYCLASS")]).lower() if "SECURITYCLASS" in headers else ""
                item = {
                    "amc": amc,
                    "fund": fund,
                    "security": fund,
                    "type": term_type,
                    "sale_price": _clean_amount(row[headers.index("SALEPRICEPERUNIT")]) if "SALEPRICEPERUNIT" in headers else 0,
                    "quantity": _clean_amount(row[headers.index("QUANTITY")]),
                    "consideration": cons,
                    "cost": cost,
                    "gain": cons - cost,
                    "fmv_31jan2018": _clean_amount(row[headers.index("FAIRMARKETVALUE")]) if "FAIRMARKETVALUE" in headers else 0,
                    "sale_date": _parse_date(row[headers.index("DATEOFSALETRANSFER")]) if "DATEOFSALETRANSFER" in headers else "",
                }

                # Dynamic routing based on Security Class instead of just fund name guessing
                is_debt = ("other" in sec_class or "liquid" in fund.lower() or "debt" in fund.lower()
                           or "gilt" in fund.lower() or "government securities" in fund.lower())
                if is_debt:
                    # Flag debt-oriented units so the engine can apply Section 50AA slab
                    # taxation when the acquisition date is on/after the 01-Apr-2023 cut-off.
                    item["is_debt"] = True
                    result["capital_gains_mf_other"].append(item)
                else:
                    result["capital_gains_mf_equity"].append(item)
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _extract_dividends_fallback(text: str) -> list:
    divs = []
    blocks = re.finditer(r'Dividend income.*?([\d,]+)', text, re.IGNORECASE)
    for m in blocks:
        amt = _clean_amount(m.group(1))
        if amt > 0 and amt < 1000000: divs.append({"amount": amt, "source": "SFT", "type": "SFT"})
    return divs

def _process_real_estate(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            if "STATUS" in headers and "inactive" in str(row[headers.index("STATUS")]).lower():
                continue
            amt = _clean_amount(row[headers.index("TRANSACTIONVALUE")])
            if amt > 0:
                result["cg_real_estate"].append({
                    "type": "LTCG", # Defaulting to LTCG for real estate if missing term
                    "security": str(row[headers.index("PROPERTYDESCRIPTION")]).strip()[:50] or "Real Estate Property",
                    "sale_price": amt, 
                    "consideration": amt, 
                    "cost": 0, 
                    "gain": amt, 
                    "needs_review": True
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_tax_payments(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            total = _clean_amount(row[headers.index("TOTALABCD")])
            if total > 0:
                result["tax_payments"].append({
                    "fy": str(row[headers.index("FINANCIALYEAR")]).strip(),
                    "tax": _clean_amount(row[headers.index("TAXA")]),
                    "surcharge": _clean_amount(row[headers.index("SURCHARGEB")]),
                    "cess": _clean_amount(row[headers.index("EDUCATIONCESSC")]),
                    "total": total,
                    "date": _parse_date(row[headers.index("DATEOFDEPOSIT")]) if "DATEOFDEPOSIT" in headers else ""
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_refunds(df, headers, result):
    for idx, row in df.iloc[1:].iterrows():
        try:
            amt = _clean_amount(row[headers.index("REFUNDAMOUNT")])
            if amt > 0:
                result["refunds"].append({
                    "fy": str(row[headers.index("FINANCIALYEAR")]).strip(),
                    "amount": amt,
                    "date": _parse_date(row[headers.index("DATEOFPAYMENT")]) if "DATEOFPAYMENT" in headers else ""
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

