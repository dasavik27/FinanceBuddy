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
from shared.config import GOAL_TIMELINE, PE_ESTIMATES, BENCHMARKS

router = APIRouter()

@router.get("/{session_id}/insights")
def get_insights(session_id: str, benchmark: str = "Nifty 500"):
    """
    Portfolio health, nudges, and ledger metrics.

    `benchmark` is honored for the Alpha pillar (via get_summary). Other query
    filters (category/AMC/plan) are intentionally whole-portfolio — Insights is
    a CIO view of the full book, not a filtered slice.
    """
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    df_s = portfolio.df_s
    total_value = float(df_h["Market Value"].sum())
    num_funds   = len(df_h)
    # Resolve display/canonical benchmark key for get_summary lookup.
    bench_key = benchmark if benchmark in BENCHMARKS else (
        next((k for k in BENCHMARKS if k.lower() == str(benchmark).lower()), benchmark)
    )

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
    if liquid_pct > 15:
        # Cash-drag nudge: excess Liquid holdings above the 5-10% emergency-fund norm may just be
        # idle "lazy money" losing out on growth-asset returns — but we can't tell from CAS data
        # alone whether it's earmarked for a near-term goal, so this is a prompt, not a verdict.
        nudges.append({"type":"info","message":f"₹{liquid_val:,.0f} ({liquid_pct:.1f}%) is in Liquid funds — well above the 5-10% emergency-fund norm. If this isn't earmarked for a near-term goal, the excess may be a cash drag on long-term returns; consider deploying it if it's just sitting idle."})

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

    # Institutional Portfolio Health Scoring Matrix.
    #
    # One get_summary() call supplies both figures below. This endpoint used to run its
    # own copy of the TER loop and then call get_summary(), which runs the identical
    # loop internally - so the same number was computed twice per request, with the
    # two copies free to drift apart.
    try:
        summary = portfolio.get_summary(benchmark=bench_key)
        real_alpha = summary.get("alpha", 0.0)
        total_expense = summary.get("expense_drag", 0.0)
    except Exception:
        real_alpha = 0.0
        total_expense = portfolio.compute_expense_drag()

    # TER coverage so the UI can show N/A instead of a misleading ₹0 drag.
    ter_covered_value = 0.0
    if not df_h.empty and "TER" in df_h.columns:
        ter_ok = df_h["TER"].notna() & (pd.to_numeric(df_h["TER"], errors="coerce").fillna(0) > 0)
        ter_covered_value = float(df_h.loc[ter_ok, "Market Value"].sum())
    ter_coverage_pct = (ter_covered_value / total_value * 100) if total_value > 0 else 0.0

    expense_pct = (total_expense / total_value * 100) if total_value > 0 else 0.0

    if real_alpha > 5:
        score_alpha = 30
    elif real_alpha > 2:
        score_alpha = 22
    elif real_alpha > 0:
        score_alpha = 15  # pragma: no cover — defensive / hard to exercise in unit tests
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
        "sip_score":       round(sip_score, 1),
        "sip_score_label": "SIP Habit & Performance",
        "liquid_val":      liquid_val,
        "liquid_pct":      round(liquid_pct, 1),
        "expense_drag":    round(total_expense, 0),
        "expense_pct":     round(expense_pct, 2),
        "ter_coverage_pct": round(ter_coverage_pct, 1),
        "expense_available": ter_coverage_pct > 0,
        "elss_val":        float(df_h[df_h["Category"] == "ELSS"]["Market Value"].sum()),
        "benchmark":       bench_key,
        "alpha":           round(real_alpha, 2),
    }
