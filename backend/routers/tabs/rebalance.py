"""
routers/tabs/rebalance.py

Institutional CIO Rebalancing & RMSD Drift Audit Engine
=======================================================
Evaluates portfolio asset class drift against target model portfolios (Conservative, Balanced,
Aggressive) utilizing Root-Mean-Square Deviation (RMSD). Synthesizes actionable rebalancing orders
and intra-equity volatility management switches for institutional advisory parity.
"""

from fastapi import APIRouter
from core.sessions import get_session
from core.config import get_standard_category
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
    def roll_up(cat):
        c = get_standard_category(cat)
        if c in ["Equity", "Debt", "Hybrid"]: return c
        return "Other"
    
    df_h["SimpleCat"] = df_h["Category"].apply(roll_up)
    
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

    # Simple order generation
    orders = []
    for cat, d in drifts.items():
        if abs(d) > REBALANCE_THRESHOLD:
            amount = abs(d) / 100 * total_value
            cat_funds = df_h[df_h["SimpleCat"] == cat].sort_values(by="Market Value", ascending=False)
            if not cat_funds.empty:
                fund_suggestion = f" (e.g. {cat_funds.iloc[0]['Fund']})"
            else:
                if cat == "Hybrid":
                    fund_suggestion = " (e.g., consider adding a standard Aggressive Hybrid Fund)"
                elif cat == "Other":
                    fund_suggestion = " (e.g., consider adding a standard Gold ETF)"
                else:
                    fund_suggestion = f" (e.g., consider adding a standard {cat} Fund)"
            
            if d > 0:
                orders.append({
                    "action": "Sell (Overweight)",
                    "category": cat,
                    "amount": round(amount, 0),
                    "note": f"Reduce {cat} exposure by {abs(d):.1f}%{fund_suggestion} to reach target."
                })
            else:
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
            sc_funds = equity_funds[equity_funds["Cap Type"] == "Small Cap"]
            sc_val   = float(sc_funds["Market Value"].sum())
            sc_weight_in_equity = (sc_val / equity_total) * 100
            
            # If Small Cap is > 40% of equity, suggest de-risking within equity
            if sc_weight_in_equity > 40:
                orders.append({
                    "action": "Switch (Intra-Equity)",
                    "category": "Small Cap → Large Cap",
                    "amount": round(sc_val * 0.25, 0), # Suggest rebalancing 25% of the small cap exposure
                    "note": f"Small Cap is {sc_weight_in_equity:.1f}% of your equity — consider rebalancing into Large/Flexi Cap to manage volatility while remaining Aggressive."
                })

    return {
        "drift_score": round(drift_score, 2),
        "status": "Balanced" if drift_score < REBALANCE_THRESHOLD else "Rebalancing Required",
        "drifts": {k: round(v, 2) for k, v in drifts.items()},
        "orders": orders
    }
