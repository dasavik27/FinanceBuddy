"""
domains/budget/natures.py - mapping a category onto its 50/30/20 nature.

Lifted out of the analytics router so the Sankey builder, the envelope report and the
overview all classify identically. It was previously a private function inside the
router module, which meant anything else that needed it would either import from a
router (a circular import waiting to happen) or quietly reimplement it and drift.

"needs" / "wants" / "investments" / "transfers" / "income". Categories are open-ended -
users create their own through rules - so this has to work on an unseen name, hence the
keyword pass after the exact-match table.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict

NEEDS = "needs"
WANTS = "wants"
INVESTMENTS = "investments"
TRANSFERS = "transfers"
INCOME = "income"

# Exact matches for the categories the default rules produce. Keys are lowercase
# because the lookup lowercases - an earlier version had "interest Income" here with a
# capital I, which could never match and was silently dead.
_EXACT: Dict[str, str] = {
    "utilities & bills": NEEDS,
    "loans & emi": NEEDS,
    "health & medical": NEEDS,
    "taxes": NEEDS,
    "bank charges & fees": NEEDS,
    "rent & housing": NEEDS,
    "insurance": NEEDS,
    "education": NEEDS,
    "food & dining": WANTS,
    "shopping & groceries": WANTS,
    "entertainment": WANTS,
    "travel & transport": WANTS,
    "investments": INVESTMENTS,
    "salary/income": INCOME,
    "interest income": INCOME,
    "transfers & payments": TRANSFERS,
    "cash withdrawal": TRANSFERS,
    "credit card payment": TRANSFERS,
}

_NEEDS_TOKENS = (
    "utilit", "bill", "electr", "water", "gas", "recharge", "wifi", "broadband",
    "rent", "emi", "loan", "mortgage", "insur", "medic", "health", "doctor", "pharm",
    "hospital", "tax", "gst", "tds", "fee", "charg", "grocer", "ration", "school",
    "tuition", "college", "childcare", "commute",
)
_INVESTMENT_TOKENS = (
    "invest", "sip", "mutual fund", "stock", "equity", "demat", "groww", "zerodha",
    "nps", "ppf", "elss", "gold", "crypto", "wealth", "recurring deposit", "fixed deposit",
)
_TRANSFER_TOKENS = (
    "transfer", "tfr", "atm", "cash", "self", "card pay", "credit card pay", "cc bill",
    "settle", "wallet load",
)
_INCOME_TOKENS = (
    "salary", "wage", "payroll", "dividend", "interest", "refund", "cashback",
    "reimburse", "bonus", "stipend",
)
_WANTS_TOKENS = (
    "dine", "dining", "food", "restaurant", "swiggy", "zomato", "cafe", "coffee",
    "shop", "apparel", "cloth", "fashion", "movie", "cinema", "netflix", "ott", "game",
    "travel", "flight", "hotel", "trip", "vacation", "cab", "uber", "ola", "lifestyle",
    "hobby", "subscription", "gift",
)


@lru_cache(maxsize=1024)
def nature_of(category_name: str) -> str:
    """
    The 50/30/20 nature of a category name, standard or user-created.

    Defaults to "wants". That is the conservative direction: an unclassified expense
    counted as discretionary makes the wants percentage look worse than it is, which
    prompts the user to categorise it. Defaulting to "needs" would flatter the number
    and hide the gap.

    Cached because the miss path is up to ~120 substring scans across five token
    tuples, and the callers (the 50/30/20 engine, the Sankey builder, the envelope
    report) ask about the same handful of category names repeatedly. Pure function of
    its argument over a bounded key space - the category vocabulary - so the cache
    cannot go stale or grow without limit.
    """
    if not category_name or not str(category_name).strip():
        return WANTS

    text = str(category_name).strip().lower()

    exact = _EXACT.get(text)
    if exact:
        return exact

    # Order matters: "credit card payment" contains "pay" and would otherwise be caught
    # by a looser bucket, and investment names often contain "fund" and "deposit".
    for tokens, nature in (
        (_TRANSFER_TOKENS, TRANSFERS),
        (_INVESTMENT_TOKENS, INVESTMENTS),
        (_NEEDS_TOKENS, NEEDS),
        (_INCOME_TOKENS, INCOME),
        (_WANTS_TOKENS, WANTS),
    ):
        if any(token in text for token in tokens):
            return nature

    return WANTS
