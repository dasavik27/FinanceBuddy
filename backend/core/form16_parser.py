import re
import pdfplumber
from io import BytesIO

def _clean_amount(val: str) -> float:
    """Parse Indian formatted amounts like '27,03,160' or '1,50,000' into float."""
    if not val:
        return 0.0
    val = val.strip().replace(',', '').replace('₹', '').replace(' ', '')
    try:
        return float(val)
    except ValueError:
        return 0.0

def parse_form16_pdf(raw_bytes: bytes) -> dict:
    """
    Parse a Form 16 (Part B) PDF and extract deductions (Chapter VI-A) and exemptions (Sec 10).
    """
    pdf = pdfplumber.open(BytesIO(raw_bytes))
    
    full_text = ""
    for page in pdf.pages:
        full_text += (page.extract_text() or "") + "\n"
        
    with open("form16_debug.txt", "w") as f:
        f.write(full_text)
        
    deductions = {}
    
    # Common Patterns for Form 16 Part B / TRACES format
    # The last number on a line with these keywords is usually the claimed/deductible amount.
    
    lines = full_text.split('\n')
    
    def extract_val(pattern):
        # Scan line by line for a match, then extract the last number on the line
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE):
                # Find all numbers in the line
                nums = re.findall(r'[\d,]+\.?\d*', line)
                if nums:
                    # Form 16 usually lists Gross Amount and Deductible Amount. 
                    # The right-most number is typically the final deductible amount.
                    return _clean_amount(nums[-1])
        return 0.0

    # Section 10 Exemptions
    hra = extract_val(r'House\s*Rent\s*Allowance|Sec(?:tion)?\s*10\(13A\)')
    if hra > 0: deductions['hra'] = hra
    
    lta = extract_val(r'Leave\s*Travel\s*Concession|Sec(?:tion)?\s*10\(5\)')
    if lta > 0: deductions['lta'] = lta
    
    sec10_other = extract_val(r'Gratuity|Sec(?:tion)?\s*10\(10\)|Leave\s*Encashment')
    if sec10_other > 0: deductions['sec10_other'] = sec10_other
    
    # Professional Tax
    ptax = extract_val(r'Tax\s*on\s*employment|Professional\s*Tax|Sec(?:tion)?\s*16\(iii\)')
    if ptax > 0: deductions['ptax'] = ptax

    # Home Loan Interest
    hl = extract_val(r'Interest\s*on\s*Housing\s*Loan|Sec(?:tion)?\s*24\(b\)')
    if hl > 0: deductions['24b'] = hl
    
    # Chapter VI-A Deductions
    val_80c = extract_val(r'Life\s*insurance|80C|Provident\s*Fund|PPF|ELSS|Tuition\s*Fees')
    if val_80c > 0: deductions['80c'] = val_80c
    
    val_80ccc = extract_val(r'Pension\s*Fund|80CCC')
    if val_80ccc > 0: deductions['80ccc'] = val_80ccc
    
    val_80ccd1 = extract_val(r'80CCD\(1\)(?!B)')
    if val_80ccd1 > 0: deductions['80ccd1'] = val_80ccd1
    
    val_80ccd1b = extract_val(r'80CCD\(1B\)')
    if val_80ccd1b > 0: deductions['80ccd1b'] = val_80ccd1b
    
    val_80ccd2 = extract_val(r'80CCD\(2\)|Employer\s*contribution')
    if val_80ccd2 > 0: deductions['80ccd2'] = val_80ccd2
    
    val_80d = extract_val(r'Health\s*Insurance|Medical\s*Premium|80D(?!D)')
    if val_80d > 0: deductions['80d'] = val_80d
    
    val_80e = extract_val(r'Education\s*Loan|80E')
    if val_80e > 0: deductions['80e'] = val_80e
    
    val_80g = extract_val(r'Donation|80G(?!G)')
    if val_80g > 0: deductions['80g'] = val_80g
    
    val_80tta = extract_val(r'Savings\s*Bank\s*Interest|80TTA')
    if val_80tta > 0: deductions['80tta'] = val_80tta
    
    return deductions
