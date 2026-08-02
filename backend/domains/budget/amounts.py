"""
domains/budget/amounts.py - turning what a bank prints into a signed number.

The bug this replaces
---------------------
The whole of amount parsing used to be:

    amount = float(re.sub(r'[^\\d.]', '', str(value)))

which is wrong in four separate ways, each of them silent:

  "-1,500.00"   -> 1500.00   the minus sign is stripped, so a refund books as a spend
  "(2,300.50)"  -> 2300.50   accounting parentheses mean negative; also stripped
  "1.234,56"    -> raises     ValueError, uncaught on one of the two branches -> HTTP 500
  "1e3"         -> 13.0       the 'e' is stripped and the digits are concatenated

None of these announce themselves. A stripped minus turns every reversal, refund and
chargeback into an expense, which then flows into the 50/30/20 split, the savings rate
and the health score.

What a bank actually prints
---------------------------
Across the formats this domain accepts, an amount cell can carry: a currency symbol
(Rs, Rs., INR, the rupee sign), thin/non-breaking spaces as grouping, Indian lakh
grouping (5,00,000.00), European grouping (1.500,00), a trailing or leading Cr/Dr
marker, a unicode minus or en-dash instead of ASCII '-', accounting parentheses, and
a trailing '-' (some mainframe exports put the sign after the number).

Deciding which separator is the decimal point
---------------------------------------------
There is no locale to consult - the file does not say. The rule used here is the one
that is unambiguous in practice:

  * the *last* separator is the decimal point if 1-2 digits follow it
  * a separator with exactly 3 digits after it is a grouping separator
  * more than 3 trailing digits is not a separator in any convention -> reject

So "1,500" is 1500 (grouping) and "1,50" is 1.50 (decimal), "5,00,000.00" is 500000.00,
and "1.500,00" is 1500.00. Anything that still contains a non-digit after the
separators are resolved is rejected rather than coerced.

Rejection returns None. The caller skips the row and counts it, so a statement that
parses badly reports "412 of 430 rows parsed" instead of quietly booking 18 wrong
numbers - which is the behaviour the old code had.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

# Currency noise, grouping whitespace, and the several dash characters that show up in
# exports from Windows-1252 and UTF-8 systems alike.
_CURRENCY = re.compile(r"(?:₹|rs\.?|inr|\$|usd)", re.IGNORECASE)
_SPACES = re.compile(r"[\s   ]+")
_DASHES = "−–—"  # minus sign, en dash, em dash

# A Cr/Dr marker on either side, with or without a separating space.
#
# The body is required to contain a digit rather than the marker being delimited by \b.
# Grouping whitespace is removed *after* this runs, so "1,500.00 Cr" may already be
# "1,500.00Cr" - and there is no word boundary between "0" and "C". Requiring a digit in
# the body is what stops a bare "Cr" cell from being mistaken for an amount.
_MARKER_TRAILING = re.compile(r"^(?P<body>.*\d)\s*\.?\s*(?P<mark>cr|dr)\.?$", re.IGNORECASE)
_MARKER_LEADING = re.compile(r"^(?P<mark>cr|dr)\.?\s*(?P<body>.*\d.*)$", re.IGNORECASE)

_SEPARATORS = ".,'"


@dataclass(frozen=True)
class Money:
    """
    A parsed amount.

    `magnitude` is always non-negative - the size of the movement. `negative` records
    that the cell itself carried a sign (minus, parentheses, trailing dash), and
    `marker` records an explicit Cr/Dr. The caller combines these with the column the
    value came from, because the meaning of "negative" depends on that column: -500 in
    a *Withdrawal* column is a reversed withdrawal, i.e. money in.
    """

    magnitude: float
    negative: bool = False
    marker: Optional[str] = None  # "cr" | "dr" | None

    @property
    def is_zero(self) -> bool:
        return self.magnitude == 0.0


def _strip_marker(text: str) -> tuple[str, Optional[str]]:
    """Pull a Cr/Dr marker off either end, returning the remainder and the marker."""
    for pattern in (_MARKER_TRAILING, _MARKER_LEADING):
        m = pattern.match(text)
        if m:
            body = m.group("body").strip()
            # A bare "Cr" with no digits is not an amount; leave it for the digit check
            # to reject rather than returning an empty body with a marker attached.
            if body:
                mark = m.group("mark").lower()
                return body, ("cr" if mark in ("cr", "c") else "dr")
    return text, None


def _resolve_decimal(text: str) -> Optional[Decimal]:
    """
    Turn a digits-and-separators string into a Decimal, or None if it is not one.

    See the module docstring for the separator rule. Everything that is not a digit
    after the rule is applied is a rejection, not a character to drop.
    """
    if not text or not any(ch.isdigit() for ch in text):
        return None

    positions = [i for i, ch in enumerate(text) if ch in _SEPARATORS]

    if not positions:
        digits = text
        fraction = ""
    else:
        last = positions[-1]
        tail = text[last + 1:]
        if not tail.isdigit():
            return None
        if len(tail) <= 2:
            # Decimal separator: everything before it is the integer part.
            digits = text[:last]
            fraction = tail
        elif len(tail) == 3:
            # Grouping separator; the whole string is an integer.
            digits = text
            fraction = ""
        else:
            # No convention groups in fours or puts three-plus digits after a decimal
            # point in a money column.
            return None

    # Strip the remaining grouping separators and require what is left to be digits.
    # This is the check the old regex-substitution approach skipped: it deleted the
    # offending characters instead of noticing them.
    integer = "".join(ch for ch in digits if ch not in _SEPARATORS)
    if integer == "":
        integer = "0"
    if not integer.isdigit():
        return None

    try:
        return Decimal(f"{integer}.{fraction}" if fraction else integer)
    except InvalidOperation:
        return None


def parse_amount(raw) -> Optional[Money]:
    """
    Parse one amount cell. Returns None when the cell is not an amount at all.

    None covers blanks, NaN, header text that survived into the data rows, and values
    malformed enough that any interpretation would be a guess. Callers must treat None
    as "skip and count", never as zero - a skipped row is visible in the parse report,
    a zero is not.
    """
    if raw is None:
        return None

    # Fast path for values pandas already typed as numeric. NaN is not an amount;
    # bool is excluded because True would otherwise parse as 1.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            return None
        if value != value:  # NaN
            return None
        return Money(magnitude=float(abs(value)), negative=value < 0)

    text = str(raw).strip()
    if not text or text.lower() in ("nan", "none", "null", "-", "--"):
        return None

    text = _CURRENCY.sub("", text)
    for dash in _DASHES:
        text = text.replace(dash, "-")
    # Collapse runs of whitespace to a single space rather than deleting them outright.
    # Deletion here is what previously hid the Cr/Dr marker: "1,500.00 Cr" became
    # "1,500.00Cr", and the marker pattern could no longer find its left edge. Spaces
    # used as grouping are removed below, once the marker and sign are off.
    text = _SPACES.sub(" ", text).strip()

    negative = False

    # Accounting parentheses. Checked before the sign so "(-500)" is not read twice.
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    text, marker = _strip_marker(text)

    # Leading or trailing sign. The trailing form appears in mainframe exports.
    if text.startswith(("-", "+")):
        negative = negative or text[0] == "-"
        text = text[1:].strip()
    elif text.endswith(("-", "+")):
        negative = negative or text[-1] == "-"
        text = text[:-1].strip()

    # Whatever whitespace survives is grouping ("1 234,50"); only now is it safe to drop.
    text = _SPACES.sub("", text)

    value = _resolve_decimal(text)
    if value is None:
        return None

    return Money(magnitude=float(round(value, 2)), negative=negative, marker=marker)


def direction_from(
    money: Optional[Money],
    column_direction: Optional[str] = None,
    type_hint: Optional[str] = None,
) -> str:
    """
    Resolve a Money plus its context into "credit" or "debit".

    Precedence, strongest evidence first:

      1. an explicit Cr/Dr marker in the cell itself
      2. a type column ("CR", "Credit", "C", "Dr", ...)
      3. the column the value came from ("debit" / "credit")

    A cell-level minus *flips* whatever the above decided, because a negative in a
    Withdrawal column is a reversed withdrawal. This is the case the old parser lost
    entirely, and it is not rare: refunds, failed-transaction reversals and chargebacks
    are all posted this way.

    A None `money` means the caller has nothing to classify. It is not an error worth
    raising from inside a per-row parse loop - one unparseable cell must not turn into
    a 500 for the whole upload - so it resolves to the column's own direction.
    """
    if money is None:
        return column_direction or "debit"

    direction = None

    if money.marker:
        direction = "credit" if money.marker == "cr" else "debit"
    elif type_hint:
        hint = str(type_hint).strip().lower()
        if hint.startswith(("cr", "c ", "credit", "deposit", "inflow", "in")) or hint == "c":
            direction = "credit"
        elif hint.startswith(("dr", "d ", "debit", "withdraw", "outflow", "out")) or hint == "d":
            direction = "debit"

    if direction is None:
        direction = column_direction or "debit"

    if money.negative:
        direction = "debit" if direction == "credit" else "credit"

    return direction
