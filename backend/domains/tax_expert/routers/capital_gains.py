"""
routers/capital_gains.py

Tax Expert - Capital Gains
==========================
Per-transaction capital gains breakdown and manual cost-basis correction.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domains.tax_expert.tax_engine import LTCG_EQUITY_EXEMPTION
from domains.tax_expert.tax_sessions import get_tax_session, update_ais_data

router = APIRouter()


@router.get("/{session_id}/tax/capital-gains")
def get_capital_gains(session_id: str):
    """Get detailed capital gains breakdown with per-transaction data."""
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

    # Compute summaries
    ltcg_equity = sum(t.get("gain", 0) for t in cg_equity if t.get("type") == "LTCG")
    ltcg_equity += sum(t.get("gain", 0) for t in cg_mf_equity if t.get("type") == "LTCG")

    stcg_equity = sum(t.get("gain", 0) for t in cg_equity if t.get("type") == "STCG")
    stcg_equity += sum(t.get("gain", 0) for t in cg_mf_equity if t.get("type") == "STCG")

    other_assets = cg_mf_other + cg_real_estate + cg_unlisted + cg_bonds_gold
    ltcg_other = sum(t.get("gain", 0) for t in other_assets if t.get("type") == "LTCG")
    stcg_other = sum(t.get("gain", 0) for t in other_assets if t.get("type") == "STCG")

    return {
        "summary": {
            "ltcg_equity": round(ltcg_equity, 0),
            "stcg_equity": round(stcg_equity, 0),
            "ltcg_other": round(ltcg_other, 0),
            "stcg_other": round(stcg_other, 0),
            "total": round(ltcg_equity + stcg_equity + ltcg_other + stcg_other, 0),
            "ltcg_equity_exemption": LTCG_EQUITY_EXEMPTION,
            "ltcg_equity_taxable": round(max(0, ltcg_equity - LTCG_EQUITY_EXEMPTION), 0),
        },
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
        raise HTTPException(status_code=404, detail="Tax session not found")

    ais_data = session["ais_data"]
    category = body.category

    if category not in ais_data:
        raise HTTPException(status_code=400, detail=f"Category {category} not found in AIS data")

    # Find transaction by sr
    transaction_list = ais_data[category]
    tx_index = next((i for i, tx in enumerate(transaction_list) if tx.get("sr") == body.sr), None)

    if tx_index is None:
        raise HTTPException(status_code=404, detail=f"Transaction with sr {body.sr} not found")

    tx = transaction_list[tx_index]
    tx["cost"] = body.new_cost
    tx["gain"] = tx["consideration"] - body.new_cost
    tx["patched"] = True
    tx["needs_review"] = False

    # Save back to session
    update_ais_data(session_id, ais_data)

    return {"status": "success", "transaction": tx}
