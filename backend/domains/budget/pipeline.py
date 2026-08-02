"""
domains/budget/pipeline.py - one way to get from a session id to an analysable frame.

Every read endpoint needs the same four things: the caller's transactions, account
identity attached, transfers marked, and the per-account rollup. Doing that in each
router is how the four of them drift apart - one forgets to exclude transfers and
reports a savings rate 40 points too high, and nothing catches it.

So it happens once, here, and the result is memoized on the frame's content hash. The
authorization check is inside sessions.get_budget_session(), which this calls, so there
is no path to a frame that skips it.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.budget import derived
from domains.budget.accounts import (
    Account,
    attach_account_keys,
    load_account_meta,
    summarise_accounts,
)
from domains.budget.merchants import apply_aliases, load_aliases
from domains.budget.sessions import get_all_budget_sessions, get_budget_session
from domains.budget.transfers import TransferPair, detect_transfers, load_flags, mark_transfers

logger = logging.getLogger(__name__)


@dataclass
class BudgetContext:
    """Everything the read endpoints share, computed once per request."""

    df: pd.DataFrame
    accounts: List[Account]
    transfers: List[TransferPair]
    meta: Dict[str, Any]

    # Digests of the two user-editable inputs that are *not* recoverable from the frame:
    # transfer overrides and account metadata (labels, credit limits, opening balances).
    # Any cache keyed on this context has to include them, or an account rename serves
    # the previous label out of the memo until the transactions themselves change.
    flag_signature: str = "none"
    meta_signature: str = "none"

    @property
    def real(self) -> pd.DataFrame:
        """Transactions excluding internal movement - the basis for every total."""
        if self.df.empty or "is_transfer" not in self.df.columns:
            return self.df
        return self.df[~self.df["is_transfer"]]

    @property
    def internal(self) -> pd.DataFrame:
        if self.df.empty or "is_transfer" not in self.df.columns:
            return self.df.iloc[0:0]
        return self.df[self.df["is_transfer"]]

    def account(self, key: str) -> Optional[Account]:
        return next((a for a in self.accounts if a.account_key == key), None)

    @property
    def available_balance(self) -> Optional[float]:
        """Total across deposit accounts, or None when no balance is known at all."""
        balances = [a.balance for a in self.accounts if not a.is_card and a.balance is not None]
        return round(sum(balances), 2) if balances else None


def _signature(payload: Dict[str, Any]) -> str:
    """
    A short, stable digest of a dict, for use in a cache key.

    Sorted, so two dicts with the same contents in different insertion order produce
    one key rather than two - otherwise the cache misses on every other request for no
    reason.
    """
    material = "|".join(f"{k}={payload[k]}" for k in sorted(payload))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def load_context(session_id: str, user_id: str) -> BudgetContext:
    """
    Resolve a session (or "overall") into a fully enriched context.

    Raises 404/503 from get_budget_session when the id is not the caller's - this
    function deliberately has no ownership logic of its own, so there is exactly one
    place where that decision is made.
    """
    if session_id == "overall":
        df, meta = get_all_budget_sessions(user_id)
    else:
        df, meta = get_budget_session(session_id)

    if df is None or df.empty:
        return BudgetContext(df=pd.DataFrame(), accounts=[], transfers=[], meta=meta or {})

    df = attach_account_keys(df)

    aliases = load_aliases(user_id)
    if "description" in df.columns:
        df["merchant"] = df["description"].map(lambda d: apply_aliases(d, aliases))

    flags = load_flags(user_id)
    flag_signature = _signature(flags) if flags else "none"

    pairs = derived.transfers(df, flag_signature, lambda: detect_transfers(df))
    df, pairs = mark_transfers(df, pairs, flags)

    account_meta = load_account_meta(user_id)
    meta_signature = _signature({k: str(v) for k, v in account_meta.items()}) if account_meta else "none"
    accounts = derived.account_summary(
        df, meta_signature, lambda: summarise_accounts(df, account_meta)
    )

    return BudgetContext(
        df=df, accounts=accounts, transfers=pairs, meta=meta or {},
        flag_signature=flag_signature, meta_signature=meta_signature,
    )


def filter_signature(**filters: Any) -> str:
    """Stable digest of a filter set, for the overview cache key."""
    return _signature({k: v for k, v in filters.items() if v is not None})
