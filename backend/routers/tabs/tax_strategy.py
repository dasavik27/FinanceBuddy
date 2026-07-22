"""
routers/tabs/tax_strategy.py

Tax Expert API Router
=====================
REST gateway for the AIS-powered Tax Expert module.
Handles AIS PDF upload/parsing, tax computation (Old/New regime),
income breakdown, capital gains detail, deduction management, and regime comparison.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, Header
from pydantic import BaseModel
from typing import Optional

from core.ais_parser import parse_ais_pdf
from core.itr_parser import parse_itr_pdf
from core.tax_engine import compute_tax, LTCG_EQUITY_EXEMPTION
from core.broker_parser import parse_zerodha_tax_pnl
from core.reconciliation import reconcile_trades
from core.tax_sessions import (
    create_tax_session, get_tax_session, update_deductions, update_overrides, get_sessions_by_pan, update_ais_data, update_itr_data, get_itr_data
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tax Expert"])


# ── AIS Upload & Session Creation ─────────────────────────────────────────

@router.post("/parse-ais")
async def parse_ais(
    file: UploadFile = File(...),
    broker_file: Optional[UploadFile] = File(None),
    x_user_pan: str = Header(None),
):
    """Parse an AIS PDF and create a tax computation session."""
    raw = await file.read()
    
    try:
        ais_data = parse_ais_pdf(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse AIS PDF: {str(e)}")
    
    # Validate that we got meaningful data
    salary = ais_data.get("salary", {})
    has_income = (
        salary.get("gross", 0) > 0 or 
        bool(ais_data.get("dividends")) or 
        bool(ais_data.get("capital_gains_equity")) or
        bool(ais_data.get("interest_deposits")) or
        bool(ais_data.get("interest_savings")) or
        bool(ais_data.get("capital_gains_mf_other"))
    )
    if not has_income:
        raise HTTPException(status_code=422, detail="Could not extract financial data from this PDF. Please upload a valid AIS document.")
    
    reconciliation_flags = {}
    if broker_file:
        broker_raw = await broker_file.read()
        try:
            broker_trades = parse_zerodha_tax_pnl(broker_raw)
            reconciliation_flags = reconcile_trades(ais_data, broker_trades)
        except Exception as e:
            # We don't fail the whole parsing if broker file fails
            print(f"Failed to parse broker file: {e}")
            pass

    session_id = create_tax_session(ais_data, pan_id=x_user_pan, flags=reconciliation_flags)
    
    # Compute initial tax (New Regime by default)
    tax_result = compute_tax(ais_data, regime="new")
    
    return {
        "session_id": session_id,
        "personal": ais_data.get("personal", {}),
        "fy": ais_data.get("fy", "2025-26"),
        "gross_salary": salary.get("gross", 0),
        "itr_type": tax_result.get("itr_type", "ITR-1"),
        "total_tax": tax_result.get("total_tax", 0),
        "refund_or_due": tax_result.get("refund_or_due", 0),
        "reconciliation_flags": reconciliation_flags,
    }


@router.post("/{session_id}/tax/reconcile-broker")
async def reconcile_broker(
    session_id: str,
    broker_file: UploadFile = File(...)
):
    """Parse a broker file, reconcile against AIS, auto-correct missing costs, and update the session."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")
        
    broker_raw = await broker_file.read()
    try:
        broker_trades = parse_zerodha_tax_pnl(broker_raw)
        logger.info(f"Parsed {len(broker_trades)} trades from broker file.")
    except Exception as e:
        logger.error(f"Failed to parse broker file: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse broker file: {str(e)}")
        
    ais_data = session["ais_data"]
    reconciliation_flags = reconcile_trades(ais_data, broker_trades)
    logger.debug(f"Reconciliation flags: {reconciliation_flags}")
    
    zero_cost_flags = {f"{f['security']}___{f.get('type', 'UNKNOWN')}": f["broker_cost"] for f in reconciliation_flags.get("zero_cost", [])}
    mismatch_flags = {f"{f['security']}___{f.get('type', 'UNKNOWN')}": f["broker_cost"] for f in reconciliation_flags.get("cost_mismatch", [])}
    
    corrected_count = 0
    cat_keys = ["capital_gains_equity", "capital_gains_mf_equity", "capital_gains_mf_other", "cg_bonds_gold", "cg_unlisted", "cg_real_estate"]
    
    from collections import defaultdict
    flag_key_sales = defaultdict(float)
    if zero_cost_flags or mismatch_flags:
        for cat in cat_keys:
            for t in ais_data.get(cat, []):
                sec = str(t.get("security", t.get("amc", "") + " " + t.get("fund", ""))).strip()
                t_type = t.get("type", "UNKNOWN")
                flag_key = f"{sec}___{t_type}"
                if float(t.get("cost", 0)) == 0 and float(t.get("consideration", 0)) > 0:
                    flag_key_sales[flag_key] += float(t.get("consideration", 0))
                elif float(t.get("cost", 0)) > 0:
                    flag_key_sales[flag_key + "_mismatch"] += float(t.get("consideration", 0))
                    
        for cat in cat_keys:
            trades = ais_data.get(cat, [])
            for t in trades:
                sec = t.get("security", "")
                if not sec:
                    amc = t.get("amc", "")
                    fund = t.get("fund", "")
                    sec = f"{amc} {fund}".strip()
                
                sec = str(sec).strip()
                cost = float(t.get("cost", 0))
                sale = float(t.get("consideration", 0))
                
                t_type = t.get("type", "UNKNOWN")
                flag_key = f"{sec}___{t_type}"
                
                # Auto-correct Zero Cost
                if cost == 0 and sale > 0 and flag_key in zero_cost_flags:
                    total_sale = flag_key_sales.get(flag_key, sale)
                    proportion = sale / total_sale if total_sale > 0 else 1
                    t["cost"] = round(float(zero_cost_flags[flag_key]) * proportion, 2)
                    t["gain"] = sale - t["cost"]
                    t["needs_review"] = False
                    t["patched"] = True
                    corrected_count += 1
                # Auto-correct Cost Mismatch (> 20% diff)
                elif cost > 0 and flag_key in mismatch_flags:
                    total_sale = flag_key_sales.get(flag_key + "_mismatch", sale)
                    proportion = sale / total_sale if total_sale > 0 else 1
                    t["cost"] = round(float(mismatch_flags[flag_key]) * proportion, 2)
                    t["gain"] = sale - t["cost"]
                    t["needs_review"] = False
                    t["patched"] = True
                    corrected_count += 1
                        
        reconciliation_flags["zero_cost"] = []
        reconciliation_flags["cost_mismatch"] = []
        
    # Duplicate Detection
    duplicates_removed_count = 0
    from collections import defaultdict
    import difflib
    from core.reconciliation import _normalize
    
    ais_trades_by_sec = defaultdict(list)
    for cat in cat_keys:
        for t in ais_data.get(cat, []):
            sec = str(t.get("security", t.get("amc", "") + " " + t.get("fund", ""))).strip()
            if sec: ais_trades_by_sec[sec].append((cat, t))
            
    # Broker dictionary by security
    broker_cons_by_sec = {}
    for bt in broker_trades:
        n_sec = _normalize(bt.get("security", ""))
        if n_sec:
            broker_cons_by_sec[n_sec] = broker_cons_by_sec.get(n_sec, 0) + float(bt.get("consideration", 0))
        
    for sec, trades in ais_trades_by_sec.items():
        if len(trades) < 2: continue
        
        trade_sigs = defaultdict(list)
        for cat, t in trades:
            sig = f"{t.get('date', '')}_{t.get('consideration', 0)}_{t.get('cost', 0)}"
            trade_sigs[sig].append((cat, t))
            
        for sig, matching_trades in trade_sigs.items():
            if len(matching_trades) >= 2:
                ais_total_cons = sum(float(x[1].get("consideration", 0)) for x in trades)
                n_sec = _normalize(sec)
                
                best_b_cons = 0
                best_score = 0
                for b_sec, b_cons in broker_cons_by_sec.items():
                    score = difflib.SequenceMatcher(None, n_sec, b_sec).ratio()
                    is_sale_exact = abs(ais_total_cons - b_cons) <= max(10, ais_total_cons * 0.005)
                    is_match = score > 0.5 or (b_sec in n_sec) or (n_sec in b_sec) or (is_sale_exact and score > 0.15)
                    if is_match and score > best_score:
                        best_score = score
                        best_b_cons = b_cons
                        
                if best_b_cons > 0 and ais_total_cons > (best_b_cons * 1.5):
                    # Remove the duplicate
                    cat, duplicate_trade = matching_trades.pop()
                    if duplicate_trade in ais_data[cat]:
                        ais_data[cat].remove(duplicate_trade)
                        duplicates_removed_count += 1
                        
    reconciliation_flags["duplicates_removed"] = duplicates_removed_count
        
    session["ais_data"] = ais_data
    session["reconciliation_flags"] = reconciliation_flags
    
    return {"status": "success", "corrected": corrected_count, "duplicates_removed": duplicates_removed_count}


@router.post("/{session_id}/tax/form16")
async def parse_form16(
    session_id: str,
    form16_file: UploadFile = File(...)
):
    """Parse a Form 16 PDF and auto-fill deductions."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")
        
    raw = await form16_file.read()
    try:
        from core.form16_parser import parse_form16_pdf
        extracted_deductions = parse_form16_pdf(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse Form 16: {str(e)}")
        
    # Merge into existing overrides
    overrides = session.get("overrides", {})
    existing_deductions = overrides.get("deductions", {})
    
    # Overwrite existing with the extracted ones (as Form 16 is the source of truth)
    for k, v in extracted_deductions.items():
        existing_deductions[k] = v
        
    overrides["deductions"] = existing_deductions
    update_overrides(session_id, overrides)
    
    return {"status": "success", "flags": reconciliation_flags}


# ── ITR Upload & Comparison ───────────────────────────────────────────────

@router.post("/{session_id}/tax/itr")
async def upload_itr(session_id: str, file: UploadFile = File(...)):
    """Upload a filed ITR PDF and extract summary figures for comparison."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")
        
    raw = await file.read()
    try:
        itr_data = parse_itr_pdf(raw)
        update_itr_data(session_id, itr_data)
        return {"status": "success", "itr_data": itr_data}
    except Exception as e:
        logger.error(f"Failed to parse ITR PDF: {e}")
        raise HTTPException(status_code=422, detail=f"Failed to parse ITR document: {str(e)}")

@router.get("/{session_id}/tax/itr")
async def get_itr(session_id: str):
    """Retrieve previously uploaded ITR summary for comparison."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")
        
    itr_data = get_itr_data(session_id)
    if not itr_data:
        raise HTTPException(status_code=404, detail="No ITR data uploaded for this session")
        
    return {"status": "success", "itr_data": itr_data}


# ── Computations & Summaries ───────────────────────────────────────────────────────────

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


# ── Income Breakdown ──────────────────────────────────────────────────────

@router.get("/{session_id}/tax/income")
def get_tax_income(session_id: str):
    """Get detailed income breakdown from AIS data."""
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")
    
    ais = session["ais_data"]
    salary = ais.get("salary", {})
    
    return {
        "personal": ais.get("personal", {}),
        "salary": {
            "gross": salary.get("gross", 0),
            "employer": salary.get("employer", ""),
            "tds_deducted": salary.get("tds_deducted", 0),
            "quarterly": salary.get("quarterly", []),
        },
        "dividends": ais.get("dividends", []),
        "interest_savings": ais.get("interest_savings", []),
        "interest_deposits": ais.get("interest_deposits", []),
        "interest_others": ais.get("interest_others", []),
        "misc_income": ais.get("misc_income", []),
        "total_dividends": sum(d.get("amount", 0) for d in ais.get("dividends", [])),
        "total_savings_interest": sum(i.get("amount", 0) for i in ais.get("interest_savings", [])),
        "total_fd_interest": sum(i.get("amount", 0) for i in ais.get("interest_deposits", [])),
        "total_other_interest": sum(i.get("amount", 0) for i in ais.get("interest_others", [])),
        "total_misc_income": sum(i.get("amount", 0) for i in ais.get("misc_income", [])),
    }


# ── Capital Gains Detail ─────────────────────────────────────────────────

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


# ── Manual Overrides ──────────────────────────────────────────────────────

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


# ── Regime Comparison ─────────────────────────────────────────────────────

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


# ── Tax History ───────────────────────────────────────────────────────────

@router.get("/tax-history")
def get_tax_history(x_user_pan: str = Header(None)):
    """Get all tax sessions for the current user."""
    if not x_user_pan:
        return {"sessions": []}
    return {"sessions": get_sessions_by_pan(x_user_pan)}
