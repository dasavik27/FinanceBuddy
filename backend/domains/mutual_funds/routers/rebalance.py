"""
routers/tabs/rebalance.py

Institutional CIO Rebalancing & RMSD Drift Audit Engine
=======================================================
Evaluates portfolio asset class drift against target model portfolios (Conservative, Balanced,
Aggressive) utilizing Root-Mean-Square Deviation (RMSD). Synthesizes actionable rebalancing orders
and intra-equity volatility management switches for institutional advisory parity.

Sell-side orders are tax-lot aware (see tax_lots.select_sell_candidate): they respect ELSS
3-year lock-in and prefer trimming LTCG-eligible (lower-tax) units over STCG-eligible ones.
"""

from fastapi import APIRouter
from domains.mutual_funds.sessions import get_session
from domains.mutual_funds.tax_lots import select_sell_candidate
from shared.config import get_standard_category
import pandas as pd
import numpy as np

router = APIRouter()

RISK_PROFILES = {
    "Conservative": {"Equity": 20, "Debt": 60, "Hybrid": 10, "Other": 10},
    "Balanced":     {"Equity": 50, "Debt": 30, "Hybrid": 10, "Other": 10},
    "Aggressive":   {"Equity": 80, "Debt": 10, "Hybrid": 5,  "Other": 5},
}

REBALANCE_THRESHOLD = 5.0

@router.get("/{session_id}/plan")
def get_rebalance_plan(session_id: str, profile: str = "Balanced"):
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t

    if df_h.empty:
        return {"status": "Empty", "orders": [], "drift_score": 0.0}

    total_value = float(df_h["Market Value"].sum())
    if total_value <= 0:
        return {"status": "Empty", "orders": [], "drift_score": 0.0}

    df_h = df_h.copy()
    from domains.mutual_funds.tab_common import rebalance_roll_up
    
    df_h["SimpleCat"] = df_h["Category"].apply(rebalance_roll_up)
    
    detected_profile = profile
    if profile == "Auto":
        # Derive investor's actual risk profile based on their revealed preference (current Equity allocation)
        current_equity = df_h[df_h["SimpleCat"] == "Equity"]["Market Value"].sum()
        equity_pct = (current_equity / total_value * 100)
        
        if equity_pct >= 65:
            detected_profile = "Aggressive"
        elif equity_pct >= 35:
            detected_profile = "Balanced"
        else:
            detected_profile = "Conservative"
            
    targets = RISK_PROFILES.get(detected_profile, RISK_PROFILES["Balanced"])
    
    current_allocs = {}
    for cat in targets.keys():
        current_allocs[cat] = float(df_h[df_h["SimpleCat"] == cat]["Market Value"].sum() / total_value * 100)

    drifts = {cat: current_allocs[cat] - target for cat, target in targets.items()}
    # FIX P2-2: Use RMSD instead of Euclidean L2 norm.
    # L2 norm grows with the number of categories, making scores from
    # profiles with different category counts incomparable.
    # RMSD = sqrt(sum(d^2) / N) normalizes for category count.
    n_cats = len(drifts) if drifts else 1
    drift_score = float(np.sqrt(sum(d**2 for d in drifts.values()) / n_cats))

    # Order generation — sell-side is tax-lot aware (ELSS lock-in + LTCG-preference)
    orders = []
    for cat, d in drifts.items():
        if abs(d) > REBALANCE_THRESHOLD:
            amount = abs(d) / 100 * total_value
            cat_mask = df_h["SimpleCat"] == cat
            cat_funds = df_h[cat_mask].sort_values(by="Market Value", ascending=False)

            if d > 0:
                sell_info = select_sell_candidate(df_h, df_t, cat_mask, amount) if not cat_funds.empty else {}
                fund_suggestion = (
                    f" (e.g. {sell_info['fund_suggestion']})" if sell_info.get("fund_suggestion")
                    else (f" (e.g. {cat_funds.iloc[0]['Fund']})" if not cat_funds.empty else "")
                )
                note = f"Reduce {cat} exposure by {abs(d):.1f}%{fund_suggestion} to reach target."
                if sell_info.get("locked_note"):
                    note += f" {sell_info['locked_note']}"
                if sell_info.get("exit_load_note"):
                    note += f" {sell_info['exit_load_note']}"
                if sell_info.get("shortfall"):
                    available = amount - sell_info["shortfall"]
                    note += f" Only ₹{available:,.0f} of the ₹{amount:,.0f} target is available unlocked."

                orders.append({
                    "action": "Sell (Overweight)",
                    "category": cat,
                    "amount": round(amount, 0),
                    "note": note,
                    "tax_estimate": sell_info.get("estimated_tax"),
                    "ltcg_pulled": sell_info.get("ltcg_pulled"),
                    "stcg_pulled": sell_info.get("stcg_pulled"),
                    "exit_load_estimate": sell_info.get("estimated_exit_load"),
                })
            else:
                if not cat_funds.empty:
                    fund_suggestion = f" (e.g. {cat_funds.iloc[0]['Fund']})"
                elif cat == "Hybrid":
                    fund_suggestion = " (e.g., consider adding a standard Aggressive Hybrid Fund)"
                elif cat == "Other":
                    fund_suggestion = " (e.g., consider adding a standard Gold ETF)"
                else:
                    fund_suggestion = f" (e.g., consider adding a standard {cat} Fund)"

                orders.append({
                    "action": "Buy (Underweight)",
                    "category": cat,
                    "amount": round(amount, 0),
                    "note": f"Increase {cat} exposure by {abs(d):.1f}%{fund_suggestion} to reach target."
                })

    # ── Institutional Fix: Intra-Equity Rebalancing (Aggressive Profile) ──
    if profile == "Aggressive":
        equity_funds = df_h[df_h["SimpleCat"] == "Equity"]
        equity_total = float(equity_funds["Market Value"].sum())
        if equity_total > 0:
            sc_mask  = (df_h["SimpleCat"] == "Equity") & (df_h["Cap Type"] == "Small Cap")
            sc_val   = float(df_h[sc_mask]["Market Value"].sum())
            sc_weight_in_equity = (sc_val / equity_total) * 100

            # If Small Cap is > 40% of equity, suggest de-risking within equity
            if sc_weight_in_equity > 40:
                switch_amount = sc_val * 0.25  # Suggest rebalancing 25% of the small cap exposure
                sc_sell_info = select_sell_candidate(df_h, df_t, sc_mask, switch_amount)
                note = f"Small Cap is {sc_weight_in_equity:.1f}% of your equity — consider rebalancing into Large/Flexi Cap to manage volatility while remaining Aggressive."
                if sc_sell_info.get("locked_note"):
                    note += f" {sc_sell_info['locked_note']}"
                if sc_sell_info.get("exit_load_note"):
                    note += f" {sc_sell_info['exit_load_note']}"

                orders.append({
                    "action": "Switch (Intra-Equity)",
                    "category": "Small Cap → Large Cap",
                    "amount": round(switch_amount, 0),
                    "note": note,
                    "tax_estimate": sc_sell_info.get("estimated_tax"),
                    "ltcg_pulled": sc_sell_info.get("ltcg_pulled"),
                    "stcg_pulled": sc_sell_info.get("stcg_pulled"),
                    "exit_load_estimate": sc_sell_info.get("estimated_exit_load"),
                })

    return {
        "drift_score": round(drift_score, 2),
        "status": "Balanced" if drift_score < REBALANCE_THRESHOLD else "Rebalancing Required",
        "drifts": {k: round(v, 2) for k, v in drifts.items()},
        "orders": orders
    }
