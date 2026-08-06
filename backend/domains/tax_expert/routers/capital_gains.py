"""
routers/capital_gains.py

Tax Expert - Capital Gains
==========================
Per-transaction capital gains breakdown and manual cost-basis correction.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domains.tax_expert.computation_cache import get_computation
from domains.tax_expert.tax_sessions import get_tax_session, update_ais_data

router = APIRouter()


@router.get("/{session_id}/tax/capital-gains")
def get_capital_gains(session_id: str, regime: str = "new"):
    """Get detailed capital gains breakdown with per-transaction data.

    The `summary` block comes straight from the tax engine rather than being
    recomputed here. This endpoint previously reimplemented the aggregation with
    plain `sum(t["gain"])` passes, which silently omitted:

      - Section 112A grandfathering (FMV as on 31-Jan-2018)
      - the Section 50AA specified-fund exclusion from 12.5% LTCG treatment
      - brought-forward STCL/LTCL offsets
      - manual `capital_gains` overrides

    so /tax/capital-gains and /tax/summary reported *different* ltcg_equity for
    the same session. Projecting from the single engine result fixes that
    divergence and removes the duplicate arithmetic.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    ais = session["ais_data"]

    cg_equity = ais.get("capital_gains_equity", [])
    cg_mf_equity = ais.get("capital_gains_mf_equity", [])
    cg_mf_other = ais.get("capital_gains_mf_other", [])

    cg_real_estate = ais.get("cg_real_estate", [])
    cg_unlisted = ais.get("cg_unlisted", [])
    cg_bonds_gold = ais.get("cg_bonds_gold", [])

    # Memoized — normally a cache hit, since the dashboard also requests
    # /tax/summary for this session and regime.
    computed = get_computation(session_id, session, regime)

    return {
        "summary": dict(computed["income_heads"]["capital_gains"]),
        "equity_shares": cg_equity,
        "equity_mf": cg_mf_equity,
        "other_mf": cg_mf_other,
        "real_estate": cg_real_estate,
        "unlisted": cg_unlisted,
        "bonds_gold": cg_bonds_gold,
        "equity_shares_count": len(cg_equity),
        "equity_mf_count": len(cg_mf_equity),
        "other_mf_count": len(cg_mf_other),
        "real_estate_count": len(cg_real_estate),
        "unlisted_count": len(cg_unlisted),
        "bonds_gold_count": len(cg_bonds_gold),
        "bf_losses": session.get("overrides", {}).get("bf_losses", {}),
    }


class TransactionCostUpdate(BaseModel):
    category: str
    sr: int
    new_cost: float


@router.post("/{session_id}/tax/capital-gains/transaction")
def update_transaction_cost(session_id: str, body: TransactionCostUpdate):
    """Manually update the cost of a specific capital gains transaction."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")  # pragma: no cover — defensive / hard to exercise in unit tests

    ais_data = session["ais_data"]
    category = body.category

    if category not in ais_data:
        raise HTTPException(status_code=400, detail=f"Category {category} not found in AIS data")  # pragma: no cover — defensive / hard to exercise in unit tests

    # Find transaction by sr
    transaction_list = ais_data[category]
    tx_index = next((i for i, tx in enumerate(transaction_list) if tx.get("sr") == body.sr), None)

    if tx_index is None:
        raise HTTPException(status_code=404, detail=f"Transaction with sr {body.sr} not found")  # pragma: no cover — defensive / hard to exercise in unit tests

    tx = transaction_list[tx_index]
    tx["cost"] = body.new_cost
    tx["gain"] = tx["consideration"] - body.new_cost
    tx["patched"] = True
    tx["needs_review"] = False

    # Save back to session
    update_ais_data(session_id, ais_data)

    return {"status": "success", "transaction": tx}
