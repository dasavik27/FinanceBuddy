"""
domains/budget/planning.py - envelope budgets and cash position.

Envelopes
---------
A monthly cap per category, with a *pace* indicator rather than only a total. Knowing
you have spent 60% of your dining budget is not useful on its own; knowing you have
spent 60% of it on the 10th is. Pace is what turns a budget from a report into a
warning.

Cash position
-------------
Deliberately budget-only: bank balances and card debt, nothing else.

This module used to compute a cross-domain net worth by reading the mutual-funds and
equity sessions out of the shared registry and summing a "Market Value" column out of
their payloads. That coupling ran the wrong way - it made the budget domain
undeployable without two other domains present, and pinned it to their payload
schemas, so an equity column rename silently zeroed a user's net worth. Investments
are reported by the domains that own them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from shared import db



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


# net_worth() lived here. It has been removed rather than trimmed: the bank-only half
# of it duplicated the `totals` block that GET /budget/accounts already returns, so
# keeping a cash-only version would have been a second way to compute the same two
# numbers.
