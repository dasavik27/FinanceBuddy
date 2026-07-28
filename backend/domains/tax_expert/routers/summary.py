"""
routers/summary.py

Tax Expert - Computation & Regime Compare
==========================================
Full tax computation summary, manual deduction/override recalculation, and
side-by-side Old vs New regime comparison.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domains.tax_expert.tax_engine import compute_tax
from domains.tax_expert.tax_sessions import get_tax_session, update_overrides

router = APIRouter()


@router.get("/{session_id}/tax/summary")
def get_tax_summary(session_id: str, regime: str = "new"):
    """Get complete tax computation summary for the given regime."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    result = compute_tax(
        session["ais_data"],
        regime=regime,
        overrides=session.get("overrides", {})
    )
    result["overrides"] = session.get("overrides", {})
    result["reconciliation_flags"] = session.get("reconciliation_flags", {})
    return result


class RecalculateInput(BaseModel):
    deductions: Optional[dict] = None
    bf_losses: Optional[dict] = None
    schedule_al: Optional[dict] = None
    manual_taxes: Optional[float] = None
    manual_tds: Optional[float] = None
    disclosures: Optional[dict] = None
    foreign_interest: Optional[float] = None
    business_income: Optional[dict] = None
    crypto_income: Optional[float] = None
    gaming_income: Optional[float] = None
    capital_gains: Optional[dict] = None


@router.post("/{session_id}/tax/recalculate")
def recalculate_tax(session_id: str, body: RecalculateInput):
    """Save manual user overrides and return updated computation."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    overrides = {}
    if body.deductions is not None:
        overrides["deductions"] = body.deductions
    if body.bf_losses is not None:
        overrides["bf_losses"] = body.bf_losses
    if body.schedule_al is not None:
        overrides["schedule_al"] = body.schedule_al
    if body.manual_taxes is not None:
        overrides["manual_taxes"] = body.manual_taxes
    if body.manual_tds is not None:
        overrides["manual_tds"] = body.manual_tds
    if body.disclosures is not None:
        overrides["disclosures"] = body.disclosures
    if body.foreign_interest is not None:
        overrides["foreign_interest"] = body.foreign_interest
    if body.business_income is not None:
        overrides["business_income"] = body.business_income
    if body.crypto_income is not None:
        overrides["crypto_income"] = body.crypto_income
    if body.gaming_income is not None:
        overrides["gaming_income"] = body.gaming_income
    if body.capital_gains is not None:
        overrides["capital_gains"] = body.capital_gains

    update_overrides(session_id, overrides)

    # Return updated session state summary
    result = compute_tax(session["ais_data"], regime="new", overrides=session.get("overrides", {}))
    result["overrides"] = session.get("overrides", {})
    return result


@router.get("/{session_id}/tax/compare-regimes")
def compare_regimes(session_id: str):
    """Side-by-side comparison of Old vs New regime tax computation."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    new_result = compute_tax(session["ais_data"], regime="new", overrides=session.get("overrides", {}))
    old_result = compute_tax(
        session["ais_data"],
        regime="old",
        overrides=session.get("overrides", {})
    )

    new_tax = new_result.get("total_tax", 0)
    old_tax = old_result.get("total_tax", 0)

    return {
        "new_regime": {
            "total_tax": new_tax,
            "taxable_income": new_result.get("taxable_normal_income", 0),
            "refund_or_due": new_result.get("refund_or_due", 0),
            "std_deduction": new_result["income_heads"]["salary"]["std_deduction"],
        },
        "old_regime": {
            "total_tax": old_tax,
            "taxable_income": old_result.get("taxable_normal_income", 0),
            "refund_or_due": old_result.get("refund_or_due", 0),
            "std_deduction": old_result["income_heads"]["salary"]["std_deduction"],
            "total_deductions": old_result.get("total_deductions", 0),
        },
        "recommended": "new" if new_tax <= old_tax else "old",
        "savings": abs(new_tax - old_tax),
    }
