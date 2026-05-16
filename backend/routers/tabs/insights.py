"""
routers/tabs/insights.py

CIO Intelligence Engine & Wealth Advisory Nudges
================================================
Evaluates comprehensive portfolio structural efficiency. Computes dynamic weighted expense drag
across Regular and Direct plan allocations, assesses concentration risks, maps goal-aligned horizons,
and synthesizes an institutional Portfolio Health Score and SIP Habit Rating.
"""

from fastapi import APIRouter
from core.sessions import get_session
from core.config import GOAL_TIMELINE, EXP_RATIO_BANDS, PE_ESTIMATES

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
    liquid_val = float(df_h[df_h["Category"] == "Liquid"]["Market Value"].sum())
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
        nudges.append({"type":"warn","message":"Low liquid reserves. Consider adding 5-10% in liquid funds for emergencies."})

    # 3. Wealth Planning Horizon Timeline
    goal_data = []
    for cat, (goal_label, color, _) in GOAL_TIMELINE.items():
        val = float(df_h[df_h["Category"] == cat]["Market Value"].sum())
        if val > 0:
            goal_data.append({
                "category": cat, "goal": goal_label, "value": round(val, 0),
                "pct": round(val / total_value * 100, 1), "color": color
            })

    # Calculate dynamic weighted expense ratio drag
    total_expense = 0.0
    for _, row in df_h.iterrows():
        cat = row["Category"]
        val = row["Market Value"]
        lo, hi = EXP_RATIO_BANDS.get(cat, (0.50, 1.00))
        # Account for typical Direct vs Regular plan expense drag delta (~0.8%)
        if "direct" in str(row["Plan"]).lower():
            est_er = lo
        else:
            est_er = lo + 0.80
        total_expense += val * (est_er / 100.0)

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
    score_div   = 25 if 5 <= num_funds <= 12 else (15 if num_funds > 15 else 10)
    score_dir   = 20 if reg_pct == 0 else max(0, 20 - (reg_pct * 0.5))
    score_conc  = 15 if top_weight < 15 else max(0, 15 - (top_weight - 15) * 0.5)
    score_bal   = 10 if liquid_pct >= 5 and sc_pct <= 20 else 5

    score_breakdown = [
        {"label":"Alpha vs Benchmark", "max":30, "score": round(score_alpha)},
        {"label":"Fund Diversification","max":25, "score": round(score_div)},
        {"label":"Direct Plan Usage",   "max":20, "score": round(score_dir)},
        {"label":"Concentration Risk",  "max":15, "score": round(score_conc)},
        {"label":"Category Balance",    "max":10, "score": round(score_bal)},
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
