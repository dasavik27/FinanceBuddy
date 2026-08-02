"""
domains/budget/planning.py - envelope budgets and cross-domain net worth.

Envelopes
---------
A monthly cap per category, with a *pace* indicator rather than only a total. Knowing
you have spent 60% of your dining budget is not useful on its own; knowing you have
spent 60% of it on the 10th is. Pace is what turns a budget from a report into a
warning.

Net worth
---------
The one number this application can produce that a standalone budgeting app cannot.
Bank balances and card debt live here, mutual funds and equities live in their own
domains, and nobody was adding them up. The cross-domain read is deliberately
best-effort: if the equity module raises, net worth still renders with the parts it
could reach and says which parts are missing, because a dashboard that 500s because one
domain is unavailable is worse than one that is honest about a gap.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from shared import db
from domains.budget.accounts import Account, CREDIT_CARD

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Envelope budgets
# ---------------------------------------------------------------------------

def load_envelopes(user_id: Optional[str]) -> Dict[str, float]:
    if not user_id:
        return {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT category, monthly_cap FROM budget_envelopes WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def set_envelope(user_id: str, category: str, monthly_cap: Optional[float]) -> None:
    """Set or clear a category's monthly cap. None clears it."""
    with db.connect() as conn:
        if monthly_cap is None:
            conn.execute(
                "DELETE FROM budget_envelopes WHERE user_id = %s AND category = %s",
                (user_id, category),
            )
        else:
            conn.execute(
                """
                INSERT INTO budget_envelopes (user_id, category, monthly_cap)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category) DO UPDATE
                SET monthly_cap = EXCLUDED.monthly_cap, updated_at = now()
                """,
                (user_id, category, float(monthly_cap)),
            )


def envelope_status(
    df: pd.DataFrame, caps: Dict[str, float], as_of: Optional[pd.Timestamp] = None
) -> List[Dict[str, Any]]:
    """
    Spend against each cap for the current month, with a pace verdict.

    Categories with a cap always appear, even at zero spend - a budget you have not
    touched is information too, and a list that silently omits it looks broken.
    """
    if not caps:
        return []

    spend_by_category: Dict[str, float] = {}
    days_elapsed, days_in_month = 1, 30

    if df is not None and not df.empty:
        work = df.copy()
        if "is_transfer" in work.columns:
            work = work[~work["is_transfer"]]
        work = work[work["type"] == "debit"]
        work["_date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["_date"])

        if not work.empty:
            as_of = as_of or work["_date"].max()
            month_start = as_of.replace(day=1)
            days_in_month = ((month_start + pd.offsets.MonthBegin(1)) - month_start).days
            days_elapsed = max(1, (as_of - month_start).days + 1)
            current = work[work["_date"] >= month_start]
            if not current.empty:
                spend_by_category = (
                    current.groupby(current["category"].fillna("Uncategorized"))["amount"]
                    .sum().to_dict()
                )

    # How far through the month we are. Spending 60% of a budget is fine on the 20th
    # and a problem on the 5th, and this is the only thing that distinguishes them.
    month_progress = days_elapsed / days_in_month

    out: List[Dict[str, Any]] = []
    for category, cap in sorted(caps.items()):
        spent = float(spend_by_category.get(category, 0.0))
        used = (spent / cap) if cap > 0 else 0.0

        if used >= 1.0:
            status = "over"
        elif used > month_progress + 0.15:
            status = "ahead_of_pace"
        elif used > month_progress:
            status = "slightly_ahead"
        else:
            status = "on_track"

        remaining = max(0.0, cap - spent)
        days_left = max(0, days_in_month - days_elapsed)

        out.append({
            "category": category,
            "monthly_cap": round(cap, 2),
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "used_pct": round(used * 100, 1),
            "month_progress_pct": round(month_progress * 100, 1),
            "status": status,
            "daily_allowance": round(remaining / days_left, 2) if days_left else 0.0,
            # Straight-line extrapolation of the current rate. Blunt, but it is the
            # projection a user would do in their head and it is easy to sanity-check.
            "projected_month_end": round(spent / month_progress, 2) if month_progress > 0 else 0.0,
        })

    return out


# ---------------------------------------------------------------------------
# Net worth
# ---------------------------------------------------------------------------

def net_worth(user_id: str, accounts: List[Account]) -> Dict[str, Any]:
    """
    Assets less liabilities, across every domain that holds a position.

    Bank balances and card outstandings come from the budget accounts passed in.
    Mutual funds and equities are read from their own domains, each behind its own
    try/except so one unavailable domain degrades that line rather than the response.
    """
    breakdown: List[Dict[str, Any]] = []
    unavailable: List[str] = []

    cash = 0.0
    card_debt = 0.0
    for account in accounts:
        if account.kind == CREDIT_CARD:
            owed = account.outstanding or 0.0
            if owed > 0:
                card_debt += owed
                breakdown.append({
                    "domain": "budget", "label": account.label or account.account_key,
                    "kind": "liability", "value": round(owed, 2),
                })
        else:
            balance = account.balance
            if balance is not None:
                cash += balance
                breakdown.append({
                    "domain": "budget", "label": account.label or account.account_key,
                    "kind": "asset", "value": round(balance, 2),
                })

    investments = 0.0

    mf_value = _mutual_fund_value(user_id)
    if mf_value is None:
        unavailable.append("mutual_funds")
    elif mf_value > 0:
        investments += mf_value
        breakdown.append({"domain": "mutual_funds", "label": "Mutual funds",
                          "kind": "asset", "value": round(mf_value, 2)})

    equity_value = _equity_value(user_id)
    if equity_value is None:
        unavailable.append("equity")
    elif equity_value > 0:
        investments += equity_value
        breakdown.append({"domain": "equity", "label": "Stocks",
                          "kind": "asset", "value": round(equity_value, 2)})

    assets = cash + investments
    return {
        "assets": round(assets, 2),
        "liabilities": round(card_debt, 2),
        "net_worth": round(assets - card_debt, 2),
        "cash": round(cash, 2),
        "investments": round(investments, 2),
        "card_debt": round(card_debt, 2),
        "breakdown": sorted(breakdown, key=lambda b: -abs(b["value"])),
        # Named explicitly so the UI can say "excluding mutual funds - could not load"
        # instead of quietly under-reporting the user's net worth.
        "unavailable_domains": unavailable,
    }


def _latest_session_id(user_id: str, upload_type: str) -> Optional[str]:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE user_id = %s AND upload_type = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, upload_type),
        ).fetchone()
    return str(row[0]) if row else None


def _mutual_fund_value(user_id: str) -> Optional[float]:
    """Current MF value, or None if the domain could not be read."""
    try:
        session_id = _latest_session_id(user_id, "mutual_funds")
        if not session_id:
            return 0.0
        from shared import storage

        loaded = storage.load_session(session_id)
        if not loaded:
            return 0.0
        df_h = loaded[0]
        if df_h is None or df_h.empty:
            return 0.0
        for column in ("Market Value", "market_value", "current_value"):
            if column in df_h.columns:
                return float(pd.to_numeric(df_h[column], errors="coerce").fillna(0).sum())
        return 0.0
    except Exception as e:
        logger.warning("[budget.networth] mutual fund value unavailable: %s", e)
        return None


def _equity_value(user_id: str) -> Optional[float]:
    """Current equity value, or None if the domain could not be read."""
    try:
        session_id = _latest_session_id(user_id, "equity")
        if not session_id:
            return 0.0
        from shared import storage

        loaded = storage.load_session(session_id)
        if not loaded:
            return 0.0
        df_h = loaded[0]
        if df_h is None or df_h.empty:
            return 0.0
        for column in ("Market Value", "current_value", "market_value"):
            if column in df_h.columns:
                return float(pd.to_numeric(df_h[column], errors="coerce").fillna(0).sum())
        return 0.0
    except Exception as e:
        logger.warning("[budget.networth] equity value unavailable: %s", e)
        return None
