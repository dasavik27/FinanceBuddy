"""
domains/budget/merchants.py - turning a bank narration into a name a human recognises.

"UPI/DR/402938471/SWIGGY BANGALORE/YESB/paytmqr2895@ybl/Payment from Ph" is what the
bank stores. "Swiggy" is what the user is looking for. Every merchant grouping in the
domain - top payees, recurring detection, anomalies, the Sankey leaves - is only as
good as this normalisation, which is why it is one module with one implementation
rather than a helper copied into each caller.

Three layers, cheapest first:

  1. strip the transport wrapper (UPI/POS/NEFT/IMPS reference numbers, VPA handles)
  2. match against known merchant tokens, so "SWIGGYBANGALORE" and "SWIGGY LTD" and
     "swiggy*order" all collapse to one name
  3. a per-user alias the user typed themselves, which always wins

Layer 3 matters more than it looks. Normalisation is heuristic and will always get
some merchants wrong; what makes that acceptable is that a correction is permanent
after one edit.
"""

from __future__ import annotations

import functools
import re
from typing import Dict, Optional

from shared import db

UNKNOWN = "Unknown Payee"

# The rail prefixes and reference blocks banks staple onto a narration.
_PREFIXES = re.compile(
    r"^(?:"
    r"upi[/\-](?:dr|cr)?[/\-]?\d*[/\-]?|"
    r"pos\s*\d*\s*|"
    # A rail name, an optional Dr/Cr, and an optional *reference*. The reference must
    # contain digits: an earlier `[a-z0-9]*` here matched the merchant itself, so
    # "ACH DR AMAZON PAY INDIA" lost the word Amazon and resolved to "PAY India".
    r"(?:neft|rtgs|imps|ach|nach)[\s/\-]*(?:dr|cr)?[\s/\-]*(?:[a-z]{0,4}\d{4,}[a-z0-9]*)?[\s/\-]*|"
    r"inf\*|inb\s*|bil[/\-]|e-?comm\s*|ecom\s*|mmt[/\-]|ift[/\-]|"
    r"tfr[\s/\-]*(?:to|from)?[\s/\-]*|"
    r"vps\s*|nfs\s*|atw[/\-]|atm[\s/\-]*"
    r")+",
    re.IGNORECASE,
)

# A VPA ("name@okaxis"), a long reference run, or a trailing rail suffix.
_VPA = re.compile(r"\b[\w.\-]+@[\w.\-]+\b")
_LONG_DIGITS = re.compile(r"\b\d{6,}\b")
_TRAILING_NOISE = re.compile(
    r"[\s/\-]*(?:payment\s*from\s*ph|payment\s*from|refno|ref\s*no|txn\s*id|"
    r"collect|autopay|mandate|si|emandate)\b.*$",
    re.IGNORECASE,
)
_PUNCT_RUN = re.compile(r"[\s/\\|*_,\-]{2,}")
_NON_NAME = re.compile(r"[^A-Za-z0-9&.' ]+")

# Recognised merchants. Matching on a squashed, lowercased form so spacing and
# punctuation in the narration do not matter.
_KNOWN = {
    "swiggy": "Swiggy", "zomato": "Zomato", "dominos": "Domino's", "mcdonald": "McDonald's",
    "starbucks": "Starbucks", "kfc": "KFC", "subway": "Subway", "blinkit": "Blinkit",
    "zepto": "Zepto", "instamart": "Instamart", "bigbasket": "BigBasket", "dmart": "DMart",
    "amazon": "Amazon", "flipkart": "Flipkart", "myntra": "Myntra", "ajio": "AJIO",
    "nykaa": "Nykaa", "meesho": "Meesho", "tatacliq": "Tata CLiQ", "croma": "Croma",
    "reliancedigital": "Reliance Digital", "decathlon": "Decathlon", "ikea": "IKEA",
    "netflix": "Netflix", "spotify": "Spotify", "hotstar": "Hotstar", "primevideo": "Prime Video",
    "sonyliv": "SonyLIV", "zee5": "ZEE5", "bookmyshow": "BookMyShow", "youtube": "YouTube",
    "audible": "Audible", "jiocinema": "JioCinema", "apple": "Apple",
    "uber": "Uber", "ola": "Ola", "rapido": "Rapido", "irctc": "IRCTC", "redbus": "RedBus",
    "makemytrip": "MakeMyTrip", "goibibo": "Goibibo", "indigo": "IndiGo", "vistara": "Vistara",
    "spicejet": "SpiceJet", "cleartrip": "Cleartrip", "yatra": "Yatra", "fastag": "FASTag",
    "jio": "Jio", "airtel": "Airtel", "vodafone": "Vi", "bsnl": "BSNL", "actfibernet": "ACT Fibernet",
    "zerodha": "Zerodha", "groww": "Groww", "upstox": "Upstox", "kuvera": "Kuvera",
    "angelone": "Angel One", "indmoney": "INDmoney", "smallcase": "smallcase",
    "etmoney": "ET Money", "paytmmoney": "Paytm Money",
    "apollo": "Apollo Pharmacy", "medplus": "MedPlus", "netmeds": "Netmeds",
    "pharmeasy": "PharmEasy", "practo": "Practo", "1mg": "Tata 1mg",
    "coursera": "Coursera", "udemy": "Udemy", "byju": "BYJU'S", "unacademy": "Unacademy",
    "paytm": "Paytm", "phonepe": "PhonePe", "googlepay": "Google Pay", "gpay": "Google Pay",
    "razorpay": "Razorpay", "billdesk": "BillDesk", "cred": "CRED",
}

_MAX_DISPLAY = 28


def normalise_key(description: Optional[str]) -> str:
    """
    The lookup key for a narration: lowercase, alphanumerics only.

    Used both for the known-merchant table and as the primary key of a user alias, so
    an alias set on one spelling of a merchant applies to all of them.
    """
    return re.sub(r"[^a-z0-9]", "", str(description or "").lower())


@functools.lru_cache(maxsize=4096)
def clean_merchant_name(description: Optional[str]) -> str:
    """
    A displayable merchant name.

    Cached because it is called once per transaction by several engines over the same
    frame, and real statements repeat the same few hundred narrations. The cache is
    keyed on the raw narration and the function is pure, so there is nothing to
    invalidate; the bound keeps it from growing without limit.
    """
    if description is None:
        return UNKNOWN
    raw = str(description).strip()
    if not raw or raw.lower() in ("nan", "none", "null"):
        return UNKNOWN

    text = _PREFIXES.sub("", raw)
    text = _TRAILING_NOISE.sub("", text)
    text = _VPA.sub(" ", text)
    text = _LONG_DIGITS.sub(" ", text)

    # Known merchant anywhere in what remains. Checked before the cosmetic tidy-up so a
    # match is not lost to truncation.
    squashed = normalise_key(text)
    for token, display in _KNOWN.items():
        if token in squashed:
            return display

    text = _NON_NAME.sub(" ", text)
    text = _PUNCT_RUN.sub(" ", text).strip()

    if not text:
        # Everything was noise - fall back to the raw narration so the row is still
        # identifiable, rather than collapsing unrelated payees into one bucket.
        fallback = _NON_NAME.sub(" ", raw).strip()
        return (fallback[:_MAX_DISPLAY] or UNKNOWN).title()

    if len(text) > _MAX_DISPLAY:
        text = text[: _MAX_DISPLAY - 1].rstrip() + "…"

    # Title-case, but leave acronyms that are already upper-case alone.
    return " ".join(w if w.isupper() and len(w) <= 4 else w.capitalize() for w in text.split())


def load_aliases(user_id: Optional[str]) -> Dict[str, str]:
    """The user's own merchant renames, keyed by normalised narration."""
    if not user_id:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT normalised, display_name FROM budget_merchant_aliases WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def set_alias(user_id: str, description: str, display_name: str) -> str:
    """Remember a rename. Returns the key it was stored under."""
    key = normalise_key(description)
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO budget_merchant_aliases (user_id, normalised, display_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, normalised) DO UPDATE SET display_name = EXCLUDED.display_name
            """,
            (user_id, key, display_name.strip()[:64]),
        )
    return key


def apply_aliases(description: Optional[str], aliases: Dict[str, str]) -> str:
    """Resolve a narration, letting a user alias override the heuristic."""
    if aliases:
        hit = aliases.get(normalise_key(description))
        if hit:
            return hit
    return clean_merchant_name(description)
