"""
domains/budget/categorizer.py - assigning a category to each transaction.

Two structural changes from the original.

**No database access from inside categorization.** It used to open a connection to read
the user's rules, and a second one to increment `match_count`, from inside a loop that
its caller was already running inside an open transaction. With a six-connection pool
that deadlocked under concurrency (see the note in sessions.py). Rules are now loaded
by an explicit call, categorization is pure, and the caller decides when to persist
match counts.

**Patterns are compiled once.** The old loop re-read `r["type"]` and called `re.search`
with a raw pattern string for every transaction, so a 5,000-row statement recompiled
each user regex 5,000 times. Compilation happens in rules_safety.compile_rules, which
also re-validates stored patterns - a rule written before the ReDoS guard existed is
not trusted just because it is already in the table.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import List, Optional, Tuple

import pandas as pd

from shared import db
from domains.budget.rules_safety import CompiledRule, clip_subject, compile_rules

logger = logging.getLogger(__name__)

UNCATEGORIZED = "Uncategorized"

# Fallback rules, applied only where no user rule matched. Ordered: the first match
# wins, so the specific patterns must precede the generic transfer/UPI ones - an
# "UPI/SWIGGY" narration should be Food, not Transfers.
_CATEGORY_RULES: List[Tuple[str, str]] = [
    (r"\b(swiggy|zomato|dominos|mcdonalds|kfc|starbucks|pizza\s*hut|subway|eatclub|freshmenu|dunzo|faasos|behrouz|chaayos|barbeque)\b", "Food & Dining"),
    (r"\b(uber|ola|rapido|irctc|makemytrip|goibibo|indigo|spicejet|redbus|cleartrip|yatra|vistara|airasia|fastag|petrol|diesel|hpcl|bpcl|iocl|shell)\b", "Travel & Transport"),
    (r"\b(amazon|flipkart|myntra|ajio|blinkit|zepto|instamart|bigbasket|dmart|nykaa|reliancedigital|croma|meesho|tatacliq|decathlon|ikea)\b", "Shopping & Groceries"),
    (r"\b(netflix|primevideo|spotify|hotstar|youtube|sonyliv|zee5|bookmyshow|jiocinema|apple\.com/bill|audible)\b", "Entertainment"),
    (r"\b(jio|airtel|vodafone|bsnl|act\s*fibernet|bescom|msedcl|tneb|electricity|water\s*bill|gas\s*bill|dth|recharge|tatasky|broadband)\b", "Utilities & Bills"),
    (r"\b(zerodha|groww|upstox|kuvera|angelone|indmoney|smallcase|mutual\s*fund|sip|ppf|nps|elss|etmoney|paytmmoney)\b", "Investments"),
    (r"\b(rent|landlord|maintenance\s*charge|society\s*maintenance|brokerage\s*rent)\b", "Rent & Housing"),
    (r"\b(salary|payroll|wages|stipend)\b", "Salary/Income"),
    (r"\b(atm|cash\s*withdrawal|cash\s*wdl|nfs\s*cash)\b", "Cash Withdrawal"),
    (r"\b(emi|loan|mortgage|instalment|installment)\b", "Loans & EMI"),
    (r"\b(lic|insurance|premium|policybazaar|hdfc\s*life|icici\s*pru|max\s*life|star\s*health)\b", "Insurance"),
    (r"\b(hospital|pharmacy|apollo|medplus|netmeds|1mg|pharmeasy|practo|clinic|diagnostic|lab)\b", "Health & Medical"),
    (r"\b(school|college|university|tuition|coursera|udemy|byju|unacademy|vedantu|fees?)\b", "Education"),
    (r"\b(credit\s*card\s*payment|card\s*payment|cc\s*payment|autopay\s*card|bill\s*payment\s*card)\b", "Credit Card Payment"),
    (r"\b(interest|int\.pd|credit\s*interest|int\s*credit)\b", "Interest Income"),
    (r"\b(charges?|annual\s*fee|sms\s*charge|debit\s*card\s*fee|amc|penalty|late\s*fee|convenience\s*fee)\b", "Bank Charges & Fees"),
    (r"\b(gst|tds|income\s*tax|advance\s*tax|self\s*assessment)\b", "Taxes"),
    (r"\b(imps|neft|rtgs|upi|fund\s*transfer|transfer\s*to|transfer\s*from|tfr\s*to|tfr\s*from|ach|nach)\b", "Transfers & Payments"),
]

_COMPILED_DEFAULTS = [(re.compile(p, re.IGNORECASE), c) for p, c in _CATEGORY_RULES]


def load_user_rules(user_id: Optional[str]) -> List[CompiledRule]:
    """
    Fetch and compile this user's rules. One query, one connection, done up front.

    Returns an empty list for an anonymous caller rather than raising: categorization
    still works off the default rules.
    """
    if not user_id:
        return []
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT rule_id, pattern, category, match_type FROM budget_rules "
            "WHERE user_id = %s ORDER BY created_at",
            (user_id,),
        ).fetchall()
    return compile_rules(rows)


def categorize_transactions(
    df: pd.DataFrame,
    rules: Optional[List[CompiledRule]] = None,
    user_id: Optional[str] = None,
) -> Tuple[pd.DataFrame, Counter]:
    """
    Add a 'category' column. Returns the frame and a Counter of rule_id -> hits.

    Pure with respect to the database when `rules` is supplied. Passing `user_id`
    instead is a convenience for callers not already holding a connection; it must not
    be used from inside an open transaction.
    """
    if rules is None:
        rules = load_user_rules(user_id)

    if df is None or df.empty:
        if df is not None and "category" not in df.columns:
            df["category"] = pd.Series(dtype="object")
        return df, Counter()

    if "description" not in df.columns:
        df["category"] = UNCATEGORIZED
        return df, Counter()

    descriptions = df["description"].tolist()
    categories: List[str] = [UNCATEGORIZED] * len(descriptions)
    hits: Counter = Counter()

    # A description repeated across rows - the same merchant, the same subscription -
    # resolves to the same category, so the rule sweep runs once per distinct string.
    # Real statements are dominated by repeats, which makes this the difference between
    # O(rows x rules) and O(distinct x rules).
    resolved: dict = {}

    for i, raw in enumerate(descriptions):
        text = clip_subject(raw if raw is not None else "")
        cached = resolved.get(text)
        if cached is not None:
            category, rule_id = cached
            categories[i] = category
            if rule_id:
                hits[rule_id] += 1
            continue

        lowered = text.lower()
        category = UNCATEGORIZED
        rule_id = None

        for rule in rules:
            if rule.matches(text, lowered):
                category = rule.category
                rule_id = rule.rule_id
                break

        if rule_id is None:
            for regex, default_category in _COMPILED_DEFAULTS:
                if regex.search(text):
                    category = default_category
                    break

        resolved[text] = (category, rule_id)
        categories[i] = category
        if rule_id:
            hits[rule_id] += 1

    df["category"] = categories
    return df, hits


def persist_match_counts(hits: Counter) -> None:
    """
    Record rule hit counts.

    Separate from categorization so it can be called outside whatever transaction the
    caller is running, and skipped entirely on read-only paths. Failure is logged, not
    raised: a statistics counter must not fail an upload.
    """
    if not hits:
        return
    try:
        with db.connect() as conn:
            for rule_id, count in hits.items():
                conn.execute(
                    "UPDATE budget_rules SET match_count = match_count + %s WHERE rule_id = %s",
                    (count, rule_id),
                )
    except Exception as e:
        logger.warning("[budget.rules] could not update match counts: %s", e)
