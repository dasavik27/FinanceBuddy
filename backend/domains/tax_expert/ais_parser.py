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
from datetime import datetime

from .ais_schemas import validate_schema, AISStructureChangedError, AISUnknownCodeError, clean_header

logger = logging.getLogger(__name__)

# camelot is imported lazily inside parse_ais_pdf rather than at module scope.
# It pulls in OpenCV (cv2), and the pair costs ~1.8s of import time and ~60 MB
# RSS — unaffordable at boot on a 512 MB Render instance where the vast majority
# of requests never touch a PDF. Deferring it to the first AIS upload keeps the
# idle footprint low and cuts cold-start latency.


def _is_blank(val) -> bool:
    """True for None, NaN, or whitespace-only values.

    Replaces the former pd.isna() call. Camelot yields str cells (occasionally
    float NaN for empty ones), so this covers every case reachable here without
    importing pandas — which module-level cost ~8.7s and ~70 MB purely for this
    null check. NaN is detected via the self-inequality identity.
    """
    if val is None:
        return True
    if isinstance(val, float) and val != val:
        return True
    return not str(val).strip()


def _col_map(headers) -> dict:
    """Map header name -> column position, resolved once per table.

    The row loops below used `headers.index("X")` for every column of every row —
    a linear scan of the header list per cell, so O(rows x cols) list scans on
    tables that can run to thousands of rows.

    First occurrence wins, matching list.index() semantics, which matters because
    PDF-extracted headers can legitimately contain duplicates.
    """
    col = {}
    for i, name in enumerate(headers):
        if name not in col:
            col[name] = i
    return col


def _clean_amount(val) -> float:
    if _is_blank(val):
        return 0.0
    val_str = str(val).strip().replace(',', '').replace('₹', '').replace(' ', '')
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def _parse_date(val) -> str:
    if _is_blank(val):
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
    try:
        import camelot  # lazy — see module header
    except ImportError:
        return {"error": "AIS PDF parsing not available - install camelot-py"}

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
                    # Two different table shapes share this branch. SFT-016 reports
                    # "INTEREST AMOUNT"; a 194A child table reports "AMOUNT
                    # PAID/CREDITED" + "TDS DEDUCTED". Dispatch on the columns actually
                    # present rather than assuming the SFT shape - assuming it meant
                    # every 194A table failed the guard and was dropped whole.
                    if "INTERESTAMOUNT" in headers:
                        validate_schema("interest_sb", raw_headers)
                        _process_interest(df, headers, result)
                    elif "AMOUNTPAIDCREDITED" in headers:
                        validate_schema("dividend_tds", raw_headers)
                        _process_interest_tds(df, headers, result)
                    else:
                        current_info_code = None
                        continue
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
            
        _finalise_tds_total(result)

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
    col = _col_map(headers)
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            amt = _clean_amount(row[col["AMOUNTPAIDCREDITED"]])
            tds = _clean_amount(row[col["TDSDEDUCTED"]])
            if amt > 0 or tds > 0:
                result["salary"]["quarterly"].append({
                    "sr": _clean_amount(row[col["SRNO"]]) if "SRNO" in col else len(result["salary"]["quarterly"]) + 1,
                    "quarter": str(row[col["QUARTER"]]).strip() if "QUARTER" in col else "",
                    "date": _parse_date(row[col["DATEOFPAYMENTCREDIT"]]) if "DATEOFPAYMENTCREDIT" in col else "",
                    "amount_paid": amt,
                    "tds_deducted": tds,
                    "tds_deposited": _clean_amount(row[col["TDSDEPOSITED"]]) if "TDSDEPOSITED" in col else 0,
                })
                result["salary"]["gross"] += amt
                result["salary"]["tds_deducted"] += tds
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_salary_annexure(df, headers, result):
    for row in df.iloc[1:].itertuples(index=False, name=None):
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
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

def _process_dividend_sft(df, headers, result):
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            amt = _clean_amount(row[headers.index("DIVIDENDAMOUNT")])
            if amt > 0:
                result["dividends"].append({"amount": amt, "source": "SFT-015", "type": "SFT-015"})
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

def _process_dividend_tds(df, headers, result):
    for row in df.iloc[1:].itertuples(index=False, name=None):
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
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

def _finalise_tds_total(result: dict) -> None:
    """
    Sum every head that can carry TDS into `tds_total`, in place.

    This used to add salary and dividends only. Interest TDS - which for anyone with a
    fixed deposit is the second-largest credit they have - was simply absent, so tax
    already deducted at source went uncredited and the balance payable was overstated.
    Extracted from the parse function so the arithmetic is testable on its own.
    """
    salary_tds = sum(
        _safe_num(q.get("tds_deducted")) for q in result.get("salary", {}).get("quarterly", [])
    )
    dividend_tds = sum(_safe_num(d.get("tds_deducted")) for d in result.get("dividends", []))
    interest_tds = sum(
        _safe_num(i.get("tds_deducted"))
        for i in (result.get("interest_deposits", []) + result.get("interest_savings", []))
    )
    other_tds = sum(_safe_num(r.get("tds_deducted")) for r in result.get("rent_received", []))
    result["tds_total"] = salary_tds + dividend_tds + interest_tds + other_tds


def _safe_num(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _process_interest(df, headers, result):
    """SFT-016-shaped interest table, keyed on INTEREST AMOUNT."""
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            amt = _clean_amount(row[headers.index("INTERESTAMOUNT")])
            if amt > 0:
                acc_type = str(row[headers.index("ACCOUNTTYPE")]).lower()
                if "saving" in acc_type:
                    result["interest_savings"].append({"amount": amt, "type": "savings"})
                else:
                    result["interest_deposits"].append({"amount": amt, "type": "term_deposit"})
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests


def _process_interest_tds(df, headers, result):
    """
    TDS-194A interest table, keyed on AMOUNT PAID/CREDITED.

    A 194A child table has the *TDS* shape - "AMOUNT PAID/CREDITED" and "TDS DEDUCTED",
    like dividend_tds - not the SFT-016 shape with "INTEREST AMOUNT". Both codes were
    routed to _process_interest, whose guard requires INTERESTAMOUNT, so every 194A table
    hit `current_info_code = None; continue` and was discarded whole. Bank and FD interest
    reported under 194A never reached income, and the tax deducted on it never reached
    tds_total - understating the income and the credit, with no error at any log level.
    """
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            amt = _clean_amount(row[headers.index("AMOUNTPAIDCREDITED")])
            tds = _clean_amount(row[headers.index("TDSDEDUCTED")]) if "TDSDEDUCTED" in headers else 0.0
            if amt > 0:
                # 194A covers interest other than on securities - deposits, not a savings
                # account (banks do not deduct on SB interest), so it books as a deposit.
                result["interest_deposits"].append({
                    "amount": amt,
                    "type": "term_deposit",
                    "source": "TDS-194A",
                    "tds_deducted": tds,
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

def _process_cg_equity(df, headers, result):
    col = _col_map(headers)
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            if "STATUS" in col and "inactive" in str(row[col["STATUS"]]).lower():
                continue
            term = str(row[col["ASSETTYPE"]]).lower() if "ASSETTYPE" in col else ""
            term_type = "LTCG" if "long" in term else "STCG"
            cons = _clean_amount(row[col["SALESCONSIDERATION"]])
            cost = _clean_amount(row[col["COSTOFACQUISITION"]]) if "COSTOFACQUISITION" in col else 0
            if cons > 0:
                sec_name = str(row[col["SECURITYNAMESECURITYCODE"]]).replace('\n', ' ')
                sec_class = str(row[col["SECURITYCLASS"]]).lower() if "SECURITYCLASS" in col else ""

                item = {
                    "security": sec_name,
                    "type": term_type,
                    "sale_price": _clean_amount(row[col["SALEPRICEPERUNIT"]]) if "SALEPRICEPERUNIT" in col else 0,
                    "quantity": _clean_amount(row[col["QUANTITY"]]) if "QUANTITY" in col else 0,
                    "consideration": cons,
                    "cost": cost,
                    "gain": cons - cost,
                    # 31-Jan-2018 grandfathering FMV (Section 112A); the engine only applies it
                    # when the acquisition date is known to precede the cut-off.
                    "fmv_31jan2018": _clean_amount(row[col["FAIRMARKETVALUE"]]) if "FAIRMARKETVALUE" in col else 0,
                    "sale_date": _parse_date(row[col["DATEOFSALETRANSFER"]]) if "DATEOFSALETRANSFER" in col else "",
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
    col = _col_map(headers)
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            if "STATUS" in col and "inactive" in str(row[col["STATUS"]]).lower():
                continue
            term = str(row[col["ASSETTYPE"]]).lower()
            term_type = "LTCG" if "long" in term else "STCG"
            cons = _clean_amount(row[col["SALESCONSIDERATION"]])
            cost = _clean_amount(row[col["COSTOFACQUISITION"]])
            if cons > 0:
                amc = str(row[col["AMCNAMECODE"]]).replace('\n', ' ')
                fund = str(row[col["SECURITYNAMESECURITYCODE"]]).replace('\n', ' ')
                sec_class = str(row[col["SECURITYCLASS"]]).lower() if "SECURITYCLASS" in col else ""
                item = {
                    "amc": amc,
                    "fund": fund,
                    "security": fund,
                    "type": term_type,
                    "sale_price": _clean_amount(row[col["SALEPRICEPERUNIT"]]) if "SALEPRICEPERUNIT" in col else 0,
                    "quantity": _clean_amount(row[col["QUANTITY"]]),
                    "consideration": cons,
                    "cost": cost,
                    "gain": cons - cost,
                    "fmv_31jan2018": _clean_amount(row[col["FAIRMARKETVALUE"]]) if "FAIRMARKETVALUE" in col else 0,
                    "sale_date": _parse_date(row[col["DATEOFSALETRANSFER"]]) if "DATEOFSALETRANSFER" in col else "",
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
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            if "STATUS" in headers and "inactive" in str(row[headers.index("STATUS")]).lower():
                continue
            amt = _clean_amount(row[headers.index("TRANSACTIONVALUE")])
            if amt > 0:
                # `gain` is 0 and `cost_unknown` is set, deliberately.
                #
                # This used to record `cost: 0, gain: amt` - the entire transaction value
                # booked as a capital gain. The AIS reports an immovable-property
                # transaction value; it never reports your cost of acquisition, and under
                # SFT-012 / TDS-194IA the same code covers both sides of a conveyance. So
                # buying a Rs 1 crore flat manufactured Rs 1 crore of LTCG and roughly
                # Rs 12.5 lakh of tax. `needs_review` was set but tax_engine summed the
                # fabricated gain into ltcg_other and taxed it regardless.
                #
                # The transaction is still surfaced - suppressing it would hide a real
                # reporting event - but it contributes nothing taxable until the user
                # supplies a cost. See _sum_real_estate_gains in tax_engine.
                result["cg_real_estate"].append({
                    "type": "LTCG",  # Immovable property is long-term after 24 months.
                    "security": str(row[headers.index("PROPERTYDESCRIPTION")]).strip()[:50] or "Real Estate Property",
                    "sale_price": amt,
                    "consideration": amt,
                    "cost": 0.0,
                    "gain": 0.0,
                    "cost_unknown": True,
                    "needs_review": True,
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)

def _process_tax_payments(df, headers, result):
    for row in df.iloc[1:].itertuples(index=False, name=None):
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
    for row in df.iloc[1:].itertuples(index=False, name=None):
        try:
            amt = _clean_amount(row[headers.index("REFUNDAMOUNT")])
            if amt > 0:
                result["refunds"].append({
                    "fy": str(row[headers.index("FINANCIALYEAR")]).strip(),
                    "amount": amt,
                    "date": _parse_date(row[headers.index("DATEOFPAYMENT")]) if "DATEOFPAYMENT" in headers else ""
                })
        except Exception as e: logger.debug("AIS row skipped during parse: %s", e)  # pragma: no cover — defensive / hard to exercise in unit tests

