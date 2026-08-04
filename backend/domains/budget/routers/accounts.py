"""
Budget accounts: the per-account view, and the metadata only the user can supply.

Accounts are derived from uploads, not registered - see domains/budget/accounts.py -
so there is no POST here. What a statement cannot tell us (credit limit, statement and
due day, opening balance, a friendly label) is what PUT writes.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Response
from pydantic import BaseModel, Field

from shared import identity
from shared.services.cache import get_cache_headers
from domains.budget.accounts import UTILISATION_WARNING, upsert_account_meta
from domains.budget.pipeline import load_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_caller() -> str:
    user_id = identity.current_user_id()
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to use the budget analyzer.")
    return user_id


class AccountMetaUpdate(BaseModel):
    """
    Editable account metadata. Every field optional: this is a PATCH in spirit, and a
    UI that sends only the field it changed must not blank the others.
    """

    label: Optional[str] = Field(None, max_length=64)
    last4: Optional[str] = Field(None, max_length=4)
    credit_limit: Optional[float] = Field(None, ge=0)
    statement_day: Optional[int] = Field(None, ge=1, le=31)
    due_day: Optional[int] = Field(None, ge=1, le=31)
    opening_balance: Optional[float] = None


@router.get("")
def list_accounts(response: Response, session_id: str = "overall"):
    """
    Every account seen across the user's statements, with balances and card utilisation.

    Cards come first (see the sort in accounts.summarise_accounts) because a card
    outstanding is the thing most likely to need action.
    """
    for header, value in get_cache_headers("tax_calculations").items():
        response.headers[header] = value

    ctx = load_context(session_id, _require_caller())
    accounts = [a.as_dict() for a in ctx.accounts]

    cards = [a for a in accounts if a["is_card"]]
    deposits = [a for a in accounts if not a["is_card"]]

    return {
        "accounts": accounts,
        "totals": {
            "deposit_balance": round(
                sum(a["balance"] for a in deposits if a["balance"] is not None), 2),
            "card_outstanding": round(
                sum(max(0.0, a["outstanding"] or 0.0) for a in cards), 2),
            "account_count": len(accounts),
            "card_count": len(cards),
        },
        # Surfaced separately so the UI does not have to know the threshold. Utilisation
        # above ~30% is the largest negative input to an Indian credit score.
        "utilisation_warnings": [
            {
                "account_key": a["account_key"],
                "label": a["label"],
                "utilisation": a["utilisation"],
                "status": a["utilisation_status"],
            }
            for a in cards
            if a["utilisation"] is not None and a["utilisation"] >= UTILISATION_WARNING
        ],
        # A card with no limit set cannot have utilisation computed at all, and the UI
        # should prompt for it rather than showing a blank tile.
        "cards_missing_limit": [
            a["account_key"] for a in cards if not a["credit_limit"]
        ],
    }


@router.put("/{account_key}")
def update_account(account_key: str, payload: AccountMetaUpdate = Body(...)):
    """Write the fields a statement cannot supply."""
    user_id = _require_caller()

    values = payload.model_dump(exclude_unset=True, exclude_none=False)
    if not values:
        raise HTTPException(status_code=422, detail="Nothing to update.")

    if payload.last4 is not None and payload.last4 and not payload.last4.isdigit():
        raise HTTPException(status_code=422, detail="last4 must be four digits.")

    upsert_account_meta(user_id, account_key, values)
    return {"status": "ok", "account_key": account_key}
