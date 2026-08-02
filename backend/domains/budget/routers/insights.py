"""
Budget insights: transfers, recurring charges, forecast, anomalies, reconciliation,
coverage, envelopes and the Sankey flow.

Every handler is thin. The work is in the engine modules and the memoization is in
derived.py, so a route is: authenticate, load the context, call one function, return.
Authorization happens inside pipeline.load_context -> sessions.get_budget_session.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Response
from pydantic import BaseModel

from shared import identity
from shared.services.cache import get_cache_headers
from domains.budget import derived, insights, planning
from domains.budget.merchants import set_alias
from domains.budget.natures import nature_of
from domains.budget.pipeline import load_context
from domains.budget.transfers import set_flag

logger = logging.getLogger(__name__)

router = APIRouter(tags=["budget"])


def _require_caller() -> str:
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to use the budget analyzer.")
    return user_id


def _private(response: Response) -> None:
    """
    Mark a response as user-specific.

    These payloads are derived from one person's bank statements; a shared cache must
    never hold them. shared/services/cache.py treats visibility as a correctness field
    rather than a performance one, and this is why.
    """
    for header, value in get_cache_headers("tax_calculations").items():
        response.headers[header] = value


@router.get("/{session_id}/transfers")
def get_transfers(session_id: str, response: Response):
    """
    Movements between the user's own accounts, netted out of income and expense.

    Returned in full rather than as a total: the pairing is a heuristic, and a number
    the user cannot audit is a number they will not trust.
    """
    _private(response)
    ctx = load_context(session_id, _require_caller())

    pairs = [p.as_dict() for p in ctx.transfers]
    card_payments = [p for p in pairs if p["is_card_payment"]]

    return {
        "pairs": pairs,
        "count": len(pairs),
        "total_amount": round(sum(p["amount"] for p in pairs), 2),
        "card_payment_total": round(sum(p["amount"] for p in card_payments), 2),
        # What the numbers would have been without pairing, so the user can see what
        # the correction is worth.
        "excluded_from_income": round(
            float(ctx.internal[ctx.internal["type"] == "credit"]["amount"].sum())
            if not ctx.internal.empty else 0.0, 2),
        "excluded_from_expense": round(
            float(ctx.internal[ctx.internal["type"] == "debit"]["amount"].sum())
            if not ctx.internal.empty else 0.0, 2),
    }


class TransferFlag(BaseModel):
    txn_id: str
    flag: Optional[str] = None  # "transfer" | "not_transfer" | None to clear


@router.post("/transfers/flag")
def flag_transfer(payload: TransferFlag = Body(...)):
    """Override the pairing heuristic for one transaction."""
    user_id = _require_caller()
    if payload.flag not in (None, "transfer", "not_transfer"):
        raise HTTPException(status_code=422, detail="flag must be 'transfer', 'not_transfer' or null.")
    set_flag(user_id, payload.txn_id, payload.flag)
    return {"status": "ok"}


@router.get("/{session_id}/recurring")
def get_recurring(session_id: str, response: Response):
    """Subscriptions and standing charges, with price changes and annualised cost."""
    _private(response)
    ctx = load_context(session_id, _require_caller())

    found = derived.recurring(ctx.df, lambda: insights.find_recurring(ctx.df))
    items = [r.as_dict() for r in found]
    active = [i for i in items if i["status"] == "active"]

    return {
        "subscriptions": items,
        "active_count": len(active),
        "lapsed_count": len(items) - len(active),
        "monthly_commitment": round(
            sum(i["annualised_cost"] for i in active) / 12.0, 2),
        "annual_commitment": round(sum(i["annualised_cost"] for i in active), 2),
        "price_increases": [
            {"merchant": i["merchant"], **change}
            for i in items for change in i["price_changes"] if change["change_pct"] > 0
        ],
    }


@router.get("/{session_id}/forecast")
def get_forecast(session_id: str, response: Response):
    """Month-end projection and a daily safe-to-spend figure."""
    _private(response)
    ctx = load_context(session_id, _require_caller())

    found = derived.recurring(ctx.df, lambda: insights.find_recurring(ctx.df))
    return insights.build_forecast(ctx.df, found, available_balance=ctx.available_balance)


@router.get("/{session_id}/anomalies")
def get_anomalies(session_id: str, response: Response):
    """Duplicate charges, category spikes and unusually large first-time merchants."""
    _private(response)
    ctx = load_context(session_id, _require_caller())

    found = derived.anomalies(ctx.df, lambda: insights.find_anomalies(ctx.df))
    return {
        "anomalies": found,
        "count": len(found),
        "high_severity_count": sum(1 for a in found if a["severity"] == "high"),
    }


@router.get("/{session_id}/reconciliation")
def get_reconciliation(session_id: str, response: Response):
    """
    Whether each statement's printed balances agree with its own transactions.

    This is the check that tells the user whether to believe the rest of the dashboard.
    """
    _private(response)
    ctx = load_context(session_id, _require_caller())

    results = derived.reconciliation(ctx.df, lambda: insights.reconcile_accounts(ctx.df))
    checked = len(results)
    clean = sum(1 for r in results if r["status"] == "reconciled")

    return {
        "accounts": results,
        "checked": checked,
        "reconciled": clean,
        "status": "reconciled" if checked and clean == checked
                  else "no_balance_data" if not checked else "gaps_found",
        # Accounts whose export carried no running balance cannot be checked at all.
        # Saying so is better than implying everything passed.
        "unverifiable_accounts": [
            a.account_key for a in ctx.accounts
            if a.account_key not in {r["account_key"] for r in results}
        ],
    }


@router.get("/{session_id}/coverage")
def get_coverage(session_id: str, response: Response):
    """
    Which months each account has statements for, and which are missing.

    Without this a user draws confident conclusions from a trend built on a gap - the
    dashboard cannot tell "spent nothing in March" from "never uploaded March".
    """
    _private(response)
    ctx = load_context(session_id, _require_caller())

    out = []
    for account in ctx.accounts:
        months = account.months_covered
        gaps = []
        if len(months) >= 2:
            span = [
                f"{p:%Y-%m}" for p in
                pd.period_range(months[0], months[-1], freq="M").to_timestamp()
            ]
            gaps = [m for m in span if m not in set(months)]
        out.append({
            "account_key": account.account_key,
            "label": account.label or account.account_key,
            "months_covered": months,
            "missing_months": gaps,
            "first_txn": account.first_txn,
            "last_txn": account.last_txn,
            "complete": not gaps,
        })

    return {
        "accounts": out,
        "complete": all(a["complete"] for a in out) if out else True,
        "total_missing_months": sum(len(a["missing_months"]) for a in out),
    }


@router.get("/{session_id}/sankey")
def get_sankey(session_id: str, response: Response):
    """Nodes and links for the income -> nature -> category flow diagram."""
    _private(response)
    ctx = load_context(session_id, _require_caller())
    return derived.sankey(ctx.df, lambda: insights.build_sankey(ctx.df, nature_of))


# GET /{session_id}/net-worth was removed along with planning.net_worth(). It summed
# budget balances with mutual-fund and equity holdings read out of those domains'
# sessions, which is the one place the budget domain depended on another domain
# existing. The bank-side half of it - deposit balance and card outstanding - is
# already served by GET /budget/accounts under `totals`.


# ── Envelope budgets ─────────────────────────────────────────────────────────

class EnvelopeUpdate(BaseModel):
    category: str
    monthly_cap: Optional[float] = None


@router.get("/{session_id}/envelopes")
def get_envelopes(session_id: str, response: Response):
    """Spend against each monthly category cap, with a pace verdict."""
    _private(response)
    user_id = _require_caller()
    ctx = load_context(session_id, user_id)
    caps = planning.load_envelopes(user_id)
    return {"envelopes": planning.envelope_status(ctx.df, caps)}


@router.put("/envelopes")
def put_envelope(payload: EnvelopeUpdate = Body(...)):
    """Set or clear one category's monthly cap."""
    user_id = _require_caller()
    if payload.monthly_cap is not None and payload.monthly_cap < 0:
        raise HTTPException(status_code=422, detail="A monthly cap cannot be negative.")
    planning.set_envelope(user_id, payload.category.strip(), payload.monthly_cap)
    return {"status": "ok"}


# ── Merchant aliases ─────────────────────────────────────────────────────────

class MerchantRename(BaseModel):
    description: str
    display_name: str


@router.put("/merchants/alias")
def rename_merchant(payload: MerchantRename = Body(...)):
    """Remember a merchant rename, so the user only corrects it once."""
    user_id = _require_caller()
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="A display name is required.")
    key = set_alias(user_id, payload.description, name)
    return {"status": "ok", "normalised": key, "display_name": name}
