"""
domains/budget/accounts.py - the account entity, and what a credit card actually is.

Why an account is not just a string on a row
--------------------------------------------
The domain modelled "which account" as two free-text columns, source_bank and
account_type, partly guessed from the upload's filename. That cannot represent two
accounts at one bank, and - more damaging - it gives a credit card the same semantics
as a savings account.

That last point is the one that makes the dashboard wrong rather than merely limited.

On a savings account, a debit is money leaving: it is spending. On a credit card, a
debit is a *purchase* - the money has not left any account yet, it has become debt -
and the credit on the card is the bill payment that clears it. Meanwhile the same bill
payment appears as a debit on the savings statement. Treated identically, a 30,000
card spend is counted once as card debits and again as the savings-account payment, so
the user's expenses read 60,000. The card's outstanding balance, which is the number
that actually matters for their credit score, is never shown at all.

So the account carries a `kind`, and the kind decides three things:

  * whether a debit is spending (savings) or borrowing (card)
  * whether a credit is income (savings) or debt repayment (card)
  * whether the balance is an asset or a liability

Identity without a registration step
------------------------------------
Accounts are derived from uploads rather than created. `account_key` is a pure function
of (bank, kind, last4), so any transaction can name its account without a lookup, and a
user who never customises anything never needs a row in budget_account_meta. The table
holds only what a statement cannot tell us: credit limit, statement and due day,
opening balance, a label.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from shared import db

logger = logging.getLogger(__name__)

SAVINGS = "savings"
CURRENT = "current"
SALARY = "salary"
CREDIT_CARD = "credit_card"

ASSET_KINDS = (SAVINGS, CURRENT, SALARY)

# Utilisation above this is the largest negative input to an Indian credit score, and
# the threshold issuers themselves report against.
UTILISATION_WARNING = 0.30
UTILISATION_CRITICAL = 0.50


def kind_from_account_type(account_type: Optional[str]) -> str:
    """
    Map the user-facing account_type string onto a kind.

    Kept tolerant: the string comes from a dropdown today but from a filename for old
    sessions, and an unrecognised value must degrade to "savings" rather than raise.
    """
    text = (account_type or "").strip().lower()
    if not text:
        return SAVINGS
    if "credit" in text and "card" in text:
        return CREDIT_CARD
    if "card" in text and "debit" not in text:
        return CREDIT_CARD
    if "current" in text:
        return CURRENT
    if "salary" in text:
        return SALARY
    return SAVINGS


def is_credit_card(account_type: Optional[str]) -> bool:
    return kind_from_account_type(account_type) == CREDIT_CARD


_LAST4 = re.compile(r"(?:x{2,}|\*{2,}|ending\s*)(\d{4})\b", re.IGNORECASE)


def extract_last4(text: Optional[str]) -> Optional[str]:
    """Pull a masked card/account tail ("XXXX1234", "ending 5678") out of free text."""
    if not text:
        return None
    m = _LAST4.search(str(text))
    return m.group(1) if m else None


def account_key(bank: Optional[str], account_type: Optional[str], last4: Optional[str] = None) -> str:
    """
    Stable identity for an account, computable from a transaction row alone.

    Deliberately derived rather than a surrogate id: it has to be reproducible from a
    frame that has just been decrypted, without a database round trip per row.
    """
    return f"{(bank or 'GENERIC').strip().upper()}:{kind_from_account_type(account_type)}:{(last4 or '-')}"


@dataclass
class Account:
    """One account, with whatever the statements and the metadata row together know."""

    account_key: str
    bank: str
    kind: str
    label: str = ""
    last4: Optional[str] = None
    credit_limit: Optional[float] = None
    statement_day: Optional[int] = None
    due_day: Optional[int] = None
    opening_balance: Optional[float] = None

    # Derived from the transactions.
    txn_count: int = 0
    inflow: float = 0.0
    outflow: float = 0.0
    first_txn: Optional[str] = None
    last_txn: Optional[str] = None
    closing_balance: Optional[float] = None
    months_covered: List[str] = field(default_factory=list)

    @property
    def is_card(self) -> bool:
        return self.kind == CREDIT_CARD

    @property
    def outstanding(self) -> Optional[float]:
        """
        What is owed on a card: purchases less payments and refunds.

        None for a deposit account, where "outstanding" is meaningless - callers must
        branch on the kind rather than reading a zero as "nothing owed".
        """
        if not self.is_card:
            return None
        return round(self.outflow - self.inflow, 2)

    @property
    def balance(self) -> Optional[float]:
        """
        Current balance of a deposit account.

        Prefers the running balance printed on the statement, which is authoritative,
        and falls back to opening + net flow when the export carries no balance column.
        """
        if self.is_card:
            return None
        if self.closing_balance is not None:
            return round(self.closing_balance, 2)
        if self.opening_balance is not None:
            return round(self.opening_balance + self.inflow - self.outflow, 2)
        return None

    @property
    def utilisation(self) -> Optional[float]:
        out = self.outstanding
        if not self.is_card or not self.credit_limit or self.credit_limit <= 0:
            return None
        return round(max(0.0, out) / self.credit_limit, 4)

    @property
    def utilisation_status(self) -> Optional[str]:
        u = self.utilisation
        if u is None:
            return None
        if u >= UTILISATION_CRITICAL:
            return "critical"
        if u >= UTILISATION_WARNING:
            return "warning"
        return "healthy"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "account_key": self.account_key,
            "bank": self.bank,
            "kind": self.kind,
            "label": self.label or self._default_label(),
            "last4": self.last4,
            "is_card": self.is_card,
            "credit_limit": self.credit_limit,
            "statement_day": self.statement_day,
            "due_day": self.due_day,
            "opening_balance": self.opening_balance,
            "balance": self.balance,
            "outstanding": self.outstanding,
            "utilisation": self.utilisation,
            "utilisation_status": self.utilisation_status,
            "inflow": round(self.inflow, 2),
            "outflow": round(self.outflow, 2),
            "txn_count": self.txn_count,
            "first_txn": self.first_txn,
            "last_txn": self.last_txn,
            "months_covered": self.months_covered,
        }

    def _default_label(self) -> str:
        pretty = {
            SAVINGS: "Savings", CURRENT: "Current",
            SALARY: "Salary", CREDIT_CARD: "Credit Card",
        }[self.kind]
        tail = f" ••{self.last4}" if self.last4 else ""
        return f"{self.bank} {pretty}{tail}"


# ---------------------------------------------------------------------------
# Deriving accounts from a transaction frame
# ---------------------------------------------------------------------------

def attach_account_keys(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add `account_key` and `account_kind` columns, vectorised.

    Cheap enough to run on every read, which is what lets account identity stay a
    derived property instead of something that has to be migrated into old payloads.
    """
    if df is None or df.empty:
        return df
    if "source_bank" not in df.columns:
        df["source_bank"] = "GENERIC"
    if "account_type" not in df.columns:
        df["account_type"] = "Savings Account"

    banks = df["source_bank"].fillna("GENERIC").astype(str).str.upper()
    kinds = df["account_type"].fillna("Savings Account").astype(str).map(kind_from_account_type)

    last4 = df["last4"] if "last4" in df.columns else pd.Series([None] * len(df), index=df.index)
    last4 = last4.fillna("-").astype(str).replace({"": "-", "nan": "-", "None": "-"})

    df["account_kind"] = kinds
    df["account_key"] = banks + ":" + kinds + ":" + last4
    return df


def summarise_accounts(df: pd.DataFrame, meta: Dict[str, Dict[str, Any]]) -> List[Account]:
    """
    One Account per distinct account_key present in the frame.

    `meta` is the budget_account_meta rows keyed by account_key; an account with no row
    still appears, using only what the statements know.
    """
    if df is None or df.empty:
        return []

    df = attach_account_keys(df)
    accounts: List[Account] = []

    for key, group in df.groupby("account_key", sort=False):
        bank, kind, last4 = _split_key(key)
        row = meta.get(key, {})

        inflow = float(group.loc[group["type"] == "credit", "amount"].sum())
        outflow = float(group.loc[group["type"] == "debit", "amount"].sum())

        dates = pd.to_datetime(group["date"], errors="coerce").dropna()
        closing = None
        if "balance" in group.columns and not dates.empty:
            # The balance on the chronologically last row is the account's closing
            # balance. Sorting by date rather than trusting file order: statements are
            # not always exported newest-last.
            ordered = group.assign(_d=pd.to_datetime(group["date"], errors="coerce")).dropna(subset=["_d"])
            ordered = ordered.sort_values("_d")
            tail = ordered["balance"].dropna()
            if not tail.empty:
                closing = float(tail.iloc[-1])

        accounts.append(Account(
            account_key=key,
            bank=bank,
            kind=kind,
            label=row.get("label", ""),
            last4=None if last4 == "-" else last4,
            credit_limit=row.get("credit_limit"),
            statement_day=row.get("statement_day"),
            due_day=row.get("due_day"),
            opening_balance=row.get("opening_balance"),
            txn_count=int(len(group)),
            inflow=inflow,
            outflow=outflow,
            first_txn=f"{dates.min():%Y-%m-%d}" if not dates.empty else None,
            last_txn=f"{dates.max():%Y-%m-%d}" if not dates.empty else None,
            closing_balance=closing,
            months_covered=sorted(dates.dt.strftime("%Y-%m").unique().tolist()) if not dates.empty else [],
        ))

    return sorted(accounts, key=lambda a: (a.kind != CREDIT_CARD, a.bank, a.account_key))


def _split_key(key: str):
    parts = str(key).split(":")
    while len(parts) < 3:
        parts.append("-")
    return parts[0], parts[1], parts[2]


# ---------------------------------------------------------------------------
# Metadata persistence
# ---------------------------------------------------------------------------

_META_FIELDS = ("label", "kind", "last4", "credit_limit", "statement_day", "due_day", "opening_balance")


def load_account_meta(user_id: str) -> Dict[str, Dict[str, Any]]:
    """All of a user's account metadata rows, keyed by account_key. One query."""
    if not user_id:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT account_key, label, kind, last4, credit_limit,
                   statement_day, due_day, opening_balance, archived
            FROM budget_account_meta WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()

    return {
        r[0]: {
            "label": r[1], "kind": r[2], "last4": r[3], "credit_limit": r[4],
            "statement_day": r[5], "due_day": r[6], "opening_balance": r[7],
            "archived": r[8],
        }
        for r in rows
    }


def upsert_account_meta(user_id: str, key: str, values: Dict[str, Any]) -> None:
    """
    Write the editable fields of one account, merging with what is already stored.

    Read-modify-write with a *static* statement rather than composing the column list
    from `values`. Interpolating identifiers into SQL is worth avoiding even when they
    come from a whitelist - and here it also produced a statement that could not be
    parsed, which is what test_sql_is_valid_postgres.py exists to catch.

    Merging in Python rather than with COALESCE(EXCLUDED.x, ...) keeps the PATCH
    semantics honest in both directions: a field the caller omits is preserved, and a
    field the caller explicitly sets to null is cleared. COALESCE cannot tell those two
    apart, so clearing a credit limit would silently do nothing.
    """
    fields = {k: v for k, v in values.items() if k in _META_FIELDS}
    if not fields:
        return

    with db.connect() as conn:
        existing = conn.execute(
            """
            SELECT label, kind, last4, credit_limit, statement_day, due_day, opening_balance
            FROM budget_account_meta WHERE user_id = %s AND account_key = %s
            """,
            (user_id, key),
        ).fetchone()

        current = dict(zip(_META_FIELDS, existing)) if existing else {
            "label": "", "kind": kind_from_account_type(key.split(":")[1] if ":" in key else None),
            "last4": None, "credit_limit": None, "statement_day": None,
            "due_day": None, "opening_balance": None,
        }
        current.update(fields)

        conn.execute(
            """
            INSERT INTO budget_account_meta (
                user_id, account_key, label, kind, last4,
                credit_limit, statement_day, due_day, opening_balance
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, account_key) DO UPDATE SET
                label           = EXCLUDED.label,
                kind            = EXCLUDED.kind,
                last4           = EXCLUDED.last4,
                credit_limit    = EXCLUDED.credit_limit,
                statement_day   = EXCLUDED.statement_day,
                due_day         = EXCLUDED.due_day,
                opening_balance = EXCLUDED.opening_balance,
                updated_at      = now()
            """,
            (
                user_id, key,
                current.get("label") or "",
                current.get("kind") or SAVINGS,
                current.get("last4"),
                current.get("credit_limit"),
                current.get("statement_day"),
                current.get("due_day"),
                current.get("opening_balance"),
            ),
        )
