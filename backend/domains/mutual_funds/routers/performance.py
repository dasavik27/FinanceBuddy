"""
routers/tabs/performance.py

Enterprise Performance Audit & Risk Attribution Gateway
=======================================================
Orchestrates high-speed, multi-threaded quantitative risk modeling for individual holdings.
Calculates Jensen's Alpha, Sharpe & Sortino ratios, Maximum Drawdown, market capture ratios,
and full rolling return series for institutional performance benchmarking.
"""

from fastapi import APIRouter, HTTPException
import logging
logger = logging.getLogger(__name__)

from typing import Optional
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

from domains.mutual_funds.sessions import get_session
from shared.cache import MarketCache
from shared.config import (
    BENCHMARKS, CATEGORY_COLORS, RISK_LABEL,
    EXP_RATIO_BANDS, classify_er,
    PE_ESTIMATES, PB_ESTIMATES, DEBT_METRICS_MAP,
)
from domains.mutual_funds.derived import cached_period_comparison
from domains.mutual_funds.finance import (
    compute_xirr,
    compute_benchmark_xirr,
    compute_risk_metrics,
    compute_trailing_returns,
    compute_rolling_return_series,
    compute_rolling_returns,
    compute_consistency_score,
    is_absolute_return,
)
from shared.services.market_indices import fetch_benchmark_series, benchmark_uses_price_index_blend
from shared.services.market_data import (
    get_fund_benchmark,
    fetch_nav_series_by_isin,
    fetch_nav_series_by_code,
    fetch_nav_series_by_name,
    fetch_fund_ter,
    resolve_scheme_code_from_isin,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _apply_filters(
    df_h: pd.DataFrame,
    category: str,
    amc: str,
    plan: str,
    min_alloc: float,
    include_funds: Optional[str] = None,
) -> pd.DataFrame:
    df = df_h.copy()
    if category:
        cats = [c.strip().upper() for c in category.split(",") if c.strip()]
        if cats:
            df = df[df["Category"].str.strip().str.upper().isin(cats)]
    if amc:
        amcs = [a.strip().upper() for a in amc.split(",") if a.strip()]
        if amcs:
            pattern = "|".join(amcs)
            df = df[df["AMC"].str.upper().str.contains(pattern, na=False)]
    if plan and plan != "All":
        df = df[df["Plan"].str.strip().str.upper() == plan.strip().upper()]
    if min_alloc > 0 and not df.empty:
        portfolio_total = float(df_h["Market Value"].sum())
        if portfolio_total > 0:
            df = df[(df["Market Value"] / portfolio_total * 100) >= min_alloc]
    
    if include_funds:
        flist = [f.strip().upper() for f in include_funds.split(",") if f.strip()]
        # Add back funds that were filtered out but are in include_funds
        missing = df_h[df_h["Fund"].str.upper().isin(flist)]
        df = pd.concat([df, missing]).drop_duplicates(subset=["Fund"])
        
    return df


# ── Threaded Per-Fund Computation Helper ──────────────────────────────
def _compute_fund_performance(row, df_t, risk_free_rate=6.5):
    """
    Isolated thread-safe computation for a single fund.
    Calculates XIRR, Alpha, Beta, Sharpe, max drawdowns, and rolling metrics.

    Note on the returned Dictionary Payload:
    The response includes an `is_absolute` boolean. If true, the frontend uses 
    it to render an 'ABS' UI badge and change tooltips, indicating that the 
    holding period is < 1 Year and SEBI-standard Absolute Return is applied 
    instead of Annualized XIRR.
    """
    fn          = str(row.get("Fund", ""))
    cur_val     = _safe_float(row.get("Market Value", 0))
    cat         = str(row.get("Category", "Equity"))
    cap_type    = str(row.get("Cap Type", ""))
    plan_r      = str(row.get("Plan", "Direct"))
    isin        = str(row.get("ISIN", row.get("Isin", "")))
    scheme_code = str(row.get("Scheme_Code", row.get("scheme_code", "")))

    fund_txns = df_t[df_t["Fund"] == fn] if not df_t.empty and "Fund" in df_t.columns else pd.DataFrame()
    
    fund_xi = compute_xirr(fund_txns, cur_val)
    bench_ticker_f, bench_display_f = get_fund_benchmark(cat, cap_type, fn)
    bench_series_f = fetch_benchmark_series(bench_ticker_f, 1825 + 30)
    bench_xi, _ = compute_benchmark_xirr(fund_txns, bench_series_f)

    nav_series = pd.Series(dtype=float)
    if isin and isin not in ("", "nan", "None"):
        nav_series = fetch_nav_series_by_isin(isin, days=3650)
    if nav_series.empty and scheme_code and scheme_code not in ("", "nan", "None"):
        nav_series = fetch_nav_series_by_code(scheme_code, days=3650)
    if nav_series.empty and fn:
        nav_series = fetch_nav_series_by_name(fn, days=3650)

    risk = compute_risk_metrics(nav_series, bench_series_f, risk_free_rate=risk_free_rate)
    trailing = compute_trailing_returns(nav_series)
    bench_trailing = compute_trailing_returns(bench_series_f)
    roll_labels = ["1M", "3M", "6M", "1Y", "3Y", "5Y"]
    
    er = None
    if scheme_code and scheme_code not in ("", "nan", "None"):
        er = fetch_fund_ter(scheme_code, plan_r)
        if er is None:
            logger.info(f"[TER] scheme_code={scheme_code} for '{fn[:30]}' returned None from AMFI TER file.")
    if er is None and isin and isin not in ("", "nan", "None"):
        resolved_code = resolve_scheme_code_from_isin(isin)
        if resolved_code:
            er = fetch_fund_ter(resolved_code, plan_r)
            if er is None:
                logger.info(f"[TER] ISIN-resolved scheme_code={resolved_code} for '{fn[:30]}' also returned None.")
        else:
            logger.info(f"[TER] Could not resolve ISIN={isin} to a scheme code for '{fn[:30]}'.")

    er_is_estimate = er is None
    if er is None:
        from shared.services.fallbacks.deterministic import DeterministicFallback
        fb = DeterministicFallback().generate_fallbacks(isin, cat, fn, {})
        er = fb.get("expense_ratio", 0.50)
        logger.info(f"[TER] Deterministic fallback={er:.2f}% used for '{fn[:30]}' ({cat}).")
    
    is_debt = any(kw in cat.lower() for kw in ["debt", "bond", "liquid", "gilt", "psu", "money", "banking", "credit"])
    pe_ratio = None if is_debt else PE_ESTIMATES.get(cap_type, PE_ESTIMATES.get(cat, PE_ESTIMATES["Default"]))
    pb_ratio = None if is_debt else PB_ESTIMATES.get(cap_type, PB_ESTIMATES.get(cat, PB_ESTIMATES["Default"]))

    dur_proxy, credit_proxy, ytm_proxy = None, None, None
    if is_debt:
        dur_val, credit_q, ytm_val = (3.0, "AA", 7.5)
        fn_u = fn.upper()
        if "BANKING" in fn_u or "PSU" in fn_u: dur_val, credit_q, ytm_val = DEBT_METRICS_MAP["Banking & PSU"]
        else:
            for k, v in sorted(DEBT_METRICS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
                if k.upper() in fn_u: dur_val, credit_q, ytm_val = v; break
        if cat in DEBT_METRICS_MAP and cat != "Debt": dur_val, credit_q, ytm_val = DEBT_METRICS_MAP[cat]
        dur_proxy, credit_proxy, ytm_proxy = dur_val, credit_q, ytm_val

    consistency = compute_consistency_score(nav_series, bench_series_f)
    
    # FIX P0-3: The UI displays `Fund XIRR` (transaction-based) next to `Alpha`.
    # Therefore, Alpha MUST be `fund_xi - bench_xi` to maintain mathematical consistency.
    # Passing the 3-Year point-to-point Alpha from `risk["alpha"]` creates an illusion
    # of broken math when the user tries to reverse-engineer the Benchmark XIRR.
    simple_alpha = fund_xi - bench_xi
    alpha_to_use = simple_alpha

    # ── Weighted Fund Health Score (0-10) ─────────────────────────────
    # Mirrors how Morningstar/Zerodha Coin compute composite quality:
    #   Alpha contribution (30%), Sharpe (25%), Consistency (25%), Stability (20%)
    alpha_score = min(10, max(0, (alpha_to_use + 5) * 1.0))     # -5% → 0, +5% → 10
    sharpe_score = min(10, max(0, risk["sharpe"] * 5.0))          # 0 → 0, 2.0 → 10
    consist_score = consistency                                    # Already 0-10
    stability_score = min(10, max(0, 10 - risk["vol"] * 0.3))    # 33% vol → 0, 0% vol → 10
    fund_score = round(
        alpha_score * 0.30 + sharpe_score * 0.25 + consist_score * 0.25 + stability_score * 0.20,
    1)

    # ── Verdict with clear human-readable reasoning ───────────────────
    verdict_reasons = []
    if is_debt:
        if simple_alpha >= 1.0 and consistency >= 6.0:
            verdict, action = "Strong", "Hold"
            verdict_reasons.append(f"Outperforming bond benchmark by {simple_alpha:.1f}%")
            verdict_reasons.append(f"Consistency {consistency:.0f}/10 — reliable compounder")
        elif simple_alpha < -1.5 or consistency < 3.5:
            verdict, action = "Weak", "Review"
            if simple_alpha < -1.5: verdict_reasons.append(f"Underperforming benchmark by {abs(simple_alpha):.1f}%")
            if consistency < 3.5: verdict_reasons.append(f"Low consistency ({consistency:.0f}/10) — erratic returns")
        else:
            verdict, action = "Average", "Monitor"
            verdict_reasons.append("Performing in line with bond benchmark")
    else:
        if (alpha_to_use >= 1.5 and risk["sharpe"] >= 0.5 and consistency >= 6.0) or alpha_to_use >= 3.0:
            verdict, action = "Strong", "Hold"
            if alpha_to_use >= 3.0: verdict_reasons.append(f"Exceptional alpha of +{alpha_to_use:.1f}% over benchmark")
            if risk["sharpe"] >= 0.5: verdict_reasons.append(f"Sharpe {risk['sharpe']:.2f} — good risk-adjusted return")
            if consistency >= 6.0: verdict_reasons.append(f"Beat benchmark in {consistency:.0f}/10 rolling windows")
        elif alpha_to_use < -2.0 or (alpha_to_use < 0 and consistency < 4.0 and not nav_series.empty):
            verdict, action = "Weak", "Review"
            if alpha_to_use < -2.0: verdict_reasons.append(f"Lagging benchmark by {abs(alpha_to_use):.1f}% — consider switching")
            if consistency < 4.0: verdict_reasons.append(f"Only beat benchmark in {consistency:.0f}/10 periods")
            verdict_reasons.append("An index fund may deliver better results")
        else:
            verdict, action = "Average", "Monitor"
            if alpha_to_use >= 0: verdict_reasons.append(f"Slightly ahead of benchmark by {alpha_to_use:.1f}%")
            else: verdict_reasons.append(f"Trailing benchmark by {abs(alpha_to_use):.1f}%")
            verdict_reasons.append("Watch for 1-2 more quarters before deciding")

    verdict_reason = " · ".join(verdict_reasons[:2])

    return {
        "fund": fn, "category": cat, "cap_type": cap_type, "plan": plan_r, "isin": isin,
        "color": CATEGORY_COLORS.get(cat, "#94A3B8"), "verdict": verdict, "action": action,
        "verdict_reason": verdict_reason, "fund_score": fund_score,
        "bench_display": bench_display_f, "bench_ticker": bench_ticker_f,
        "fund_xi": round(fund_xi, 2), "bench_xi": round(bench_xi, 2), "alpha": round(alpha_to_use, 2),
        "cur_value": round(cur_val, 0), "vol": round(risk["vol"], 2), "beta": round(risk["beta"], 2),
        "sharpe": round(risk["sharpe"], 2), "sortino": round(risk["sortino"], 2), "max_dd": round(abs(risk["max_dd"]), 2),
        "jensen_alpha": round(risk["alpha"], 2), "risk_label": risk["risk_label"],
        "info_ratio": risk["info_ratio"], "tracking_error": risk["tracking_error"],
        "up_capture": risk["up_capture"], "down_capture": risk["down_capture"],
        "calmar": risk["calmar"], "treynor": risk["treynor"],
        "er": round(er, 2), "er_label": classify_er(er, cat), "er_display": f"{er:.2f}% {'(est.)' if er_is_estimate else ''}",
        "roll_labels": roll_labels, "fund_rolls": [trailing.get(p) for p in roll_labels],
        "bench_rolls": [bench_trailing.get(p) for p in roll_labels],
        "consistency": round(consistency, 1), "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "is_debt": is_debt,
        "ytm_proxy": ytm_proxy, "modified_duration": dur_proxy, "credit_quality": credit_proxy,
        "nav_days": risk.get("data_days", 0), "has_nav_data": not nav_series.empty,
        "return_period": round(fund_xi, 2),
        "ret_3y": trailing.get("3Y"),
        "is_absolute": is_absolute_return(fund_txns),
    }


def _get_benchmark_day_chg(ticker: str, bench_data: pd.Series) -> float:
    """
    Day-over-day % change for the selected benchmark. Cached — this was
    previously an uncached yf.Ticker(...).fast_info call on every single
    /performance request, which is slow and rate-limit-prone under load.
    """
    cache_key = f"bench_day_chg_{ticker}"
    cached = MarketCache.get(cache_key)
    if cached is not None:
        return cached

    if ticker.startswith("^") or ".NS" in ticker:
        import yfinance as yf  # lazy: heavy import, only the index path needs it

        fast_info = yf.Ticker(ticker).fast_info
        last = getattr(fast_info, "last_price", 0)
        prev = getattr(fast_info, "previous_close", 1)
        value = round(((last / prev) - 1) * 100, 2) if prev else 0.0
    else:
        value = round((bench_data.iloc[-1] / bench_data.iloc[-2] - 1) * 100, 2) if len(bench_data) >= 2 else 0.0

    MarketCache.set(cache_key, value)
    return value


# ---------------------------------------------------------------------------
# Main Performance Endpoint
# ---------------------------------------------------------------------------

@router.get("/{session_id}/performance")
def get_performance(
    session_id: str,
    period:     str   = "1Y",
    benchmark:  str   = "Nifty 50",
    category:   str   = "",
    amc:        str   = "",
    plan:       str   = "All",
    min_alloc:  float = 0.0,
    include_funds: Optional[str] = None,
):
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t

    df_h = _apply_filters(df_h, category, amc, plan, min_alloc, include_funds)
    if df_h.empty:
        return {
            "portfolio_return": 0.0, "benchmark_return": 0.0, "alpha": 0.0,
            "n_strong": 0, "n_average": 0, "n_weak": 0, "funds": [],
            "dates": [], "portfolio": [], "benchmark": [],
            "portfolio_vals": [], "benchmark_vals": [],
            "benchmark_label": benchmark, "period": period
        }

    perf_days   = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 1095, "5Y": 1825, "All Time": 9999}.get(period, 365)
    ticker      = BENCHMARKS.get(benchmark, benchmark)
    bench_data  = fetch_benchmark_series(ticker, max(perf_days + 30, 365))
    total_value = float(df_h["Market Value"].sum())

    # FIX #F-11: Full simulation using exact transaction history
    comp = cached_period_comparison(df_t, portfolio.df_h, total_value, bench_data, perf_days)

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_compute_fund_performance, row, df_t) for _, row in df_h.iterrows()]
        for f in futures:
            try: results.append(f.result())
            except Exception as e: logger.error(f"[PERF ERROR] {e}")

    # Calculate benchmark metrics (relative to itself for base stats)
    bench_risk = compute_risk_metrics(bench_data, bench_data)
    bench_trailing = compute_trailing_returns(bench_data)

    # Compute portfolio-level health score (value-weighted avg of fund scores)
    total_val = sum(r.get("cur_value", 0) for r in results) or 1
    portfolio_score = round(
        sum(r.get("fund_score", 5.0) * r.get("cur_value", 0) for r in results) / total_val,
    1)
    # Value-weighted portfolio beta (real, not the old hardcoded ~0.94 the UI used to show)
    portfolio_beta = round(
        sum(r.get("beta", 1.0) * r.get("cur_value", 0) for r in results) / total_val,
    2)

    # Calculate exact portfolio and benchmark XIRR to perfectly match Overview tab
    # FIX: XIRR requires full transaction history, not period-limited benchmark data.
    # The bench_data above is sliced for chart rendering, but XIRR needs all-time data.
    from domains.mutual_funds.finance import compute_xirr, compute_benchmark_xirr
    port_xirr_val = compute_xirr(df_t, portfolio.total_value)
    bench_full = fetch_benchmark_series(ticker, 9999)  # Full history for XIRR
    bench_xirr_val, _ = compute_benchmark_xirr(df_t, bench_full)

    return {
        "portfolio_return": round(port_xirr_val, 2),
        "is_absolute":      is_absolute_return(df_t),
        "benchmark_return": round(bench_xirr_val, 2),
        "alpha":            round(port_xirr_val - bench_xirr_val, 2),
        "dates":            comp.get("dates", []),
        "portfolio":        comp.get("portfolio", []),
        "benchmark":        comp.get("benchmark", []),
        "portfolio_vals":   comp.get("portfolio", []),
        "benchmark_vals":   comp.get("benchmark", []),
        "benchmark_label":  benchmark,
        "period":           period,
        "portfolio_score":  portfolio_score,
        "portfolio_beta":   portfolio_beta,
        "benchmark_price_index_blend": benchmark_uses_price_index_blend(ticker, perf_days),
        "n_strong":  sum(1 for r in results if r["verdict"] == "Strong"),
        "n_average": sum(1 for r in results if r["verdict"] == "Average"),
        "n_weak":    sum(1 for r in results if r["verdict"] == "Weak"),
        "funds":     results,
        "benchmark_day_chg": _get_benchmark_day_chg(ticker, bench_data),
        "benchmark_stats": {
            "alpha": 0.0,
            "beta": 1.0,
            "sharpe": round(bench_risk.get("sharpe", 0), 2),
            "sortino": round(bench_risk.get("sortino", 0), 2),
            "volatility": round(bench_risk.get("vol", 0), 2),
            "max_drawdown": round(bench_risk.get("max_dd", 0), 2),
            "returns": bench_trailing
        }
    }


@router.get("/{session_id}/rolling/{fund_isin}")
def rolling_returns_detail(session_id: str, fund_isin: str, window: int = 3):
    # Sync `def` on purpose: get_session() does SQLite reads plus a live-NAV refresh
    # on a cache miss, and fetch_benchmark_series() can go to the network. Under
    # `async def` all of that ran on the single worker's event loop and blocked every
    # other request, including /health.
    s    = get_session(session_id)
    df_h = s.df_h
    
    from domains.mutual_funds.tab_common import series_to_list

    fund_row = pd.DataFrame()
    if "ISIN" in df_h.columns:
        fund_row = df_h[df_h["ISIN"].str.upper() == fund_isin.upper()]
    if fund_row.empty and "Fund" in df_h.columns:
        fund_row = df_h[df_h["Fund"].str.upper() == fund_isin.upper()]

    if fund_row.empty:
        # Check if fund_isin is an external benchmark like ^NSEI
        bench_s = fetch_benchmark_series(fund_isin, 9999)
        if not bench_s.empty:
            bench_roll = compute_rolling_return_series(bench_s, window)
            return {"fund_series": [], "bench_series": series_to_list(bench_roll), "window_years": window}
        return {"fund_series": [], "bench_series": [], "window_years": window}

    row         = fund_row.iloc[0]
    cat         = str(row.get("Category", "Equity"))
    cap_type    = str(row.get("Cap Type", ""))
    fn          = str(row.get("Fund", ""))
    isin        = str(row.get("ISIN", row.get("Isin", "")))
    scheme_code = str(row.get("Scheme_Code", row.get("scheme_code", "")))

    nav_series = pd.Series(dtype=float)
    if isin and isin not in ("", "nan", "None"):
        nav_series = fetch_nav_series_by_isin(isin, days=9999)
    if nav_series.empty and scheme_code and scheme_code not in ("", "nan", "None"):
        nav_series = fetch_nav_series_by_code(scheme_code, days=9999)
    if nav_series.empty and fn:
        nav_series = fetch_benchmark_series(fn, days=9999)

    bench_ticker, bench_display = get_fund_benchmark(cat, cap_type, fn)
    bench_series = fetch_benchmark_series(bench_ticker, 9999)

    # One traversal per series instead of two: compute_rolling_returns() returns the
    # average and the chart series from the same walk (the _avg/_series helpers each
    # re-did the whole resample + window scan).
    fund_avg,  fund_roll_series  = compute_rolling_returns(nav_series, window)
    bench_avg, bench_roll_series = compute_rolling_returns(bench_series, window)

    return {
        "fund_isin":      fund_isin,
        "fund_name":      fn,
        "bench_display":  bench_display,
        "window_years":   window,
        "fund_series":    series_to_list(fund_roll_series),
        "bench_series":   series_to_list(bench_roll_series),
        "fund_avg":       fund_avg,
        "bench_avg":      bench_avg,
    }

# ---------------------------------------------------------------------------
# Feature 1: Portfolio Drawdown Chart
# ---------------------------------------------------------------------------
@router.get("/{session_id}/drawdown")
def get_portfolio_drawdown(session_id: str, period: str = "All Time"):
    """
    Computes the portfolio's underwater curve (drawdown from historical peaks)
    to help visualize historical pain periods.
    """
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    total_value = float(df_h["Market Value"].sum())
    
    if df_h.empty or total_value <= 0:
        return {"dates": [], "drawdowns": [], "max_drawdown": 0}

    perf_days = {"1Y": 365, "3Y": 1095, "5Y": 1825, "All Time": 9999}.get(period, 1825)
    
    # We use Nifty 50 just to get a common market trading calendar, 
    # since compute_period_comparison evaluates on the benchmark's index
    nifty = fetch_benchmark_series("^NSEI", perf_days + 30)
    
    comp = cached_period_comparison(df_t, df_h, total_value, nifty, perf_days)
    dates = comp.get("dates", [])
    port_vals = comp.get("portfolio", [])  # FIX: The key is "portfolio", not "port_vals"
    
    if not dates or not port_vals:
        return {"dates": [], "drawdowns": [], "max_drawdown": 0}
        
    # Compute running peak and drawdown
    running_peak = port_vals[0]
    drawdowns = []
    
    for val in port_vals:
        if val > running_peak:
            running_peak = val
            
        if running_peak > 0:
            dd = (val - running_peak) / running_peak * 100
        else:
            dd = 0
            
        drawdowns.append(round(dd, 2))
        
    return {
        "dates": dates,
        "drawdowns": drawdowns,
        "max_drawdown": round(min(drawdowns) if drawdowns else 0, 2)
    }

# ---------------------------------------------------------------------------
# Feature 2: SIP Performance Attribution
# ---------------------------------------------------------------------------
@router.get("/{session_id}/sip_performance")
def get_sip_performance(session_id: str):
    """
    Isolates the performance of SIP transactions (excluding lumpsums)
    to answer "What is the return of just my SIPs?"
    """
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    
    if df_h.empty or df_t.empty:
        return {"sip_funds": [], "total_sip_invested": 0, "total_sip_value": 0, "sip_xirr": 0}

    # Filter only SIPs
    # The Type enum from casparser is like 'TransactionType.PURCHASE_SIP'
    sip_txns = df_t[df_t["Type"].astype(str).str.upper().str.contains("SIP", na=False)]
    if sip_txns.empty:
        return {"sip_funds": [], "total_sip_invested": 0, "total_sip_value": 0, "sip_xirr": 0}
    
    # V8-1 FIX: Only consider SIPs for funds STILL in the current portfolio.
    # Redeemed fund SIPs have no terminal value, causing XIRR to collapse to -64%.
    current_fund_names = set(df_h["Fund"].tolist())
    sip_txns = sip_txns[sip_txns["Fund"].isin(current_fund_names)]
    if sip_txns.empty:
        return {"sip_funds": [], "total_sip_invested": 0, "total_sip_value": 0, "sip_xirr": 0}
        
    results = []
    total_sip_invested = 0
    total_sip_value = 0
    
    from domains.mutual_funds.finance import compute_xirr
    
    for fn in sip_txns["Fund"].unique():
        f_sips = sip_txns[sip_txns["Fund"] == fn]
        
        # Get current NAV for the fund
        fund_row = df_h[df_h["Fund"] == fn]
        if fund_row.empty:
            continue
            
        nav = float(fund_row.iloc[0].get("NAV", 0))
        if nav <= 0:
            continue
            
        # Total units accumulated purely via SIP. 
        # Fallback to Amount / NAV if casparser missed the units column.
        def get_tx_units(r):
            u = float(r.get("Units", 0))
            if u > 0: return u
            a = abs(float(r.get("Amount", 0)))
            n = float(r.get("NAV", 0))
            return (a / n) if n > 0 else 0.0
            
        sip_units = float(f_sips.apply(get_tx_units, axis=1).sum())
        
        if sip_units <= 0:
            continue
            
        sip_invested = float(abs(f_sips["Amount"]).sum())
        sip_current_value = sip_units * nav
        
        # SIP specific XIRR
        sip_xi = compute_xirr(f_sips, sip_current_value)
        
        total_sip_invested += sip_invested
        total_sip_value += sip_current_value
        
        results.append({
            "fund": fn,
            "category": str(fund_row.iloc[0].get("Category", "Equity")),
            "color": CATEGORY_COLORS.get(str(fund_row.iloc[0].get("Category", "Equity")), "#94A3B8"),
            "sip_units": round(sip_units, 2),
            "sip_invested": round(sip_invested, 2),
            "sip_current_value": round(sip_current_value, 2),
            "sip_gain": round(sip_current_value - sip_invested, 2),
            "sip_xirr": round(sip_xi, 2),
            "sip_count": len(f_sips)
        })
        
    # Aggregate SIP XIRR
    overall_sip_xirr = compute_xirr(sip_txns, total_sip_value)
    
    # Sort by value
    results = sorted(results, key=lambda x: x["sip_current_value"], reverse=True)
    
    return {
        "sip_funds": results,
        "total_sip_invested": round(total_sip_invested, 2),
        "total_sip_value": round(total_sip_value, 2),
        "total_sip_gain": round(total_sip_value - total_sip_invested, 2),
        "sip_xirr": round(overall_sip_xirr, 2)
    }
