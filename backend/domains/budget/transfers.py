"""
domains/budget/transfers.py - telling your own money apart from your actual income.

The problem
-----------
Move 50,000 from HDFC to ICICI and, with both statements uploaded, the domain sees a
50,000 debit and a 50,000 credit. Counted naively that is 50,000 of expense and 50,000
of income. Every headline number is then wrong in a way that scales with how often the
user moves money around: total income, total expense, savings rate, average monthly
burn, and the 50/30/20 split - which is computed as a percentage *of income* - all
inflate together.

Credit cards make it worse. A card bill payment is a debit on the savings statement and
a credit on the card statement. Without pairing, the card's purchases are counted as
spend once and the bill payment that settles them is counted as spend again.

What can and cannot be proved
-----------------------------
A transfer is only *demonstrable* when both legs are present: a debit in one account
and a matching credit in another. A narration saying "TRANSFER" proves nothing on its
own - a payment to a friend often says the same thing, and excluding it would silently
delete a real expense.

So pairing is the only thing that reclassifies. Description hints are used to *rank*
candidates when several are plausible, never to classify a lone transaction. This
errs toward counting something as a real expense, which is the safe direction: an
overstated expense is visible to the user, a wrongly hidden one is not.

Users can override either way; see budget_txn_flags in migration 0007.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from shared import db
from domains.budget.accounts import attach_account_keys

logger = logging.getLogger(__name__)

# How far apart the two legs may be. Inter-bank transfers in India settle same-day on
# IMPS/UPI and up to two working days on NEFT/cheque; four days covers a Friday
# transfer landing on Monday without pairing genuinely unrelated transactions.
MAX_LAG_DAYS = 4

# Amounts must match to the paisa. A tolerance here would pair a 5,000 rent payment
# with a 5,000 salary advance; exactness is what makes the heuristic safe enough to
# subtract from the user's income.
_AMOUNT_PRECISION = 2

_TRANSFER_HINTS = (
    "transfer", "tfr", "self", "imps", "neft", "rtgs", "upi/p2a",
    "credit card payment", "card payment", "cc payment", "cardpayment",
    "autopay", "bill payment", "payment received", "own account",
)


@dataclass
class TransferPair:
    """One matched movement between two of the user's own accounts."""

    debit_txn_id: str
    credit_txn_id: str
    from_account: str
    to_account: str
    amount: float
    debit_date: str
    credit_date: str
    lag_days: int
    confidence: str
    is_card_payment: bool

    def as_dict(self) -> dict:
        return {
            "debit_txn_id": self.debit_txn_id,
            "credit_txn_id": self.credit_txn_id,
            "from_account": self.from_account,
            "to_account": self.to_account,
            "amount": self.amount,
            "debit_date": self.debit_date,
            "credit_date": self.credit_date,
            "lag_days": self.lag_days,
            "confidence": self.confidence,
            "is_card_payment": self.is_card_payment,
        }


def _hint_score(description: str) -> int:
    text = (description or "").lower()
    return sum(1 for hint in _TRANSFER_HINTS if hint in text)


def detect_transfers(df: pd.DataFrame) -> List[TransferPair]:
    """
    Pair debits with credits across different accounts.

    Bucketed by exact amount, so this is O(n) in the number of transactions rather than
    the O(n^2) a pairwise scan would cost - which matters because it runs over every
    transaction the user has ever uploaded.

    Within a bucket the matching is greedy on (smallest lag, strongest narration hint).
    Greedy is adequate because exact-amount collisions within a four-day window are
    rare; when they do collide, any consistent pairing yields the same totals, and the
    totals are what the dashboard uses.
    """
    if df is None or df.empty or "type" not in df.columns:
        return []

    df = attach_account_keys(df)
    if df["account_key"].nunique() < 2:
        # Nothing to pair against. A single account cannot demonstrate a transfer.
        return []

    work = df.copy()
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["_date"])
    if work.empty:
        return []

    work["_amt"] = work["amount"].round(_AMOUNT_PRECISION)

    debits: Dict[float, List[tuple]] = defaultdict(list)
    credits: Dict[float, List[tuple]] = defaultdict(list)

    # Zipped column lists rather than itertuples: itertuples renames any column that is
    # not a valid identifier - which includes the leading-underscore working columns
    # above - to positional _1/_2, so attribute access on them silently reads the wrong
    # field. Zipping names each column explicitly and is faster besides.
    n = len(work)
    txn_ids = work["txn_id"].tolist() if "txn_id" in work.columns else [None] * n
    dates = work["_date"].tolist()
    amounts = work["_amt"].tolist()
    types = work["type"].tolist()
    keys = work["account_key"].tolist()
    kinds = work["account_kind"].tolist() if "account_kind" in work.columns else ["savings"] * n
    descs = (
        work["description"].fillna("").astype(str).tolist()
        if "description" in work.columns else [""] * n
    )

    for txn_id, date, amount, kind_of_txn, acct, acct_kind, desc in zip(
        txn_ids, dates, amounts, types, keys, kinds, descs
    ):
        entry = (txn_id, date, acct, desc, acct_kind)
        if kind_of_txn == "debit":
            debits[amount].append(entry)
        elif kind_of_txn == "credit":
            credits[amount].append(entry)

    pairs: List[TransferPair] = []
    used_credits: Set[str] = set()

    for amount, debit_rows in debits.items():
        candidates = credits.get(amount)
        if not candidates:
            continue

        for d_id, d_date, d_acct, d_desc, d_kind in debit_rows:
            best = None
            best_rank = None

            for c_id, c_date, c_acct, c_desc, c_kind in candidates:
                if c_id in used_credits or c_acct == d_acct:
                    continue
                lag = (c_date - d_date).days
                # The credit may land the same day or after; a credit *before* its
                # debit by more than a day is not the same movement.
                if lag < -1 or lag > MAX_LAG_DAYS:
                    continue

                hints = _hint_score(d_desc) + _hint_score(c_desc)
                rank = (abs(lag), -hints)
                if best_rank is None or rank < best_rank:
                    best_rank, best = rank, (c_id, c_date, c_acct, c_desc, c_kind, lag, hints)

            if best is None:
                continue

            c_id, c_date, c_acct, c_desc, c_kind, lag, hints = best
            used_credits.add(c_id)

            pairs.append(TransferPair(
                debit_txn_id=d_id,
                credit_txn_id=c_id,
                from_account=d_acct,
                to_account=c_acct,
                amount=float(amount),
                debit_date=f"{d_date:%Y-%m-%d}",
                credit_date=f"{c_date:%Y-%m-%d}",
                lag_days=int(lag),
                # Same-day with a corroborating narration is as certain as this gets.
                # A four-day lag with no hint is plausible but worth showing the user.
                confidence="high" if (abs(lag) <= 1 and hints) else "medium" if hints or abs(lag) <= 1 else "low",
                # A credit landing on a card account is that card's bill being paid.
                is_card_payment=(c_kind == "credit_card"),
            ))

    return pairs


def load_flags(user_id: Optional[str]) -> Dict[str, str]:
    """User overrides of the heuristic, keyed by txn_id."""
    if not user_id:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT txn_id, flag FROM budget_txn_flags WHERE user_id = %s", (user_id,)
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def set_flag(user_id: str, txn_id: str, flag: Optional[str]) -> None:
    """Force a transaction to be treated as a transfer, or force it back. None clears."""
    with db.connect() as conn:
        if flag is None:
            conn.execute(
                "DELETE FROM budget_txn_flags WHERE user_id = %s AND txn_id = %s",
                (user_id, txn_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO budget_txn_flags (user_id, txn_id, flag) VALUES (%s, %s, %s)
                ON CONFLICT (user_id, txn_id) DO UPDATE SET flag = EXCLUDED.flag
                """,
                (user_id, txn_id, flag),
            )


def mark_transfers(
    df: pd.DataFrame,
    pairs: Optional[List[TransferPair]] = None,
    flags: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, List[TransferPair]]:
    """
    Add an `is_transfer` column, honouring user overrides.

    Returns the frame and the pairs actually used, so a caller can show the user what
    was netted out rather than presenting a number they cannot audit.
    """
    if df is None or df.empty:
        return df, []

    if pairs is None:
        pairs = detect_transfers(df)
    flags = flags or {}

    transfer_ids: Set[str] = set()
    for pair in pairs:
        transfer_ids.add(pair.debit_txn_id)
        transfer_ids.add(pair.credit_txn_id)

    # Overrides last, so an explicit user decision always wins over the heuristic.
    for txn_id, flag in flags.items():
        if flag == "transfer":
            transfer_ids.add(txn_id)
        elif flag == "not_transfer":
            transfer_ids.discard(txn_id)

    if "txn_id" in df.columns:
        df["is_transfer"] = df["txn_id"].isin(transfer_ids)
    else:
        df["is_transfer"] = False

    kept = [
        p for p in pairs
        if flags.get(p.debit_txn_id) != "not_transfer"
        and flags.get(p.credit_txn_id) != "not_transfer"
    ]
    return df, kept


def split_real_flows(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Partition into (real, internal).

    Real flows are what income, expense, savings rate and the 50/30/20 split must be
    computed from. Internal movement is still shown - the user wants to see it - but in
    its own lane, not added to either side.
    """
    if df is None or df.empty:
        return df, df
    if "is_transfer" not in df.columns:
        return df, df.iloc[0:0]
    return df[~df["is_transfer"]], df[df["is_transfer"]]
