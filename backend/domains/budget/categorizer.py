import pandas as pd
import re
from shared import db

_CATEGORY_RULES = [
    (r"\b(swiggy|zomato|dominos|mcdonalds|kfc|starbucks|pizza hut|subway|eatclub|freshmenu)\b", "Food & Dining"),
    (r"\b(uber|ola|rapido|irctc|makemytrip|goibibo|indigo|spicejet|redbus|cleartrip|yatra)\b", "Travel & Transport"),
    (r"\b(amazon|flipkart|myntra|ajio|blinkit|zepto|instamart|bigbasket|nykaa|reliancedigital|croma)\b", "Shopping & Groceries"),
    (r"\b(netflix|prime|spotify|hotstar|youtube|sonyliv|zee5|bookmyshow)\b", "Entertainment"),
    (r"\b(jio|airtel|vi|vodafone|bsnl|act fibernet|bescom|electricity|water|gas|dth|recharge|tatasky)\b", "Utilities & Bills"),
    (r"\b(zerodha|groww|upstox|kuvera|coin|angelone|indmoney|mutual fund|sip|ppf)\b", "Investments"),
    (r"\b(salary|payroll|wages|neft.*employer|rtgs.*employer)\b", "Salary/Income"),
    (r"\b(atm|cash withdrawal|withdrawal)\b", "Cash Withdrawal"),
    (r"\b(emi|loan|mortgage|hdfc bank personal loan|icici bank auto loan)\b", "Loans & EMI"),
    (r"\b(hospital|pharmacy|apollo|medplus|netmeds|1mg|practo|clinic)\b", "Health & Medical"),
    (r"\b(imps|neft|rtgs|upi|fund transfer|transfer to|transfer from|tfr to|tfr from)\b", "Transfers & Payments"),
    (r"\b(interest|int\.pd|credit interest)\b", "Interest Income"),
    (r"\b(fee|charges|annual fee|chg|sms charges|debit card fee)\b", "Bank Charges & Fees"),
    (r"\b(tax|gst|tds|income tax|advance tax)\b", "Taxes")
]

def categorize_transactions(df: pd.DataFrame, user_id: str = None) -> pd.DataFrame:
    """Adds a 'category' column based on user rules and fallback regex rules."""
    if df.empty:
        df["category"] = []
        return df

    categories = ["Uncategorized"] * len(df)
    
    # 1. Load User Rules
    user_rules = []
    if user_id:
        with db.connect() as conn:
            rows = conn.execute("SELECT rule_id, pattern, category, match_type FROM budget_rules WHERE user_id = %s", (user_id,)).fetchall()
            for r_id, pat, cat, m_type in rows:
                user_rules.append({"id": r_id, "pattern": pat, "category": cat, "type": m_type})
                
    # 2. Compile Default Rules
    compiled_default = [(re.compile(pattern, re.IGNORECASE), cat) for pattern, cat in _CATEGORY_RULES]
    
    # We will track rule matches to increment their counters
    matched_rule_ids = []
    
    descriptions = df["description"].tolist()
    for i, desc in enumerate(descriptions):
        desc_str = str(desc).strip()
        desc_lower = desc_str.lower()
        
        matched = False
        
        # Apply Custom Rules First
        for r in user_rules:
            is_match = False
            if r["type"] == "exact":
                is_match = desc_lower == r["pattern"].strip().lower()
            elif r["type"] == "regex":
                try:
                    if re.search(r["pattern"], desc_str, re.IGNORECASE):
                        is_match = True
                except:
                    pass
            else:
                # contains
                is_match = r["pattern"].strip().lower() in desc_lower
                
            if is_match:
                categories[i] = r["category"]
                matched_rule_ids.append(r["id"])
                matched = True
                break
                
        if matched:
            continue
            
        # Fallback to defaults
        for regex, category in compiled_default:
            if regex.search(desc_str):
                categories[i] = category
                break
                
    df["category"] = categories
    
    # Async background increment for matched rules could go here, but for now we just do it inline
    if matched_rule_ids:
        from collections import Counter
        counts = Counter(matched_rule_ids)
        if user_id:
            with db.connect() as conn:
                for r_id, count in counts.items():
                    conn.execute("UPDATE budget_rules SET match_count = match_count + %s WHERE rule_id = %s", (count, r_id))
                    
    return df
