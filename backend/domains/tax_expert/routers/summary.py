"""
routers/summary.py

Tax Expert - Computation & Regime Compare
==========================================
Full tax computation summary, manual deduction/override recalculation, and
side-by-side Old vs New regime comparison.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from shared import identity

from domains.tax_expert.computation_cache import get_computation, cache_stats
from domains.tax_expert.tax_sessions import get_tax_session, update_overrides

router = APIRouter()

# compute_tax() embeds thirteen detail lists by reference — effectively the whole
# parsed AIS — into its result. Returning them from /tax/summary meant every
# summary response (including one per deduction keystroke via /tax/recalculate)
# serialized the entire AIS again. The object-graph construction, JSON encoding
# and gzip compression are all CPU on the single free-tier worker.
#
# The UI reads none of these from the summary payload; it uses the dedicated
# /tax/income and /tax/capital-gains endpoints instead. They are stripped here
# and remain retrievable via GET /tax/details/{bucket} below.
#
# `refunds` is deliberately NOT stripped — TaxSavingsTab reads it straight off
# the summary response.
_DETAIL_KEYS = (
    "dividends_detail",
    "interest_savings_detail",
    "interest_deposits_detail",
    "interest_others_detail",
    "misc_income_detail",
    "cg_equity_detail",
    "cg_mf_equity_detail",
    "cg_mf_other_detail",
    "cg_real_estate_detail",
    "cg_unlisted_detail",
    "cg_bonds_gold_detail",
    "salary_quarterly",
)


def summary_response(result: dict, session: dict, include_flags: bool = True) -> dict:
    """Shallow-copy the memoized result, drop bulk detail lists, attach session state.

    The shallow copy is essential: `result` is the shared cache entry, so writing
    to it directly would corrupt the cache for every later reader.
    """
    payload = {k: v for k, v in result.items() if k not in _DETAIL_KEYS}
    payload["overrides"] = session.get("overrides", {})
    if include_flags:
        payload["reconciliation_flags"] = session.get("reconciliation_flags", {})
    return payload


@router.get("/{session_id}/tax/summary")
def get_tax_summary(session_id: str, regime: str = "new"):
    """Get complete tax computation summary for the given regime."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    result = get_computation(session_id, session, regime)
    return summary_response(result, session)


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
def recalculate_tax(session_id: str, body: RecalculateInput, regime: str = "new"):
    """Save manual user overrides and return updated computation for the chosen regime."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    # Only forward fields the client actually sent, so a partial edit does not
    # clobber unrelated overrides with None.
    overrides = {k: v for k, v in body.model_dump().items() if v is not None}

    if overrides:
        update_overrides(session_id, overrides)

    # update_overrides() bumped the session version, so this necessarily
    # recomputes rather than returning a stale cache entry.
    result = get_computation(session_id, session, regime)
    return summary_response(result, session, include_flags=False)


@router.get("/{session_id}/tax/compare-regimes")
def compare_regimes(session_id: str):
    """Side-by-side comparison of Old vs New regime tax computation."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    # Both of these are cache hits when /tax/summary has already been requested
    # for the same regime — which is exactly what the dashboard does. This used
    # to be two unconditional full engine runs whose results were ~95% discarded.
    new_result = get_computation(session_id, session, "new")
    old_result = get_computation(session_id, session, "old")

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


# Buckets exposed by /tax/details/{bucket}, mapped to their AIS source key.
_DETAIL_BUCKETS = {
    "dividends": "dividends",
    "interest_savings": "interest_savings",
    "interest_deposits": "interest_deposits",
    "interest_others": "interest_others",
    "misc_income": "misc_income",
    "equity_shares": "capital_gains_equity",
    "equity_mf": "capital_gains_mf_equity",
    "other_mf": "capital_gains_mf_other",
    "real_estate": "cg_real_estate",
    "unlisted": "cg_unlisted",
    "bonds_gold": "cg_bonds_gold",
    "salary_quarterly": None,  # nested under salary
    "refunds": "refunds",
}


@router.get("/{session_id}/tax/details/{bucket}")
def get_detail_rows(
    session_id: str,
    bucket: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    """Paginated access to a single detail list.

    Replaces shipping every list inside /tax/summary. Paginated because these are
    unbounded — an active trader's AIS can carry thousands of rows.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    if bucket not in _DETAIL_BUCKETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown detail bucket '{bucket}'. Valid: {sorted(_DETAIL_BUCKETS)}",
        )

    ais = session.get("ais_data", {})
    if bucket == "salary_quarterly":
        rows = ais.get("salary", {}).get("quarterly", [])
    else:
        rows = ais.get(_DETAIL_BUCKETS[bucket], [])

    return {
        "bucket": bucket,
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "rows": rows[offset:offset + limit],
    }


@router.get("/tax/cache-stats")
def get_cache_stats():
    """
    Computation cache hit/miss counters, for verifying memoization in production.

    Authenticated: the counters carry no user data, but they do reveal how much
    traffic the deployment handles and when.
    """
    if not identity.current_user_id():
        raise HTTPException(status_code=401, detail="Authentication required.")
    return cache_stats()
