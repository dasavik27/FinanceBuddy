"""
routers/session.py

Tax Expert - Session Management
================================
AIS PDF upload/session creation, broker reconciliation, and per-user session history.
"""

from collections import defaultdict
from typing import Optional
import difflib
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, Header

from domains.tax_expert.ais_parser import parse_ais_pdf
from domains.tax_expert.ais_schemas import AISStructureChangedError, AISUnknownCodeError
from domains.tax_expert.computation_cache import get_computation
from domains.tax_expert.broker_parser import parse_zerodha_tax_pnl
from domains.tax_expert.reconciliation import reconcile_trades, _normalize
from domains.tax_expert.tax_sessions import create_tax_session, get_tax_session, get_sessions_by_pan, update_ais_data

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/parse-ais")
def parse_ais(
    file: UploadFile = File(...),
    broker_file: Optional[UploadFile] = File(None),
    x_user_pan: str = Header(None),
):
    """Parse an AIS PDF and create a tax computation session.

    Deliberately a sync `def`, not `async def`: every call below (camelot table
    extraction, broker parsing, reconciliation, the SQLite write) is blocking
    CPU-bound work taking seconds. Under `async def` it ran directly on the
    event loop and froze the entire single-worker API — including /health, which
    could fail Render's health check mid-upload. As a sync def, FastAPI runs it
    in a threadpool and the loop stays responsive.
    """
    raw = file.file.read()

    try:
        ais_data = parse_ais_pdf(raw)
    except AISUnknownCodeError as e:
        logger.error(f"AIS Unknown Code: {e.code}")
        raise HTTPException(status_code=422, detail={"type": "AIS_UNKNOWN_CODE", "message": str(e), "code": e.code})
    except AISStructureChangedError as e:
        # Persist the schema diff to a temp file (cross-platform) to aid debugging.
        import json, tempfile, os
        try:
            diff_path = os.path.join(tempfile.gettempdir(), "ais_diff.json")
            with open(diff_path, "w") as f:
                json.dump(e.diff, f)
        except Exception:
            pass
        logger.error(f"AIS Structure Changed: {e.diff}")
        raise HTTPException(status_code=422, detail={"type": "AIS_STRUCTURE_CHANGED", "message": str(e), "diff": e.diff})
    except Exception as e:
        logger.error(f"Error in parse_ais_pdf: {e}", exc_info=True)
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
        logger.warning(f"No income extracted from AIS PDF. Personal details: {ais_data.get('personal', {})}")
        raise HTTPException(status_code=422, detail="Could not extract financial data from this PDF. Please verify that the PDF is a valid AIS document and not password-protected.")

    reconciliation_flags = {}
    if broker_file:
        broker_raw = broker_file.file.read()
        try:
            broker_trades = parse_zerodha_tax_pnl(broker_raw)
            reconciliation_flags = reconcile_trades(ais_data, broker_trades)
        except Exception as e:
            # We don't fail the whole parsing if broker file fails
            logger.info(f"Failed to parse broker file: {e}")
            pass

    session_id = create_tax_session(ais_data, pan_id=x_user_pan, flags=reconciliation_flags)

    # Compute initial tax (New Regime by default). Routed through the cache so the
    # dashboard's immediate follow-up GET /tax/summary?regime=new is a hit rather
    # than a second full engine run.
    tax_result = get_computation(session_id, get_tax_session(session_id), "new")

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
def reconcile_broker(
    session_id: str,
    broker_file: UploadFile = File(...)
):
    """Parse a broker file, reconcile against AIS, auto-correct missing costs, and update the session.

    Sync `def` on purpose — see parse_ais above. Excel parsing plus the
    O(A x B) difflib reconciliation are blocking and must not run on the loop.
    """
    session = get_tax_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Tax session not found")

    broker_raw = broker_file.file.read()
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

    flag_key_sales = defaultdict(float)
    flag_key_declared_cost = defaultdict(float)
    if zero_cost_flags or mismatch_flags:
        for cat in cat_keys:
            for t in ais_data.get(cat, []):
                sec = str(t.get("security", t.get("amc", "") + " " + t.get("fund", ""))).strip()
                t_type = t.get("type", "UNKNOWN")
                flag_key = f"{sec}___{t_type}"
                t_cost = float(t.get("cost", 0))
                if t_cost == 0 and float(t.get("consideration", 0)) > 0:
                    flag_key_sales[flag_key] += float(t.get("consideration", 0))
                elif t_cost > 0:
                    flag_key_sales[flag_key + "_mismatch"] += float(t.get("consideration", 0))
                    flag_key_declared_cost[flag_key] += t_cost

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

                    broker_cost = float(zero_cost_flags[flag_key])
                    declared_cost = flag_key_declared_cost.get(flag_key, 0.0)
                    remaining_cost = max(0.0, broker_cost - declared_cost)

                    t["cost"] = round(remaining_cost * proportion, 2)
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

        # The broker best-match below depends only on the security name and the
        # security's total AIS consideration — both constant across signature
        # groups — yet it used to be recomputed inside the signature loop, running
        # a difflib.SequenceMatcher pass over every broker security per group.
        # Computed at most once per security now, and lazily, so securities with no
        # duplicate signatures pay nothing.
        _match_cache = {}

        def _broker_match():
            if "v" not in _match_cache:
                ais_total = sum(float(x[1].get("consideration", 0)) for x in trades)
                n_sec = _normalize(sec)
                best_cons, best_score = 0, 0
                for b_sec, b_cons in broker_cons_by_sec.items():
                    score = difflib.SequenceMatcher(None, n_sec, b_sec).ratio()
                    is_sale_exact = abs(ais_total - b_cons) <= max(10, ais_total * 0.005)
                    is_match = score > 0.5 or (b_sec in n_sec) or (n_sec in b_sec) or (is_sale_exact and score > 0.15)
                    if is_match and score > best_score:
                        best_score = score
                        best_cons = b_cons
                _match_cache["v"] = (ais_total, best_cons)
            return _match_cache["v"]

        for sig, matching_trades in trade_sigs.items():
            if len(matching_trades) >= 2:
                ais_total_cons, best_b_cons = _broker_match()

                if best_b_cons > 0 and ais_total_cons > (best_b_cons * 1.5):
                    # Remove the duplicate
                    cat, duplicate_trade = matching_trades.pop()
                    if duplicate_trade in ais_data[cat]:
                        ais_data[cat].remove(duplicate_trade)
                        duplicates_removed_count += 1

    reconciliation_flags["duplicates_removed"] = duplicates_removed_count

    session["ais_data"] = ais_data
    session["reconciliation_flags"] = reconciliation_flags
    # Persist the patched cost basis + flags so auto-corrections survive a backend restart.
    update_ais_data(session_id, ais_data)

    return {"status": "success", "corrected": corrected_count, "duplicates_removed": duplicates_removed_count}


@router.get("/tax-history")
def get_tax_history(x_user_pan: str = Header(None)):
    """Get all tax sessions for the current user."""
    if not x_user_pan:
        return {"sessions": []}
    return {"sessions": get_sessions_by_pan(x_user_pan)}
