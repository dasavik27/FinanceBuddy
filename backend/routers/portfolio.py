"""
routers/portfolio.py
All portfolio analytics endpoints.
All computation delegates to logic_adapter (which delegates to logic.py).
"""

from __future__ import annotations

import io
import uuid
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from logic_adapter import (
    BENCHMARKS, CATEGORY_COLORS, RISK_TIERS, MAX_DD_ESTIMATE,
    EXP_RATIOS, GOAL_TIMELINE, SECTOR_COLORS, FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT,
    parse_cas, fetch_benchmark,
    compute_xirr, compute_benchmark_xirr, compute_period_comparison,
    compute_rolling_returns, estimate_expense_drag, elss_lock_in_analysis,
    compute_portfolio_score, sip_consistency_score, fmt_inr,
)

router = APIRouter()

# ── In-memory session store (zero disk retention) ──
_SESSIONS: dict[str, dict] = {}


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Safely serialise a DataFrame to JSON-safe records."""
    if df is None or df.empty:
        return []
    df2 = df.copy()
    for col in df2.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df2[col] = df2[col].dt.strftime("%Y-%m-%d")
    for col in df2.columns:
        df2[col] = df2[col].apply(
            lambda v: None if (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) else v
        )
    return df2.to_dict(orient="records")


def _get_session(session_id: str) -> dict:
    if session_id not in _SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found. Please re-upload your CAS.")
    return _SESSIONS[session_id]


# ─────────────────────────────────────────────
# PARSE CAS
# ─────────────────────────────────────────────
@router.post("/parse")
async def parse(
    file: UploadFile = File(...),
    password: str    = Form(...),
):
    raw = await file.read()
    df_h, df_t, df_s, err, is_partial = parse_cas(raw, password)

    if err:
        raise HTTPException(status_code=422, detail=err)
    if df_h.empty:
        raise HTTPException(status_code=422, detail="No active holdings found in CAS.")

    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "df_holdings": df_h,
        "df_txns":     df_t,
        "df_sips":     df_s,
        "is_partial":  is_partial,
        "created_at":  datetime.utcnow().isoformat(),
    }

    return {
        "session_id":  session_id,
        "is_partial":  is_partial,
        "fund_count":  len(df_h),
        "amc_count":   df_h["AMC"].nunique(),
        "categories":  sorted(df_h["Category"].unique().tolist()),
        "amcs":        sorted(df_h["AMC"].unique().tolist()),
        "benchmarks":  list(BENCHMARKS.keys()),
    }


# ─────────────────────────────────────────────
# SUMMARY — top-level KPIs
# ─────────────────────────────────────────────
@router.get("/{session_id}/summary")
def summary(
    session_id: str,
    benchmark:  str  = "Nifty 50",
    category:   str  = "",
    amc:        str  = "",
    plan:       str  = "All",
    min_alloc:  float = 0.0,
):
    s = _get_session(session_id)
    df_h = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    df_t = _filter_txns(s["df_txns"], df_h)

    total_value    = float(df_h["Market Value"].sum())
    total_invested = float(df_h["Invested"].sum())
    total_gain     = total_value - total_invested
    gain_pct       = (total_gain / total_invested * 100) if total_invested > 0 else 0.0
    num_funds      = len(df_h)
    num_amcs       = df_h["AMC"].nunique()

    ticker     = BENCHMARKS.get(benchmark, "^NSEI")
    bench_data = fetch_benchmark(ticker, 9999)

    portfolio_xirr          = compute_xirr(df_t, total_value)
    bench_xirr_val, _       = compute_benchmark_xirr(df_t, bench_data)
    alpha                   = portfolio_xirr - bench_xirr_val
    port_score              = compute_portfolio_score(df_h, portfolio_xirr, bench_xirr_val)
    expense_drag            = estimate_expense_drag(df_h)
    sip_score_val           = sip_consistency_score(s["df_sips"])

    bench_cagr = 0.0
    if not bench_data.empty and len(bench_data) >= 2:
        days = max((bench_data.index[-1] - bench_data.index[0]).days, 1)
        bench_cagr = (((float(bench_data.iloc[-1]) / float(bench_data.iloc[0])) ** (365.0 / days)) - 1) * 100

    return {
        "total_value":     total_value,
        "total_invested":  total_invested,
        "total_gain":      total_gain,
        "gain_pct":        round(gain_pct, 2),
        "portfolio_xirr":  round(portfolio_xirr, 2),
        "bench_xirr":      round(bench_xirr_val, 2),
        "bench_cagr":      round(bench_cagr, 2),
        "alpha":           round(alpha, 2),
        "port_score":      port_score,
        "expense_drag":    round(expense_drag, 0),
        "sip_score":       sip_score_val,
        "num_funds":       num_funds,
        "num_amcs":        num_amcs,
        "is_partial":      s["is_partial"],
    }


# ─────────────────────────────────────────────
# OVERVIEW — period comparison + chart
# ─────────────────────────────────────────────
@router.get("/{session_id}/overview")
def overview(
    session_id:  str,
    benchmark:   str   = "Nifty 50",
    period:      str   = "1Y",
    category:    str   = "",
    amc:         str   = "",
    plan:        str   = "All",
    min_alloc:   float = 0.0,
):
    s      = _get_session(session_id)
    df_h   = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    df_t   = _filter_txns(s["df_txns"], df_h)
    period_days = {"1M":30,"3M":90,"6M":180,"1Y":365,"3Y":1095,"5Y":1825,"ALL":9999}.get(period, 365)

    ticker     = BENCHMARKS.get(benchmark, "^NSEI")
    bench_data = fetch_benchmark(ticker, 9999)
    total_value = float(df_h["Market Value"].sum())

    comp = compute_period_comparison(df_t, total_value, bench_data, period_days)

    # Build normalised chart series
    from datetime import timedelta
    if period_days < 9999:
        cutoff = bench_data.index[-1] - timedelta(days=period_days)
        bench_slice = bench_data[bench_data.index >= cutoff]
    else:
        bench_slice = bench_data
    if len(bench_slice) < 2:
        bench_slice = bench_data.iloc[-2:]

    bench_norm = (bench_slice / bench_slice.iloc[0] * 100).round(2)

    # Portfolio growth curve (proxy via benchmark shape + alpha)
    alpha_daily = (comp["port_pct"] - comp["bench_pct"]) / max(len(bench_slice), 1) / 100
    port_norm   = (bench_norm * (1 + alpha_daily)).round(2)

    chart_dates = bench_slice.index.strftime("%Y-%m-%d").tolist()

    return {
        **comp,
        "benchmark_name": benchmark,
        "period":         period,
        "chart": {
            "dates":     chart_dates,
            "portfolio": port_norm.tolist(),
            "benchmark": bench_norm.tolist(),
        },
    }


# ─────────────────────────────────────────────
# HOLDINGS LIST
# ─────────────────────────────────────────────
@router.get("/{session_id}/holdings")
def holdings(
    session_id: str,
    sort_by:    str   = "Market Value",
    ascending:  bool  = False,
    search:     str   = "",
    cap_filter: str   = "All",
    category:   str   = "",
    amc:        str   = "",
    plan:       str   = "All",
    min_alloc:  float = 0.0,
):
    s    = _get_session(session_id)
    df_h = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)

    if search:
        df_h = df_h[df_h["Fund"].str.contains(search, case=False, na=False)]
    if cap_filter != "All":
        df_h = df_h[df_h["Cap Type"] == cap_filter]
    if sort_by in df_h.columns:
        df_h = df_h.sort_values(sort_by, ascending=ascending)

    records = _df_to_records(df_h)
    # Attach colour per category
    for r in records:
        r["color"] = CATEGORY_COLORS.get(r.get("Category", ""), "#94A3B8")

    return {
        "holdings": records,
        "total": len(records),
        "cap_types": sorted(s["df_holdings"]["Cap Type"].unique().tolist()),
    }


# ─────────────────────────────────────────────
# ALLOCATION (donut / bar data)
# ─────────────────────────────────────────────
@router.get("/{session_id}/allocation")
def allocation(
    session_id: str,
    category: str = "",
    amc: str = "",
    plan: str = "All",
    min_alloc: float = 0.0,
):
    s    = _get_session(session_id)
    df_h = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    total = float(df_h["Market Value"].sum())

    # Broad asset class
    eq_val   = float(df_h[df_h["Category"].isin(["Equity","ELSS","Index"])]["Market Value"].sum())
    debt_val = float(df_h[df_h["Category"].isin(["Debt","Liquid"])]["Market Value"].sum())
    hyb_val  = float(df_h[df_h["Category"] == "Hybrid"]["Market Value"].sum())
    oth_val  = max(0.0, total - eq_val - debt_val - hyb_val)

    # By category
    cat_grp = df_h.groupby("Category")["Market Value"].sum().reset_index()
    cat_grp["color"] = cat_grp["Category"].map(CATEGORY_COLORS)
    cat_grp["pct"]   = (cat_grp["Market Value"] / total * 100).round(1) if total > 0 else 0

    # By cap size
    cap_grp = df_h.groupby("Cap Type")["Market Value"].sum().sort_values(ascending=False).reset_index()
    cap_grp["pct"] = (cap_grp["Market Value"] / total * 100).round(1) if total > 0 else 0

    # By plan
    plan_grp = df_h.groupby("Plan")["Market Value"].sum().reset_index()
    plan_grp["color"] = plan_grp["Plan"].map({"Direct":"#10B981","Regular":"#F59E0B"}).fillna("#94A3B8")

    # Concentration heatmap (top 15)
    weight_data = df_h[["Fund","AMC","Category","Weight%"]].sort_values("Weight%", ascending=False).head(15)

    reg_pct = float(df_h[df_h["Plan"]=="Regular"]["Market Value"].sum() / total * 100) if total > 0 else 0

    return {
        "broad": [
            {"label":"Equity", "value": round(eq_val,2),   "pct": round(eq_val/total*100,1) if total else 0,   "color":"#6366F1"},
            {"label":"Debt",   "value": round(debt_val,2), "pct": round(debt_val/total*100,1) if total else 0, "color":"#10B981"},
            {"label":"Hybrid", "value": round(hyb_val,2),  "pct": round(hyb_val/total*100,1) if total else 0,  "color":"#F59E0B"},
            {"label":"Other",  "value": round(oth_val,2),  "pct": round(oth_val/total*100,1) if total else 0,  "color":"#94A3B8"},
        ],
        "by_category": _df_to_records(cat_grp),
        "by_cap":      _df_to_records(cap_grp),
        "by_plan":     _df_to_records(plan_grp),
        "heatmap":     _df_to_records(weight_data),
        "reg_pct":     round(reg_pct, 1),
    }


# ─────────────────────────────────────────────
# PERFORMANCE — per-fund analysis
# ─────────────────────────────────────────────
@router.get("/{session_id}/performance")
def performance(
    session_id: str,
    period:     str  = "1Y",
    benchmark:  str  = "Nifty 50",
    verdict:    str  = "All",
    action:     str  = "All",
    sort_by:    str  = "alpha_desc",
    category:   str  = "",
    amc:        str  = "",
    plan:       str  = "All",
    min_alloc:  float = 0.0,
):
    from datetime import timedelta

    s      = _get_session(session_id)
    df_h   = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    df_t   = _filter_txns(s["df_txns"], df_h)
    perf_days = {"1M":30,"6M":180,"1Y":365,"3Y":1095,"5Y":1825,"All Time":9999}.get(period, 365)

    ticker     = BENCHMARKS.get(benchmark, "^NSEI")
    bench_data = fetch_benchmark(ticker, perf_days)
    total_value = float(df_h["Market Value"].sum())
    comp = compute_period_comparison(df_t, total_value, bench_data, perf_days)

    cat_gains: dict[str, list[float]] = {}
    for _, row in df_h.iterrows():
        cat_gains.setdefault(row["Category"], []).append(float(row["Gain%"]))

    results = []
    for _, row in df_h.iterrows():
        fn       = row["Fund"]
        cur_val  = float(row["Market Value"])
        cat      = row["Category"]
        cap_type = row["Cap Type"]
        plan_r   = row["Plan"]

        fund_txns = (df_t[df_t["Fund"] == fn]
                     if not df_t.empty and "Fund" in df_t.columns
                     else pd.DataFrame())

        # Period slice
        txns_to_analyse = fund_txns
        if not fund_txns.empty and "Date" in fund_txns.columns and perf_days < 9999:
            cutoff   = pd.Timestamp.now().normalize() - pd.Timedelta(days=perf_days)
            pre_txns = fund_txns[fund_txns["Date"] < cutoff]
            per_txns = fund_txns[fund_txns["Date"] >= cutoff]
            pre_bought   = pre_txns.loc[pre_txns["Units"]>0,"Amount"].abs().sum() if not pre_txns.empty else 0
            total_bought = fund_txns.loc[fund_txns["Units"]>0,"Amount"].abs().sum() if not fund_txns.empty else 0
            frac = pre_bought / total_bought if total_bought > 0 else 0
            opening_val = cur_val * frac
            if opening_val > 0:
                opening_row = pd.DataFrame([{
                    "Date": cutoff, "Amount": -opening_val, "Units": 1.0,
                    "Type": "PURCHASE", "Fund": fn, "AMC": "", "Category": cat, "NAV": 0.0
                }])
                txns_to_analyse = pd.concat([opening_row, per_txns], ignore_index=True)
            else:
                txns_to_analyse = per_txns if not per_txns.empty else fund_txns

        fund_xi = compute_xirr(txns_to_analyse, cur_val)

        # Per-fund benchmark
        from logic_adapter import FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT
        bench_ticker_f, bench_display_f = _get_fund_benchmark(cat, cap_type, fn)
        bench_series = fetch_benchmark(bench_ticker_f, 9999) if bench_ticker_f else pd.Series(dtype=float)
        bench_xi, bench_cur = (0.0, 0.0)
        if not bench_series.empty:
            bench_xi, bench_cur = compute_benchmark_xirr(txns_to_analyse, bench_series)

        alpha_f = fund_xi - bench_xi
        roll_periods = [30, 180, 365, 1095, 1825]
        roll_labels  = ["1M","6M","1Y","3Y","5Y"]
        bench_rolls  = compute_rolling_returns(bench_series, roll_periods) if not bench_series.empty else {}
        fund_rolls   = {d: fund_xi*(d/365.0) for d in roll_periods}
        beats        = sum(1 for d in roll_periods if fund_rolls.get(d,0) > bench_rolls.get(d,0))
        consistency  = round(beats / len(roll_periods) * 10, 1)

        tier = RISK_TIERS.get(cat, RISK_TIERS["Other"])
        vol, beta, risk_label = tier
        rf      = 5.0
        sharpe  = (fund_xi - rf) / vol if vol > 0 else 0.0
        sortino = (fund_xi - rf) / (vol*0.65) if vol > 0 else 0.0
        max_dd  = -MAX_DD_ESTIMATE.get(cat, 25)
        lo, hi  = EXP_RATIOS.get(cat, (0.50, 1.50))
        er      = lo if plan_r == "Direct" else hi

        same_cat      = cat_gains.get(cat, [])
        fund_gain_pct = float(row["Gain%"])
        cat_rank  = sum(1 for g in sorted(same_cat, reverse=True) if g > (fund_gain_pct + 1e-6)) + 1
        cat_total = len(same_cat)
        cat_rank  = min(cat_rank, cat_total)

        if alpha_f >= 2.0 and consistency >= 6:
            verdict_r, v_cls = "Strong",  "strong"
        elif alpha_f >= -1.0:
            verdict_r, v_cls = "Average", "average"
        else:
            verdict_r, v_cls = "Weak",    "weak"

        if verdict_r == "Strong" and plan_r == "Direct":
            action_r = "Keep"
        elif verdict_r == "Weak" or (alpha_f < -2 and er > 1.2):
            action_r = "Replace with Index"
        else:
            action_r = "Review"

        results.append({
            "fund":          fn,
            "category":      cat,
            "cap_type":      cap_type,
            "plan":          plan_r,
            "bench_display": bench_display_f,
            "fund_xi":       round(fund_xi, 2),
            "bench_xi":      round(bench_xi, 2),
            "alpha":         round(alpha_f, 2),
            "bench_cur":     round(bench_cur, 0),
            "cur_value":     round(cur_val, 0),
            "consistency":   consistency,
            "vol":           vol,
            "beta":          beta,
            "risk_label":    risk_label,
            "sharpe":        round(sharpe, 2),
            "sortino":       round(sortino, 2),
            "max_dd":        max_dd,
            "er":            er,
            "cat_rank":      cat_rank,
            "cat_total":     cat_total,
            "verdict":       verdict_r,
            "verdict_cls":   v_cls,
            "action":        action_r,
            "roll_labels":   roll_labels,
            "fund_rolls":    [round(fund_rolls.get(d,0),2) for d in roll_periods],
            "bench_rolls":   [round(bench_rolls.get(d,0),2) for d in roll_periods],
            "color":         CATEGORY_COLORS.get(cat, "#94A3B8"),
        })

    # Filters
    if verdict != "All":
        results = [r for r in results if r["verdict"] == verdict]
    if action != "All":
        results = [r for r in results if r["action"] == action]

    sort_map = {
        "alpha_desc":    ("alpha",       True),
        "alpha_asc":     ("alpha",       False),
        "fund_xi":       ("fund_xi",     True),
        "consistency":   ("consistency", True),
        "name":          ("fund",        False),
    }
    key, rev = sort_map.get(sort_by, ("alpha", True))
    results.sort(key=lambda r: r[key], reverse=rev)

    n_strong  = sum(1 for r in results if r["verdict"] == "Strong")
    n_average = sum(1 for r in results if r["verdict"] == "Average")
    n_weak    = sum(1 for r in results if r["verdict"] == "Weak")
    avg_alpha = float(np.mean([r["alpha"] for r in results])) if results else 0.0

    return {
        "portfolio_return":  round(comp["port_pct"], 2),
        "benchmark_return":  round(comp["bench_pct"], 2),
        "alpha":             round(comp["port_pct"] - comp["bench_pct"], 2),
        "use_xirr":          comp["use_xirr"],
        "n_strong":          n_strong,
        "n_average":         n_average,
        "n_weak":            n_weak,
        "avg_alpha":         round(avg_alpha, 2),
        "funds":             results,
    }


# ─────────────────────────────────────────────
# TAX
# ─────────────────────────────────────────────
@router.get("/{session_id}/tax")
def tax(session_id: str, category: str = "", amc: str = "", plan: str = "All", min_alloc: float = 0.0):
    s    = _get_session(session_id)
    df_h = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    df_t = _filter_txns(s["df_txns"], df_h)

    elss_df  = df_h[df_h["Category"] == "ELSS"]
    elss_val = float(elss_df["Market Value"].sum())
    elss_inv = float(elss_df["Invested"].sum())

    equity_gain = float(df_h[df_h["Category"].isin(["Equity","ELSS","Index"])]["Gain"].sum())
    debt_gain   = float(df_h[df_h["Category"].isin(["Debt","Liquid","Hybrid"])]["Gain"].sum())
    ltcg_equity = max(0, equity_gain - 125000) * 0.125 if equity_gain > 125000 else 0
    stcg_debt   = max(0, debt_gain) * 0.30

    elss_analysis = elss_lock_in_analysis(df_h, df_t)
    for item in elss_analysis:
        for k in ["Earliest Investment", "Lock-in Ends"]:
            if k in item and hasattr(item[k], "strftime"):
                item[k] = item[k].strftime("%Y-%m-%d")

    return {
        "elss_value":    round(elss_val, 0),
        "elss_invested": round(elss_inv, 0),
        "elss_count":    len(elss_df),
        "equity_gain":   round(equity_gain, 0),
        "debt_gain":     round(debt_gain, 0),
        "ltcg_equity":   round(ltcg_equity, 0),
        "stcg_debt":     round(stcg_debt, 0),
        "elss_lockin":   elss_analysis,
    }


# ─────────────────────────────────────────────
# SMART INSIGHTS
# ─────────────────────────────────────────────
@router.get("/{session_id}/insights")
def insights(session_id: str, category: str = "", amc: str = "", plan: str = "All", min_alloc: float = 0.0):
    s    = _get_session(session_id)
    df_h = _apply_filters(s["df_holdings"], category, amc, plan, min_alloc)
    df_t = _filter_txns(s["df_txns"], df_h)
    df_s = s["df_sips"]

    total_value  = float(df_h["Market Value"].sum())
    num_funds    = len(df_h)
    expense_drag = estimate_expense_drag(df_h)
    sip_sc       = sip_consistency_score(df_s)

    # ELSS for tax saving
    elss_val = float(df_h[df_h["Category"] == "ELSS"]["Market Value"].sum())

    # Emergency fund
    liquid_val = float(df_h[df_h["Category"].isin(["Liquid"])]["Market Value"].sum())
    liquid_pct = liquid_val / total_value * 100 if total_value > 0 else 0

    # Cap allocation
    sc_val = float(df_h[df_h["Cap Type"] == "Small Cap"]["Market Value"].sum())
    sc_pct = sc_val / total_value * 100 if total_value > 0 else 0

    reg_val = float(df_h[df_h["Plan"] == "Regular"]["Market Value"].sum())
    reg_pct = reg_val / total_value * 100 if total_value > 0 else 0
    reg_count = int(len(df_h[df_h["Plan"] == "Regular"]))

    top_weight = float(df_h["Weight%"].max()) if not df_h.empty else 0
    top_fund   = df_h.loc[df_h["Weight%"].idxmax(), "Fund"][:50] if not df_h.empty else ""

    # Portfolio score breakdown
    port_xi, _ = compute_benchmark_xirr(df_t, pd.Series(dtype=float))
    port_score = compute_portfolio_score(df_h, port_xi, 0)

    # Goal timeline
    goal_data = []
    if total_value > 0:
        for cat, (goal_label, color, _) in GOAL_TIMELINE.items():
            val = float(df_h[df_h["Category"] == cat]["Market Value"].sum())
            if val > 0:
                goal_data.append({
                    "category": cat,
                    "goal":     goal_label,
                    "value":    round(val, 0),
                    "pct":      round(val / total_value * 100, 1),
                    "color":    color,
                })

    nudges = []
    if reg_count > 0:
        nudges.append({"type":"warn","message":f"{reg_count} fund(s) worth ₹{reg_val:,.0f} in Regular plans. Switching to Direct saves ~0.5–1.5% annually."})
    if top_weight > 25:
        nudges.append({"type":"warn","message":f"High concentration: '{top_fund}' is {top_weight:.1f}% of portfolio. Consider diversifying below 20%."})
    if sc_pct > 30:
        nudges.append({"type":"danger","message":f"Small cap allocation is {sc_pct:.1f}% — aggressive. Ensure your risk tolerance matches."})
    elif sc_pct > 15:
        nudges.append({"type":"info","message":f"Small cap allocation: {sc_pct:.1f}%. Good exposure for long-term wealth creation."})
    if num_funds < 3:
        nudges.append({"type":"warn","message":"Very few funds. Diversify across categories for better risk management."})
    elif num_funds > 15:
        nudges.append({"type":"info","message":f"You hold {num_funds} funds. Consider consolidating — too many reduces alpha."})
    if expense_drag / total_value * 100 > 1.0 and total_value > 0:
        nudges.append({"type":"warn","message":f"Expense ratio drag ({expense_drag/total_value*100:.2f}%) above 1%. Erodes compounding."})
    if liquid_pct < 3 and total_value > 500000:
        nudges.append({"type":"warn","message":"Less than 3% in liquid funds. Consider adding an emergency/liquid fund for quick access."})

    score_breakdown = [
        {"label":"Alpha vs Benchmark", "max":30},
        {"label":"Fund Diversification","max":25},
        {"label":"Direct Plan Usage",   "max":20},
        {"label":"Concentration Risk",  "max":15},
        {"label":"Category Balance",    "max":10},
    ]

    return {
        "nudges":          nudges,
        "goal_timeline":   goal_data,
        "score":           port_score,
        "score_breakdown": score_breakdown,
        "sip_score":       sip_sc,
        "liquid_pct":      round(liquid_pct, 1),
        "liquid_val":      round(liquid_val, 0),
        "expense_drag":    round(expense_drag, 0),
        "expense_pct":     round(expense_drag / total_value * 100, 2) if total_value > 0 else 0,
        "elss_val":        round(elss_val, 0),
    }


# ─────────────────────────────────────────────
# TRANSACTIONS
# ─────────────────────────────────────────────
@router.get("/{session_id}/transactions")
def transactions(session_id: str, fund: str = "", limit: int = 200):
    s    = _get_session(session_id)
    df_t = s["df_txns"].copy()
    if fund:
        df_t = df_t[df_t["Fund"].str.contains(fund, case=False, na=False)]
    df_t = df_t.sort_values("Date", ascending=False).head(limit)
    return {"transactions": _df_to_records(df_t), "total": len(df_t)}


# ─────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────
def _apply_filters(df_h: pd.DataFrame, category="", amc="", plan="All", min_alloc=0.0) -> pd.DataFrame:
    df = df_h.copy()
    if category:
        cats = [c.strip() for c in category.split(",") if c.strip()]
        if cats:
            df = df[df["Category"].isin(cats)]
    if amc:
        amcs = [a.strip() for a in amc.split(",") if a.strip()]
        if amcs:
            df = df[df["AMC"].isin(amcs)]
    if plan != "All":
        df = df[df["Plan"] == plan]
    if min_alloc > 0:
        df = df[df["Weight%"] >= min_alloc]
    return df


def _filter_txns(df_t: pd.DataFrame, df_h: pd.DataFrame) -> pd.DataFrame:
    if df_t.empty or df_h.empty:
        return pd.DataFrame()
    funds = set(df_h["Fund"].tolist())
    if "Fund" not in df_t.columns:
        return pd.DataFrame()
    return df_t[df_t["Fund"].isin(funds)]


def _get_fund_benchmark(category: str, cap_type: str, fund_name: str):
    if cap_type in FUND_BENCH_BY_CAP:
        return FUND_BENCH_BY_CAP[cap_type]
    if category in FUND_BENCH_BY_CAT:
        return FUND_BENCH_BY_CAT[category]
    return ("^NSEI", "Nifty 50")


# expose for performance endpoint
from logic_adapter import MAX_DD_ESTIMATE, EXP_RATIOS  # noqa re-export


# ─────────────────────────────────────────────
# FIFO REDEMPTION TAX SIMULATOR
# ─────────────────────────────────────────────
@router.get("/{session_id}/fifo")
def fifo_simulation(
    session_id: str,
    fund:       str,
    units:      float,
    nav:        float,
):
    """
    Simulate redemption of `units` units of `fund` at `nav`.
    Uses FIFO logic from logic.py calculate_redemption_impact.
    """
    from logic_adapter import calculate_redemption_impact

    s    = _get_session(session_id)
    df_t = s["df_txns"]

    if df_t.empty:
        raise HTTPException(status_code=422, detail="No transaction data available for FIFO simulation.")

    result = calculate_redemption_impact(df_t, fund, float(units), float(nav))

    if not result:
        raise HTTPException(status_code=422, detail="Could not simulate — no purchase transactions found for this fund.")

    # Serialise the details DataFrame
    details = result.get("details", pd.DataFrame())
    if not details.empty:
        details = details.copy()
        if "Acquisition Date" in details.columns:
            details["Acquisition Date"] = pd.to_datetime(details["Acquisition Date"]).dt.strftime("%d %b %Y")
        for col in ["Cost", "Value", "Gain"]:
            if col in details.columns:
                details[col] = details[col].round(2)
        details_list = details.to_dict(orient="records")
    else:
        details_list = []

    return {
        "total_units":  round(result["total_units"],  4),
        "total_value":  round(result["total_value"],  2),
        "total_cost":   round(result["total_cost"],   2),
        "total_gain":   round(result["total_gain"],   2),
        "stcg_gain":    round(result["stcg_gain"],    2),
        "ltcg_gain":    round(result["ltcg_gain"],    2),
        "stcg_tax":     round(result["stcg_tax"],     2),
        "ltcg_tax":     round(result["ltcg_tax"],     2),
        "total_tax":    round(result["total_tax"],    2),
        "net_proceeds": round(result["net_proceeds"], 2),
        "details":      details_list,
    }
