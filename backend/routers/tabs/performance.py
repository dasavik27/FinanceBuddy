"""
routers/tabs/performance.py

Enterprise Performance Audit & Risk Attribution Gateway
=======================================================
Orchestrates high-speed, multi-threaded quantitative risk modeling for individual holdings.
Calculates Jensen's Alpha, Sharpe & Sortino ratios, Maximum Drawdown, market capture ratios,
and full rolling return series for institutional performance benchmarking.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

from core.sessions import get_session
from core.config import (
    BENCHMARKS, CATEGORY_COLORS, RISK_LABEL,
    EXP_RATIO_BANDS, classify_er,
    PE_ESTIMATES, PB_ESTIMATES, DEBT_METRICS_MAP,
)
from core.finance import (
    compute_xirr,
    compute_benchmark_xirr,
    compute_period_comparison,
    compute_risk_metrics,
    compute_trailing_returns,
    compute_rolling_return_avg,
    compute_rolling_return_series,
    compute_consistency_score,
)
from services.market_indices import fetch_benchmark_series
from services.market_data import (
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
    """Isolated thread-safe computation for a single fund."""
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
            print(f"[TER] scheme_code={scheme_code} for '{fn[:30]}' returned None from AMFI TER file.")
    if er is None and isin and isin not in ("", "nan", "None"):
        resolved_code = resolve_scheme_code_from_isin(isin)
        if resolved_code:
            er = fetch_fund_ter(resolved_code, plan_r)
            if er is None:
                print(f"[TER] ISIN-resolved scheme_code={resolved_code} for '{fn[:30]}' also returned None.")
        else:
            print(f"[TER] Could not resolve ISIN={isin} to a scheme code for '{fn[:30]}'.")

    er_is_estimate = er is None
    if er is None:
        # Fallback: Use category band estimate
        lo, hi = EXP_RATIO_BANDS.get(cat, (0.50, 1.00))
        # FIX P2-1: Regular plan ER = direct ER + typical markup (~0.80%)
        er = lo if "direct" in plan_r.lower() else lo + 0.80
        print(f"[TER] Fallback band estimate={er:.2f}% used for '{fn[:30]}' ({cat}).")
    
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

    if is_debt:
        if simple_alpha >= 1.0 and consistency >= 6.0: verdict, action = "Strong", "Hold"
        elif simple_alpha < -1.5 or consistency < 3.5: verdict, action = "Weak", "Review"
        else: verdict, action = "Average", "Monitor"
    else:
        if (alpha_to_use >= 1.5 and risk["sharpe"] >= 0.5 and consistency >= 6.0) or alpha_to_use >= 3.0:
            verdict, action = "Strong", "Hold"
        elif alpha_to_use < -2.0 or (alpha_to_use < 0 and consistency < 4.0 and not nav_series.empty):
            verdict, action = "Weak", "Review"
        else:
            verdict, action = "Average", "Monitor"

    return {
        "fund": fn, "category": cat, "cap_type": cap_type, "plan": plan_r, "isin": isin,
        "color": CATEGORY_COLORS.get(cat, "#94A3B8"), "verdict": verdict, "action": action,
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
    }


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
    comp = compute_period_comparison(df_t, portfolio.df_h, total_value, bench_data, perf_days)

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_compute_fund_performance, row, df_t) for _, row in df_h.iterrows()]
        for f in futures:
            try: results.append(f.result())
            except Exception as e: print(f"[PERF ERROR] {e}")

    # Calculate benchmark metrics (relative to itself for base stats)
    bench_risk = compute_risk_metrics(bench_data, bench_data)
    bench_trailing = compute_trailing_returns(bench_data)

    return {
        "portfolio_return": round(comp.get("port_pct", 0), 2),
        "benchmark_return": round(comp.get("bench_pct", 0), 2),
        "alpha":            round(comp.get("alpha", 0), 2),
        "dates":            comp.get("dates", []),
        "portfolio":        comp.get("portfolio", []),
        "benchmark":        comp.get("benchmark", []),
        "portfolio_vals":   comp.get("portfolio", []),
        "benchmark_vals":   comp.get("benchmark", []),
        "benchmark_label":  benchmark,
        "period":           period,
        "n_strong":  sum(1 for r in results if r["verdict"] == "Strong"),
        "n_average": sum(1 for r in results if r["verdict"] == "Average"),
        "funds":     results,
        "benchmark_day_chg": (lambda t: (
            round(((getattr(yf.Ticker(t).fast_info, "last_price", 0) / getattr(yf.Ticker(t).fast_info, "previous_close", 1)) - 1) * 100, 2)
            if t.startswith("^") or ".NS" in t else 
            round((bench_data.iloc[-1] / bench_data.iloc[-2] - 1) * 100, 2) if len(bench_data) >= 2 else 0.0
        ))(ticker),
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


# ---------------------------------------------------------------------------
# Peer Comparison Endpoint
# ---------------------------------------------------------------------------

@router.get("/{session_id}/peer/{fund_name}")
async def peer_comparison(session_id: str, fund_name: str):
    s    = get_session(session_id)
    df_h = s.df_h
    fund_row = df_h[df_h["Fund"].str.contains(fund_name[:30], case=False, na=False)]
    if fund_row.empty:
        return {"peers": [], "fund_name": fund_name, "cat_rank": None}

    row      = fund_row.iloc[0]
    category = str(row.get("Category", "Equity"))
    cap_type = str(row.get("Cap Type", ""))
    isin     = str(row.get("ISIN", row.get("Isin", "")))

    fund_nav = fetch_nav_series_by_isin(isin, days=1825) if isin else pd.Series(dtype=float)
    fund_trailing = compute_trailing_returns(fund_nav)
    fund_1y = fund_trailing.get("1Y") or 0.0

    bench_ticker, bench_display = get_fund_benchmark(category, cap_type, fund_name)
    bench_series = fetch_benchmark_series(bench_ticker, 1825 + 30)
    bench_trailing = compute_trailing_returns(bench_series)

    clean_cat = (cap_type if cap_type and "cap" in cap_type.lower() else category).replace("Fund", "").strip()
    from services.market_data import search_mutual_funds
    live_matches = search_mutual_funds(f"{clean_cat} Direct")
    live_matches.extend(search_mutual_funds(f"{clean_cat} Growth"))
    if " " in clean_cat:
        short_cat = clean_cat.split()[0]
        live_matches.extend(search_mutual_funds(f"{short_cat} Direct"))
        
    peers = []
    seen = set()
    for item in live_matches:
        code = str(item["symbol"])
        name = str(item["name"])
        if code not in seen and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
            ter = fetch_fund_ter(code) or 0.65
            peers.append({"name": name, "code": code, "er": ter})
            seen.add(code)
            if len(peers) >= 30:
                break

    def _extract_amc(fund_name: str) -> str:
        name = fund_name.upper().strip()
        for compound in ["NIPPON INDIA", "ICICI PRUDENTIAL", "ADITYA BIRLA", "MIRAE ASSET", "FRANKLIN TEMPLETON", "MOTILAL OSWAL", "CANARA ROBECO", "TATA", "DSP", "SBI", "HDFC", "QUANT", "AXIS", "KOTAK", "BANDHAN", "UTI", "PPFAS", "PARAG PARIKH", "SUNDARAM", "EDELWEISS", "INVESCO", "HSBC", "PGIM", "BARODA BNP", "MAHINDRA", "LIC", "BANK OF INDIA"]:
            if name.startswith(compound):
                return compound
        return name.split()[0] if name.split() else "UNKNOWN"

    peer_results = []
    peer_1y_returns = []

    for peer in peers:
        code = str(peer["code"])
        if fund_name.lower()[:20] in str(peer["name"]).lower():
            continue

        er = float(peer.get("er", 0.0))
        peer_nav = fetch_nav_series_by_code(code, days=1825 + 90)
        if peer_nav.empty:
            continue

        peer_trailing = compute_trailing_returns(peer_nav)
        ret5y = peer_trailing.get("5Y")
        if ret5y is None or ret5y == 0.0:
            print(f"[PEER FILTER] Skipping {peer['name']} (insufficient 5Y history)")
            continue

        peer_consistency = compute_consistency_score(peer_nav, bench_series)
        risk = compute_risk_metrics(peer_nav, bench_series, risk_free_rate=6.5)

        peer_results.append({
            "name":           peer["name"],
            "code":           code,
            "er":             er,
            "er_label":       classify_er(er, category),
            "returns":        peer_trailing,
            "consistency":    round(peer_consistency, 1),
            "category":       category,
            "alpha":          round(risk.get("alpha", 0.0), 2),
            "sharpe":         round(risk.get("sharpe", 0.0), 2),
            "amc":            _extract_amc(peer["name"]),
        })
        if peer_trailing.get("1Y"):
            peer_1y_returns.append(peer_trailing.get("1Y"))

    cat_rank, cat_total = None, None
    if fund_1y and peer_1y_returns:
        all_returns  = sorted(peer_1y_returns + [fund_1y], reverse=True)
        cat_rank     = all_returns.index(fund_1y) + 1
        cat_total    = len(all_returns)

    peer_results.sort(key=lambda x: (x["returns"].get("1Y") or 0.0), reverse=True)
    diverse_peers = []
    seen_amcs = set()
    for r in peer_results:
        if r["amc"] not in seen_amcs:
            diverse_peers.append(r)
            seen_amcs.add(r["amc"])
        if len(diverse_peers) >= 5:
            break

    if len(diverse_peers) < 5:
        print(f"[PEER HARVEST] Category {category} only yielded {len(diverse_peers)} diverse 5Y peers. Harvesting backup veterans...")
        backup_queries = ["Flexi Cap Direct", "Large Cap Direct", "Multi Cap Direct", "Value Fund Direct", "Index Fund Direct"]
        for bq in backup_queries:
            if len(diverse_peers) >= 5: break
            b_matches = search_mutual_funds(bq)
            for bm in b_matches:
                code = str(bm["symbol"])
                name = str(bm["name"])
                amc = _extract_amc(name)
                if code not in seen and amc not in seen_amcs and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
                    seen.add(code)
                    nav_s = fetch_nav_series_by_code(code, days=1825 + 90)
                    if nav_s.empty: continue
                    tr = compute_trailing_returns(nav_s)
                    if tr.get("5Y"):
                        risk_m = compute_risk_metrics(nav_s, bench_series, risk_free_rate=6.5)
                        er_val = fetch_fund_ter(code) or 0.65
                        diverse_peers.append({
                            "name":           name,
                            "code":           code,
                            "er":             er_val,
                            "er_label":       classify_er(er_val, category),
                            "returns":        tr,
                            "consistency":    round(compute_consistency_score(nav_s, bench_series), 1),
                            "category":       category,
                            "alpha":          round(risk_m.get("alpha", 0.0), 2),
                            "sharpe":         round(risk_m.get("sharpe", 0.0), 2),
                            "amc":            amc,
                        })
                        seen_amcs.add(amc)
                        if len(diverse_peers) >= 5: break

    return {
        "fund_name":       fund_name,
        "category":        category,
        "bench_display":   bench_display,
        "fund_trailing":   fund_trailing,
        "bench_trailing":  bench_trailing,
        "cat_rank":        cat_rank,
        "cat_total":       cat_total,
        "peers":           diverse_peers[:5],
    }


@router.get("/{session_id}/rolling/{fund_isin}")
async def rolling_returns_detail(session_id: str, fund_isin: str, window: int = 3):
    s    = get_session(session_id)
    df_h = s.df_h
    
    def series_to_list(ser: pd.Series) -> list:
        return [{"date": str(idx.date()), "value": float(val)} for idx, val in ser.items() if not np.isnan(val)]

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

    fund_roll_series  = compute_rolling_return_series(nav_series, window)
    bench_roll_series = compute_rolling_return_series(bench_series, window)

    return {
        "fund_isin":      fund_isin,
        "fund_name":      fn,
        "bench_display":  bench_display,
        "window_years":   window,
        "fund_series":    series_to_list(fund_roll_series),
        "bench_series":   series_to_list(bench_roll_series),
        "fund_avg":       compute_rolling_return_avg(nav_series, window),
        "bench_avg":      compute_rolling_return_avg(bench_series, window),
    }
