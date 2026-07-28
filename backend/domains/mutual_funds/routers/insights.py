"""
routers/tabs/insights.py

CIO Intelligence Engine & Wealth Advisory Nudges
================================================
Evaluates comprehensive portfolio structural efficiency. Computes dynamic weighted expense drag
across Regular and Direct plan allocations, assesses concentration risks, maps goal-aligned horizons,
and synthesizes an institutional Portfolio Health Score and SIP Habit Rating.
"""

from fastapi import APIRouter
import pandas as pd
from domains.mutual_funds.sessions import get_session
from shared.config import GOAL_TIMELINE, EXP_RATIO_BANDS, PE_ESTIMATES

router = APIRouter()

@router.get("/{session_id}/insights")
def get_insights(session_id: str):
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    df_s = portfolio.df_s
    total_value = float(df_h["Market Value"].sum())
    num_funds   = len(df_h)

    # 1. Broad Allocation Metrics
    liquid_mask = (df_h["Category"] == "Liquid") | (df_h["Fund"].str.upper().str.contains("LIQUID", na=False))
    liquid_val = float(df_h[liquid_mask]["Market Value"].sum())
    liquid_pct = (liquid_val / total_value * 100) if total_value > 0 else 0
    sc_val = float(df_h[df_h["Cap Type"] == "Small Cap"]["Market Value"].sum())
    sc_pct = (sc_val / total_value * 100) if total_value > 0 else 0
    reg_val = float(df_h[df_h["Plan"] == "Regular"]["Market Value"].sum())
    reg_pct = (reg_val / total_value * 100) if total_value > 0 else 0
    
    top_weight = float(df_h["Weight%"].max()) if not df_h.empty else 0
    top_fund   = df_h.loc[df_h["Weight%"].idxmax(), "Fund"][:50] if not df_h.empty else ""

    # 2. Dynamic Advisory Nudges
    nudges = []
    if reg_pct > 0:
        nudges.append({"type":"warn","message":f"₹{reg_val:,.0f} ({reg_pct:.1f}%) in Regular plans. Switching to Direct saves ~0.5–1.5% annually."})
    if top_weight > 25:
        nudges.append({"type":"warn","message":f"High concentration: '{top_fund}' is {top_weight:.1f}% of portfolio. Target < 20%."})
    if sc_pct > 30:
        nudges.append({"type":"danger","message":f"Small cap allocation is {sc_pct:.1f}% — aggressive. Verify your risk tolerance."})
    if num_funds > 15:
        nudges.append({"type":"info","message":f"Holding {num_funds} funds. Consolidation could reduce overlap and improve alpha."})
    if liquid_pct < 5 and total_value > 500000:
        nudges.append({"type":"warn","message":f"Your liquid reserves ({liquid_pct:.1f}%) are below the recommended 5-10% for emergencies."})

    # 3. Wealth Planning Horizon Timeline
    from shared.config import get_standard_category
    goal_data = []
    
    from domains.mutual_funds.tab_common import get_goal_value
    for cat, (goal_label, color, timeline) in GOAL_TIMELINE.items():
        val = get_goal_value(df_h, cat)
        if val > 0:
            goal_data.append({
                "category": cat, "goal": goal_label, "value": round(val, 0),
                "pct": round(val / total_value * 100, 1), "color": color,
                "timeline": timeline
            })

    from shared.services.market_data import fetch_fund_ter, resolve_scheme_code_from_isin
    from shared.services.fallbacks.deterministic import DeterministicFallback

    # Calculate dynamic weighted expense ratio drag
    total_expense = 0.0
    for _, row in df_h.iterrows():
        val = row.get("Market Value", 0)
        
        # Pull the exact TER resolved by the deterministic engine in holdings.py
        # which guarantees 100% sync with the UI and removes the ₹1,266 gap.
        ter = row.get("TER", 0.0)
        if pd.isna(ter) or ter == 0:
            # Fallback only if missing (should not happen with deterministic engine)
            cat = row.get("Category", "Equity")
            lo, hi = EXP_RATIO_BANDS.get(cat, (0.50, 1.00))
            ter = lo if "direct" in str(row.get("Plan", "")).lower() else lo + 0.80
            
        total_expense += val * (ter / 100.0)

    expense_pct = (total_expense / total_value * 100) if total_value > 0 else 0.85

    # Institutional Portfolio Health Scoring Matrix
    try:
        summary = portfolio.get_summary()
        real_alpha = summary.get("alpha", 0.0)
    except Exception:
        real_alpha = 0.0

    if real_alpha > 5:
        score_alpha = 30
    elif real_alpha > 2:
        score_alpha = 22
    elif real_alpha > 0:
        score_alpha = 15
    else:
        score_alpha = 8
        
    # ── Category-Balance Algorithm (Score out of 25) ──────────────────────
    score_div = 25
    if total_value > 0:
        # 1. Gather specific bucket exposures
        large_val = float(df_h[df_h["Cap Type"] == "Large Cap"]["Market Value"].sum()) if "Cap Type" in df_h.columns else 0
        mid_val   = float(df_h[df_h["Cap Type"] == "Mid Cap"]["Market Value"].sum()) if "Cap Type" in df_h.columns else 0
        small_val = sc_val # Already calculated above
        flexi_val = float(df_h[df_h["Cap Type"] == "Flexi Cap"]["Market Value"].sum()) if "Cap Type" in df_h.columns else 0
        index_val = float(df_h[df_h["Category"].str.contains("Index", case=False, na=False)]["Market Value"].sum()) if "Category" in df_h.columns else 0
        sector_val = float(df_h[df_h["Category"].str.contains("Sector|Thematic", case=False, na=False)]["Market Value"].sum()) if "Category" in df_h.columns else 0
        
        # Rule 1: Core Stability (Large + Flexi + Index)
        core_pct = ((large_val + flexi_val + index_val) / total_value) * 100
        if core_pct < 20: score_div -= 10
        elif core_pct < 30: score_div -= 5
            
        # Rule 2: Market Cap Extremes
        mc_pct = (mid_val / total_value) * 100
        if sc_pct > 40: score_div -= 7
        elif sc_pct > 30: score_div -= 4
        if mc_pct > 50: score_div -= 5
        elif mc_pct > 40: score_div -= 3
            
        # Rule 3: Sector/Thematic Overload
        sector_pct = (sector_val / total_value) * 100
        if sector_pct > 25: score_div -= 5
        elif sector_pct > 15: score_div -= 2
            
        # Rule 4: AMC Concentration
        if "AMC" in df_h.columns and not df_h.empty:
            top_amc_pct = (df_h.groupby("AMC")["Market Value"].sum().max() / total_value) * 100
            if top_amc_pct > 70: score_div -= 5
            elif top_amc_pct > 50: score_div -= 2
            
    score_div = max(0, min(25, score_div))

    score_dir   = 20 if reg_pct == 0 else max(0, 20 - (reg_pct * 0.5))
    score_conc  = 15 if top_weight < 15 else max(0, 15 - (top_weight - 15) * 0.5)
    score_bal   = 10 if liquid_pct >= 5 and sc_pct <= 20 else 5

    score_breakdown = [
        {"label":"Alpha vs Benchmark", "max":30, "score": round(score_alpha)},
        {"label":"Diversification & Balance", "max":25, "score": round(score_div)},
        {"label":"Direct Plan Usage",   "max":20, "score": round(score_dir)},
        {"label":"Concentration Risk",  "max":15, "score": round(score_conc)},
        {"label":"Liquidity & Safety",  "max":10, "score": round(score_bal)},
    ]

    total_score = sum(b["score"] for b in score_breakdown)

    # ── Institutional SIP Habit Score ─────────────────────────────────────
    has_active_sips = not df_s.empty
    habit_score = 4.0 if has_active_sips else 1.0
    perf_score  = min(6.0, max(0, real_alpha / 2 + 3))
    sip_score   = habit_score + perf_score

    return {
        "nudges":          nudges,
        "goal_timeline":   goal_data,
        "score":           total_score,
        "score_breakdown": score_breakdown,
        "sip_score":       sip_score,
        "liquid_val":      liquid_val,
        "liquid_pct":      liquid_pct,
        "expense_drag":    total_expense,
        "expense_pct":     round(expense_pct, 2),
        "elss_val":        float(df_h[df_h["Category"] == "ELSS"]["Market Value"].sum()),
    }
