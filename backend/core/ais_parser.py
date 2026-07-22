"""
core/ais_parser.py

Annual Information Statement (AIS) PDF Parser
=============================================
Extracts structured financial data from the Income Tax Department's AIS PDF.
Handles both the legacy single-line TDS summary format and the new Part B1
nested quarterly sub-row format (introduced FY 2025-26).

Parsing strategy:
  1. pdfplumber extracts raw text from each page.
  2. Section-specific regex functions extract structured data.
  3. _extract_tds_from_part_b1() sums Active sub-rows for TDS when the
     summary line omits the TDS total (new AIS format).

Set env var AIS_DEBUG=1 to dump extracted text to /tmp/ais_debug.txt for debugging.
"""

import os
import re
import logging
import pdfplumber
from io import BytesIO
from datetime import datetime

logger = logging.getLogger(__name__)


def _clean_amount(val: str) -> float:
    """Parse Indian formatted amounts like '27,03,160' or '5' into float."""
    if not val:
        return 0.0
    val = val.strip().replace(',', '').replace('₹', '').replace(' ', '')
    try:
        return float(val)
    except ValueError:
        return 0.0


def _parse_date(val: str) -> str:
    """Parse date string in DD/MM/YYYY format to ISO format."""
    if not val:
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val.strip()


def parse_ais_pdf(raw_bytes: bytes) -> dict:
    """
    Parse an AIS PDF and return structured financial data.
    
    Returns dict with keys:
        personal, salary, dividends, interest_savings, interest_deposits,
        capital_gains_equity, capital_gains_mf_equity, capital_gains_mf_other,
        tax_payments, refunds, tds_total, fy
    """
    pdf = pdfplumber.open(BytesIO(raw_bytes))
    
    # Extract all text
    full_text = ""
    page_texts = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        page_texts.append(text)
        full_text += text + "\n"
    
    # Debug dump: set env var AIS_DEBUG=1 to write extracted text
    if os.environ.get("AIS_DEBUG"):
        import tempfile
        debug_path = os.path.join(tempfile.gettempdir(), "ais_debug.txt")
        with open(debug_path, "w") as f:
            f.write(full_text)
        logger.info("AIS debug text written to %s", debug_path)
    
    deposits = _extract_interest_deposits(full_text)
    others = _extract_interest_others(full_text)
    
    # Filter out TDS-194A entries that are duplicates of SFT-016(TD)
    deposit_amounts = {d["amount"] for d in deposits}
    filtered_others = []
    for o in others:
        if o["type"] == "TDS-194A" and o["amount"] in deposit_amounts:
            continue
        filtered_others.append(o)

    result = {
        "personal": _extract_personal(full_text),
        "salary": _extract_salary(full_text),
        "dividends": _extract_dividends(full_text),
        "interest_savings": _extract_interest_savings(full_text),
        "interest_deposits": deposits,
        "interest_others": filtered_others,
        "capital_gains_equity": _extract_capital_gains_equity(full_text),
        "capital_gains_mf_equity": _extract_capital_gains_mf_equity(full_text, page_texts),
        "capital_gains_mf_other": _extract_capital_gains_mf_other(full_text, page_texts),
        "cg_real_estate": _extract_cg_real_estate(full_text),
        "cg_unlisted": _extract_cg_unlisted(full_text),
        "cg_bonds_gold": _extract_cg_bonds_gold(full_text),
        "misc_income": _extract_misc_income(full_text),
        "tax_payments": _extract_tax_payments(full_text),
        "refunds": _extract_refunds(full_text),
        "salary_annexure": _extract_salary_annexure(full_text),
    }
    
    # Compute derived fields
    result["tds_total"] = _compute_total_tds(result, full_text)
    result["fy"] = result["personal"].get("fy", "2025-26")
    
    pdf.close()
    return result


def _extract_personal(text: str) -> dict:
    """Extract Part A - General Information."""
    personal = {}
    
    # PAN
    pan_match = re.search(r'Permanent Account Number \(PAN\).*?\n([A-Z]{5}\d{4}[A-Z])', text, re.DOTALL)
    if pan_match:
        personal["pan"] = pan_match.group(1)
    else:
        pan_match = re.search(r'([A-Z]{5}\d{4}[A-Z])\s', text)
        if pan_match:
            personal["pan"] = pan_match.group(1)
    
    # Financial Year
    fy_match = re.search(r'Financial Year\s+(\d{4}-\d{2,4})', text)
    if fy_match:
        personal["fy"] = fy_match.group(1)
    
    # Name - search after PAN line
    name_match = re.search(r'([A-Z]{5}\d{4}[A-Z])\s+(?:XXXX\s+XXXX\s+\d{4}\s+)?([A-Z][A-Z\s]+?)(?:\n|$)', text)
    if name_match:
        personal["name"] = name_match.group(2).strip()
    
    # DOB
    dob_match = re.search(r'Date of Birth.*?\n(\d{2}/\d{2}/\d{4})', text, re.DOTALL)
    if dob_match:
        personal["dob"] = dob_match.group(1)
    
    # Mobile
    mobile_match = re.search(r'(\d{10})', text[:500])
    if mobile_match:
        personal["mobile"] = mobile_match.group(1)
    
    # Email
    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text[:500])
    if email_match:
        personal["email"] = email_match.group(1)
    
    return personal


def _extract_salary(text: str) -> dict:
    """Extract salary information from Part B1 - TDS-192."""
    salary = {"gross": 0, "tds_deducted": 0, "employer": "", "quarterly": []}
    
    # Find TDS-192 section block
    sal_section_match = re.search(
        r'TDS-192\s+Salary received.*?(?=\n\d+\s+TDS-|\n\d+\s+SFT-|\nPart B2|\Z)',
        text, re.DOTALL
    )
    
    if sal_section_match:
        section_text = sal_section_match.group(0)
        
        # Extract employer and gross from the section
        emp_match = re.search(r'(\w[\w\s()]+?)\s*\([A-Z0-9]+\)\s+(\d+)\s+([\d,]+)', section_text)
        if emp_match:
            salary["employer"] = emp_match.group(1).strip()
            salary["gross"] = _clean_amount(emp_match.group(3))
        
        # Extract quarterly breakdown ONLY from this section
        quarterly_pattern = re.compile(
            r'(\d+)\s+(Q[1-4]\([A-Za-z-]+\))\s+(\d{2}/\d{2}/\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+Active'
        )
        for m in quarterly_pattern.finditer(section_text):
            salary["quarterly"].append({
                "sr": int(m.group(1)),
                "quarter": m.group(2),
                "date": _parse_date(m.group(3)),
                "amount_paid": _clean_amount(m.group(4)),
                "tds_deducted": _clean_amount(m.group(5)),
                "tds_deposited": _clean_amount(m.group(6)),
            })
        
        salary["tds_deducted"] = sum(q["tds_deducted"] for q in salary["quarterly"])
        if not salary["gross"] and salary["quarterly"]:
            salary["gross"] = sum(q["amount_paid"] for q in salary["quarterly"])
            
    return salary


def _extract_salary_annexure(text: str) -> dict:
    """Extract TDS Annexure II salary details (more accurate gross salary)."""
    annexure = {"gross_salary": 0, "perquisites": 0, "profits_lieu": 0}
    
    ann_match = re.search(
        r'TDS-Ann\.II-SAL.*?(\d+)\s+([\d,]+)',
        text, re.DOTALL
    )
    if ann_match:
        annexure["gross_salary"] = _clean_amount(ann_match.group(2))
    
    return annexure


def _extract_dividends(text: str) -> list:
    """Extract dividend income from SFT-015 and TDS-194 sections."""
    dividends = []
    
    # SFT-015 dividends
    div_pattern = re.compile(
        r'SFT-015\s+Dividend income.*?([A-Z][A-Za-z0-9\s&]+?(?:LIMITED|LTD|COMPANY|CORP|INC))\s+\([A-Z0-9.]+\)\s+(\d+)\s+([\d,]+)',
        re.DOTALL | re.IGNORECASE
    )
    for m in div_pattern.finditer(text):
        dividends.append({
            "source": m.group(1).strip(),
            "count": int(m.group(2)),
            "amount": _clean_amount(m.group(3)),
            "type": "SFT-015",
        })
    
    # TDS-194 dividends
    tds194_pattern = re.compile(
        r'TDS-194\b.*?\s+([A-Z][A-Z\s.,&]+?(?:LIMITED|BANK|INDIA|LTD|COOP)[\w\s]*?)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)(?:\s+([\d,]+))?',
        re.DOTALL | re.IGNORECASE
    )
    for m in tds194_pattern.finditer(text):
        # Check if this source is already captured
        source = m.group(1).strip()
        if not any(d["source"] == source for d in dividends):
            dividends.append({
                "source": source,
                "count": int(m.group(2)),
                "amount": _clean_amount(m.group(3)),
                "tds": _clean_amount(m.group(4)) if m.group(4) else 0.0,
                "type": "TDS-194",
            })
    
    return dividends


def _extract_interest_savings(text: str) -> list:
    """Extract savings bank interest from SFT-016(SB) sections."""
    interests = []
    
    # Match each SFT-016(SB) block
    sb_blocks = re.finditer(
        r'SFT-016\(SB\)\s+Interest income.*?–\s*Savings\s+([A-Z][A-Z\s]+?(?:BANK|INDIA)[\w\s]*?)\s+\([A-Z0-9.]+\)\s+(\d+)\s+([\d,]+)',
        text, re.DOTALL
    )
    for m in sb_blocks:
        bank = m.group(1).strip()
        amount = _clean_amount(m.group(3))
        interests.append({
            "bank": bank,
            "amount": amount,
            "type": "savings",
        })
    
    return interests


def _extract_interest_deposits(text: str) -> list:
    """Extract term deposit interest from SFT-016(TD) sections."""
    deposits = []
    
    td_blocks = re.finditer(
        r'SFT-016\(TD\)\s+Interest income.*?–\s*Term Deposit\s+([A-Z][A-Z\s]+?(?:BANK|INDIA)[\w\s]*?)\s+\([A-Z0-9.]+\)\s+(\d+)\s+([\d,]+)',
        text, re.DOTALL
    )
    for m in td_blocks:
        bank = m.group(1).strip()
        amount = _clean_amount(m.group(3))
        deposits.append({
            "bank": bank,
            "amount": amount,
            "type": "term_deposit",
        })
    
    return deposits


def _extract_interest_others(text: str) -> list:
    """Extract other interest income (P2P, Bonds, PF, Refund, Unsecured loans)."""
    interests = []
    
    # SFT-016 (excluding SB and TD)
    sft_other_blocks = re.finditer(
        r'SFT-016\((?!SB|TD)[A-Z0-9]+\)\s+Interest income.*?–\s*(.*?)\s+([A-Z][A-Z\s]+?[\w\s]*?)\s+\([A-Z0-9.]+\)\s+(\d+)\s+([\d,]+)',
        text, re.DOTALL
    )
    for m in sft_other_blocks:
        interests.append({
            "source": m.group(2).strip(),
            "amount": _clean_amount(m.group(4)),
            "type": m.group(1).strip() or "other_interest",
        })
        
    # TDS-194A (Interest other than securities - typically P2P, unsecured loans)
    tds194a_blocks = re.finditer(
        r'TDS-194A.*?\s+([A-Z][A-Z\s.,&]+?(?:LIMITED|BANK|INDIA|LTD|COOP)[\w\s]*?)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)(?:\s+([\d,]+))?',
        text, re.DOTALL | re.IGNORECASE
    )
    for m in tds194a_blocks:
        interests.append({
            "source": m.group(1).strip(),
            "amount": _clean_amount(m.group(3)),
            "tds": _clean_amount(m.group(4)) if m.group(4) else 0.0,
            "type": "TDS-194A",
        })
        
    # TDS-193 (Interest on securities - bonds)
    tds193_blocks = re.finditer(
        r'TDS-193.*?\s+([A-Z][A-Z\s.,&]+?(?:LIMITED|BANK|INDIA|LTD|COOP)[\w\s]*?)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)(?:\s+([\d,]+))?',
        text, re.DOTALL | re.IGNORECASE
    )
    for m in tds193_blocks:
        interests.append({
            "source": m.group(1).strip(),
            "amount": _clean_amount(m.group(3)),
            "tds": _clean_amount(m.group(4)) if m.group(4) else 0.0,
            "type": "TDS-193",
        })
        
    # Income Tax Refund Interest (often explicit in AIS)
    refund_blocks = re.finditer(
        r'(?:Interest on income tax refund|Income Tax Refund).*?([\d,]+)',
        text, re.IGNORECASE
    )
    for m in refund_blocks:
        amt = _clean_amount(m.group(1))
        # Ensure we don't capture dates or small IDs
        if amt > 0 and amt < 1000000 and len(m.group(1)) < 10:
            # Check if already added to avoid duplicates
            if not any(i["type"] == "Tax Refund" for i in interests):
                interests.append({
                    "source": "Income Tax Department",
                    "amount": amt,
                    "type": "Tax Refund",
                })
        
    return interests


def _extract_capital_gains_equity(text: str) -> list:
    """Extract capital gains from listed equity share sales (SFT-17-LES)."""
    gains = []
    
    # Find the SFT-17-LES section
    les_section = re.search(r'SFT-17-LES\(M\).*?Sale of listed equity share', text)
    if not les_section:
        return gains
    
    # Extract individual transactions after the header
    # Pattern: SR_NO DATE SECURITY_NAME CLASS DEBIT CREDIT ASSET QTY PRICE CONSIDERATION COST FMV ... STATUS
    tx_pattern = re.compile(
        r'(\d+)\s+(\d{2}/\d{2}/\d{4})\s+'
        r'(.+?)\s+'
        r'Listed Equity\s+(?:Market|Share)\s+'
        r'(?:Market|Off)\s+'
        r'(?:market\s+)?'
        r'(Long|Short)\s+'
        r'([\d,.]+)\s+'          # quantity
        r'([\d,.]+)\s+'          # sale price per unit
        r'([\d,.]+)\s+'          # sales consideration
        r'([\d,.]+)\s+'          # cost of acquisition
        r'([\d,.]+)\s+'          # unit FMV
        r'([\d,.]+)\s+'          # fair market value
        r'\d+\s+'                # indexed cost
        r'(Active|Inactive)',
        re.DOTALL
    )
    
    # Use simpler line-based approach since AIS format is complex
    lines = text.split('\n')
    in_les_section = False
    
    for i, line in enumerate(lines):
        if 'SFT-17-LES' in line:
            in_les_section = True
            continue
        if in_les_section and re.match(r'^\d+\s+\d{2}/\d{2}/\d{4}', line.strip()):
            parts = line.strip().split()
            try:
                sr = int(parts[0])
                date = _parse_date(parts[1])
                
                # Find the term type (Long/Short) and numbers after it
                term_idx = None
                for j, p in enumerate(parts):
                    if p in ('Long', 'Short'):
                        term_idx = j
                        break
                
                if term_idx is None:
                    continue
                
                term_type = parts[term_idx]
                # After term type, numbers are: qty, price, consideration, cost, fmv, fair_market_value, indexed, status
                nums = []
                for p in parts[term_idx + 1:]:
                    cleaned = p.replace(',', '')
                    try:
                        nums.append(float(cleaned))
                    except ValueError:
                        if p in ('Active', 'Inactive'):
                            break
                        continue
                
                if len(nums) >= 3:
                    security_name = ' '.join(parts[2:term_idx]).strip()
                    # Clean up multi-line security names
                    security_name = re.sub(r'(?i)\b(Listed|Equity|Shares?|Market|Off\s*market)\b', ' ', security_name)
                    # Strip ISIN
                    security_name = re.sub(r'\([A-Z0-9]{12}\)', '', security_name)
                    security_name = re.sub(r'\s+', ' ', security_name).strip()
                    
                    gains.append({
                        "sr": sr,
                        "date": date,
                        "security": security_name,
                        "type": "LTCG" if term_type == "Long" else "STCG",
                        "quantity": nums[0],
                        "sale_price": nums[1],
                        "consideration": nums[2],
                        "cost": nums[3] if len(nums) > 3 else 0,
                        "gain": nums[2] - (nums[3] if len(nums) > 3 else 0),
                    })
            except (IndexError, ValueError):
                continue
        
        if in_les_section and ('SFT-18' in line or 'SFT-17(' in line or 'Purchase' in line):
            in_les_section = False
    
    return gains


def _extract_capital_gains_mf_equity(text: str, page_texts: list) -> list:
    """Extract capital gains from equity mutual fund sales (SFT-18-EMF)."""
    gains = []
    
    # Look for equity MF sale data (AMC-based entries)
    # These entries span multiple lines in the AIS
    # Pattern: SR AMC_NAME DATE SECURITY_CLASS SECURITY_NAME DEBIT CREDIT ASSET QTY PRICE CONSIDERATION STT COST ...
    
    in_emf_section = False
    current_entry = {}
    
    for page_text in page_texts:
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            if 'SFT-18-EMF' in line or ('Sale of unit of equity oriented mutual fund' in line):
                in_emf_section = True
                continue
            
            if in_emf_section and ('SFT-17-OTU' in line or 'SFT-18-OTU' in line or 'Purchase' in line or 'Part B3' in line):
                in_emf_section = False
                continue
            
            if not in_emf_section:
                continue
            
            # Look for entry lines starting with SR number and AMC name
            entry_match = re.match(
                r'^\s*(\d+)\s+([A-Za-z]+[\w\s]*?)\s+(\d{2}/\d{2}/\d{4})\s+Unit of',
                line
            )
            if entry_match:
                sr = int(entry_match.group(1))
                amc = entry_match.group(2).strip()
                date = _parse_date(entry_match.group(3))
                
                # Find term type and numbers
                term_match = re.search(r'(Long|Short)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)', line)
                if term_match:
                    term_type = term_match.group(1)
                    qty = _clean_amount(term_match.group(2))
                    price = _clean_amount(term_match.group(3))
                    consideration = _clean_amount(term_match.group(4))
                    
                    # For SFT-18-EMF, there is an STT column before cost
                    after_consideration = line[term_match.end():]
                    cost_nums = re.findall(r'([\d,.]+)', after_consideration)
                    cost = _clean_amount(cost_nums[1]) if len(cost_nums) >= 2 else 0
                    
                    # Extract fund name from the middle text
                    middle_text = line[entry_match.end():term_match.start()].strip()
                    fund_name = middle_text
                    fund_name = re.sub(r'(?i)\b(?:Equity Oriented Mutual Fund|AMC\s*\([A-Za-z]+\))\b', '', fund_name)
                    fund_name = re.sub(r'\([A-Z0-9]{12}\)', '', fund_name)
                    fund_name = fund_name.strip()
                    
                    if not fund_name or len(fund_name) < 3:
                        fund_name = amc
                        for j in range(i + 1, min(i + 6, len(lines))):
                            fund_line = lines[j].strip()
                            if re.match(r'^\s*\d+\s+(?:[A-Za-z]+|\d{2}/\d{2})', fund_line):
                                break
                            if len(fund_line) > 5 and 'Active' not in fund_line:
                                fund_name = fund_line.split('(')[0].strip()
                                break
                    
                    gains.append({
                        "sr": sr,
                        "amc": amc,
                        "date": date,
                        "fund": fund_name,
                        "type": "LTCG" if term_type == "Long" else "STCG",
                        "quantity": qty,
                        "sale_price": price,
                        "consideration": consideration,
                        "cost": cost,
                        "gain": consideration - cost if cost > 0 else consideration,
                    })
    
    return gains


def _extract_capital_gains_mf_other(text: str, page_texts: list) -> list:
    """Extract capital gains from other (non-equity) mutual fund sales (SFT-17-OTU, SFT-18-OTU)."""
    gains = []
    
    in_otu_section = False
    
    for page_text in page_texts:
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            if 'SFT-17-OTU' in line or 'SFT-18-OTU' in line or 'Sale of other unit' in line:
                in_otu_section = True
                continue
            
            if in_otu_section and ('Purchase' in line or 'Part B3' in line or 'SFT-17(Pur)' in line or 'SFT-18(Pur)' in line):
                in_otu_section = False
                continue
            
            if not in_otu_section:
                continue
            
            is_rta = False
            # Look for entry lines with date pattern
            entry_match = re.match(r'^\s*(\d+)\s+(\d{2}/\d{2}/\d{4})\s+', line)
            if not entry_match:
                # Also try AMC-based format
                entry_match = re.match(r'^\s*(\d+)\s+([A-Za-z]+[\w\s\&]*?)\s+(\d{2}/\d{2}/\d{4})', line)
                if entry_match:
                    is_rta = True
            
            if entry_match:
                groups = entry_match.groups()
                sr = int(groups[0])
                date = _parse_date(groups[-1])
                
                term_match = re.search(r'(Long|Short)\s+([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)', line)
                if term_match:
                    term_type = term_match.group(1)
                    qty = _clean_amount(term_match.group(2))
                    price = _clean_amount(term_match.group(3))
                    consideration = _clean_amount(term_match.group(4))
                    
                    # Try to find cost
                    after_consideration = line[term_match.end():]
                    cost_nums = re.findall(r'([\d,.]+)', after_consideration)
                    if is_rta and len(cost_nums) >= 2:
                        cost = _clean_amount(cost_nums[1])
                    elif cost_nums:
                        cost = _clean_amount(cost_nums[0])
                    else:
                        cost = 0
                    
                    # Fund name from middle text
                    middle_text = line[entry_match.end():term_match.start()].strip()
                    fund_name = middle_text
                    fund_name = re.sub(r'(?i)\b(?:Other Units|Unit of|Equity|Oriented|Mutual Fund|Market|Off market|AMC\s*\([A-Za-z]+\)|Listed Equity\s*Share)\b', '', fund_name)
                    fund_name = re.sub(r'\([A-Z0-9]{12}\)', '', fund_name)
                    fund_name = fund_name.strip()
                    
                    if not fund_name or len(fund_name) < 3:
                        fund_name = "Other Unit"
                        for j in range(i + 1, min(i + 6, len(lines))):
                            fund_line = lines[j].strip()
                            if re.match(r'^\s*\d+\s+(?:[A-Za-z]+|\d{2}/\d{2})', fund_line):
                                break
                            if len(fund_line) > 5 and 'Active' not in fund_line:
                                fund_name = fund_line.split('(')[0].strip()
                                break
                    
                    gains.append({
                        "sr": sr,
                        "date": date,
                        "fund": fund_name,
                        "type": "LTCG" if term_type == "Long" else "STCG",
                        "quantity": qty,
                        "sale_price": price,
                        "consideration": consideration,
                        "cost": cost,
                        "gain": consideration - cost if cost > 0 else consideration,
                    })
    
    # De-duplicate: The Income Tax AIS sometimes reports the same MF sale twice —
    # once by the Depository (SFT-17-OTU) and once by the Registrar/RTA (SFT-18-OTU).
    # Both entries have identical (consideration, type) but slightly different cost values.
    # We keep the entry with the HIGHER cost (lower gain = more accurate = less conservative).
    seen: dict = {}  # key: (rounded_consideration, cg_type)
    deduped = []
    for g in gains:
        key = (round(g['consideration'], 0), g['type'])
        if key not in seen:
            seen[key] = g
            deduped.append(g)
        else:
            # Duplicate found — keep the one with higher cost (lower reported gain)
            existing = seen[key]
            if g['cost'] > existing['cost']:
                # Replace existing with this one
                deduped = [g if x is existing else x for x in deduped]
                seen[key] = g
    
    return deduped


def _extract_cg_real_estate(text: str) -> list:
    """Extract capital gains from Sale of Land or Building (SFT-12 or TDS-194IA)."""
    gains = []
    
    # SFT-12 Purchase/Sale of Immovable Property
    # TDS-194IA TDS on sale of property
    blocks = re.finditer(
        r'(SFT-12|TDS-194IA)\s+[^\n]*?(?:Immovable Property|Sale of property)[^\n]*?([A-Za-z0-9\s,-]+)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)',
        text, re.IGNORECASE
    )
    for m in blocks:
        amt = _clean_amount(m.group(4))
        if amt > 0:
            gains.append({
                "type": "LTCG", # Assumed LTCG by default for real estate in this generic parsing
                "security": m.group(2).strip()[:50] or "Real Estate Property",
                "sale_price": amt,
                "consideration": amt,
                "cost": 0, # Missing cost basis in AIS
                "gain": amt,
                "needs_review": True
            })
    return gains


def _extract_cg_unlisted(text: str) -> list:
    """Extract capital gains from Unlisted Equity / Foreign RSUs (SFT-17-UELS or similar)."""
    gains = []
    
    # Unlisted equity / Foreign Assets
    blocks = re.finditer(
        r'(SFT-17-UELS|Foreign Asset|Unlisted Equity)\s+[^\n]*?([A-Za-z0-9\s,&]+(?:INC|LLC|LTD|PLC)[\w\s]*?)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)',
        text, re.IGNORECASE
    )
    for m in blocks:
        amt = _clean_amount(m.group(4))
        if amt > 0:
            gains.append({
                "type": "STCG", # Assumed STCG (slab rate) as conservative default for unlisted
                "security": m.group(2).strip()[:50] or "Foreign/Unlisted Equity",
                "sale_price": amt,
                "consideration": amt,
                "cost": 0, # Missing cost basis
                "gain": amt,
                "needs_review": True
            })
    return gains


def _extract_cg_bonds_gold(text: str) -> list:
    """Extract capital gains from Bonds, Debentures, Gold, Jewellery (SFT-17 variants)."""
    gains = []
    
    # Look for keywords in SFT-17 sales
    blocks = re.finditer(
        r'SFT-17\([A-Z]+\)\s+(?:Sale of\s+)?(Bonds|Debentures|Gold|Jewellery|Bullion)[^\n]*?([A-Za-z0-9\s,&]+)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)',
        text, re.IGNORECASE
    )
    for m in blocks:
        amt = _clean_amount(m.group(4))
        if amt > 0:
            gains.append({
                "type": "LTCG", # Default to LTCG for bonds/gold
                "security": f"{m.group(1)} - {m.group(2).strip()[:30]}",
                "sale_price": amt,
                "consideration": amt,
                "cost": 0, # Missing cost basis
                "gain": amt,
                "needs_review": True
            })
    return gains


def _extract_misc_income(text: str) -> list:
    """Extract miscellaneous income like Rent, Professional Fees, Commission, etc."""
    misc = []
    sections = {
        'TDS-194J': 'Professional/Technical Fees',
        'TDS-194I': 'Rent Income',
        'TDS-194H': 'Commission/Brokerage',
        'TDS-194C': 'Contractor Payments',
        'TDS-194B': 'Lottery/Winnings',
        'TDS-194BB': 'Horse Racing Winnings'
    }
    
    for code, desc in sections.items():
        # Match pattern: CODE [Description text...] [COMPANY NAME] (PAN) [COUNT] [AMOUNT]
        blocks = re.finditer(
            rf'{code}\s+[^\n]*?\s+([A-Z][A-Z\s&0-9]+?[\w\s]*?)\s+\([A-Z0-9]{{10}}\)\s+(\d+)\s+([\d,]+)',
            text
        )
        for m in blocks:
            source = m.group(1).strip()
            amt = _clean_amount(m.group(3))
            if amt > 0 and not any(x["source"] == source and x["code"] == code for x in misc):
                misc.append({
                    "code": code,
                    "type": desc,
                    "source": source,
                    "amount": amt,
                })
    return misc


def _extract_tax_payments(text: str) -> list:
    """Extract tax payments from Part B3."""
    payments = []
    
    if 'No Transactions Present' in text:
        return payments
    
    pay_pattern = re.compile(
        r'(\d{4}-\d{2})\s+\d+\s+\d+\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+(\d+)\s+(\d{2}/\d{2}/\d{4})'
    )
    for m in pay_pattern.finditer(text):
        payments.append({
            "fy": m.group(1),
            "tax": _clean_amount(m.group(2)),
            "surcharge": _clean_amount(m.group(3)),
            "cess": _clean_amount(m.group(4)),
            "total": _clean_amount(m.group(6)),
            "date": _parse_date(m.group(8)),
        })
    
    return payments


def _extract_refunds(text: str) -> list:
    """Extract refund information from Part B4."""
    refunds = []
    
    ref_pattern = re.compile(
        r'(\d{4}-\d{2})\s+ECS\s+.*?([\d,]+)\s+(\d{2}/\d{2}/\d{4})'
    )
    for m in ref_pattern.finditer(text):
        refunds.append({
            "fy": m.group(1),
            "amount": _clean_amount(m.group(2)),
            "date": _parse_date(m.group(3)),
        })
    
    return refunds


def _extract_tds_from_part_b1(text: str) -> float:
    """
    Extracts total TDS by summing Active quarterly sub-rows from Part B1.

    This handles the NEW AIS format (FY 2025-26+) where the Income Tax
    Department no longer prints a TDS total on the summary header line.
    Instead, TDS is buried across dozens of quarterly deduction rows:

        1  TDS-194A  ...  STATE BANK OF INDIA  (MUMS86176G)  24  4,83,630
        (Section 194A)
        SR. NO. QUARTER  DATE          AMOUNT    TDS DEDUCTED  TDS DEPOSITED  STATUS
        1  Q4(Jan-Mar)  31/03/2026   22,388     2,239         2,239          Active
        ...

    Strategy:
      1. Find each TDS summary line (code + bank + PAN + COUNT + AMOUNT).
      2. If the summary line has a TDS total printed after AMOUNT → use it (old format).
      3. Otherwise → isolate the sub-row block, match only Active rows,
         take the first COUNT rows, and sum the TDS DEDUCTED column.
    """
    nested_tds = 0.0

    tds_blocks = re.finditer(
        r'TDS-[A-Z0-9]{3,5}.*?\s+([A-Z][A-Z\s.,&]+?(?:LIMITED|BANK|INDIA|LTD|COOP)[\w\s]*?)\s+\([A-Z0-9]{10}\)\s+(\d+)\s+([\d,]+)',
        text, re.DOTALL | re.IGNORECASE
    )

    for m in tds_blocks:
        count = int(m.group(2))

        # Check if the legacy format already printed TDS on the summary line.
        # In the old format there would be another number right after AMOUNT.
        remainder = text[m.end():]
        tds_on_summary = re.match(r'^\s*([\d,]+)', remainder)
        if tds_on_summary:
            # Old format: TDS is explicitly stated on the summary line.
            nested_tds += _clean_amount(tds_on_summary.group(1))
        else:
            # New format: TDS omitted from summary — sum the Active sub-rows.
            # Find the boundary of this block (next TDS/SFT entry or Part B2).
            next_section = re.search(r'\n\d+\s+(TDS|SFT)-|\nPart B2', remainder)
            block_end = next_section.start() if next_section else len(remainder)
            block_text = remainder[:block_end]

            # Sub-row format: SR  Q#(...)  DD/MM/YYYY  AMOUNT  TDS_DEDUCTED  TDS_DEPOSITED  STATUS
            # We want the TDS DEDUCTED column (group 1 below) for Active rows only.
            sub_rows = list(re.finditer(
                r'\d+\s+Q[1-4]\(.*?\)\s+\d{2}/\d{2}/\d{4}\s+[\d,]+\s+([\d,]+).*?Active',
                block_text
            ))
            # The AIS COUNT field is authoritative — take only the first COUNT rows.
            nested_tds += sum(_clean_amount(sr.group(1)) for sr in sub_rows[:count])

    return nested_tds


def _compute_total_tds(result: dict, text: str = "") -> float:
    """
    Compute total TDS paid across all income sources.

    Priority:
      1. Salary TDS (from Form 16 / quarterly salary data).
      2. Part B1 sub-row extraction for interest/dividend TDS (new & old AIS formats).
      3. Any explicitly captured TDS from interest_others, dividends, deposits, misc.
    """
    salary_tds = result.get("salary", {}).get("tds_deducted", 0.0)

    # Extract TDS from Part B1 (handles both old and new AIS formats)
    part_b1_tds = _extract_tds_from_part_b1(text) if text else 0.0

    if part_b1_tds > 0:
        # Part B1 sub-rows are the most accurate source — use them directly.
        total_tds = part_b1_tds
    else:
        # Fallback: sum TDS from per-record fields captured by other extractors.
        total_tds = salary_tds
        for interest in result.get("interest_others", []):
            total_tds += interest.get("tds", 0.0)
        for d in result.get("dividends", []):
            total_tds += d.get("tds", 0.0)
        for dep in result.get("interest_deposits", []):
            total_tds += dep.get("tds", 0.0)
        for m in result.get("misc_income", []):
            total_tds += m.get("tds", 0.0)

    return total_tds


