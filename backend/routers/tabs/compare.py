"""
routers/tabs/compare.py

Institutional Peer Comparison & Alpha Scoring Matrix
====================================================
Synthesizes real-time dynamic mutual fund peer universes. Conducts multi-point comparative
audits across expense ratio drag, 1Y/3Y/5Y trailing CAGRs, risk-adjusted returns (Sharpe/Sortino),
and head-to-head consistency scoring for institutional peer selection.
"""

from fastapi import APIRouter
from core.config import (
    BENCHMARKS, PE_ESTIMATES, GOAL_TIMELINE, EXP_RATIO_BANDS,
    FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT
)
from services.market_indices import fetch_benchmark_series
from services.market_data import (
    search_mutual_funds, get_nse_indices, fetch_fund_ter, fetch_nav_series_by_code
)
from core.finance import (
    compute_consistency_score, compute_risk_metrics, compute_trailing_returns
)
import pandas as pd

router = APIRouter()

@router.get("/list")
def list_benchmarks():
    return {"benchmarks": list(BENCHMARKS.keys())}

@router.get("/search")
def search_ticker(q: str):
    print(f"[REALTIME] Searching for: {q}")
    results = get_nse_indices(q) + search_mutual_funds(q)
    return {"results": results, "peers": results}

@router.get("/history")
def get_history(ticker: str, days: int = 365):
    series = fetch_benchmark_series(ticker, days)
    if series.empty:
        return {"dates": [], "values": []}
    
    norm = (series / series.iloc[0] * 100).round(2)
    return {
        "dates": series.index.strftime("%Y-%m-%d").tolist(),
        "values": norm.tolist(),
        "raw": series.round(2).tolist(),
    }

@router.get("/peers")
def get_category_peers(category: str = "Large Cap"):
    """Fetch 100% dynamic live category peers via real-time market search."""
    clean_cat = category.replace("Fund", "").strip()
    dynamic_matches = search_mutual_funds(f"{clean_cat} Direct")
    dynamic_matches.extend(search_mutual_funds(f"{clean_cat} Growth"))
    if " " in clean_cat:
        short_cat = clean_cat.split()[0]
        dynamic_matches.extend(search_mutual_funds(f"{short_cat} Direct"))
        
    peers = []
    existing_codes = set()
    
    for item in dynamic_matches:
        code = str(item["symbol"])
        name = str(item["name"])
        if code not in existing_codes and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
            ter = fetch_fund_ter(code) or 0.65
            peers.append({
                "name": name,
                "code": code,
                "er": ter
            })
            existing_codes.add(code)
            if len(peers) >= 30:
                break
                
    if not peers:
        fallback = search_mutual_funds("Large Cap Fund")
        for item in fallback:
            code = str(item["symbol"])
            name = str(item["name"])
            if code not in existing_codes and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
                peers.append({"name": name, "code": code, "er": 0.65})
                existing_codes.add(code)
                if len(peers) >= 15:
                    break
    
    bench_ticker, _ = FUND_BENCH_BY_CAP.get(category, FUND_BENCH_BY_CAT.get(category, ("^CRSLDX", "Nifty 500 TRI")))
    bench_series = fetch_benchmark_series(bench_ticker, 1825 + 30)

    is_debt = any(kw in category.lower() for kw in ["debt", "bond", "liquid", "gilt", "psu", "money"])
    base_pe = None if is_debt else PE_ESTIMATES.get(category, PE_ESTIMATES["Default"])

    def _extract_amc(fund_name: str) -> str:
        name = fund_name.upper().strip()
        for compound in ["NIPPON INDIA", "ICICI PRUDENTIAL", "ADITYA BIRLA", "MIRAE ASSET", "FRANKLIN TEMPLETON", "MOTILAL OSWAL", "CANARA ROBECO", "TATA", "DSP", "SBI", "HDFC", "QUANT", "AXIS", "KOTAK", "BANDHAN", "UTI", "PPFAS", "PARAG PARIKH", "SUNDARAM", "EDELWEISS", "INVESCO", "HSBC", "PGIM", "BARODA BNP", "MAHINDRA", "LIC", "BANK OF INDIA"]:
            if name.startswith(compound):
                return compound
        return name.split()[0] if name.split() else "UNKNOWN"

    results = []
    for p in peers:
        try:
            code = str(p['code'])
            peer_nav = fetch_nav_series_by_code(code, days=1825 + 90)
            if peer_nav.empty:
                continue

            trailing = compute_trailing_returns(peer_nav)
            ret5y = trailing.get("5Y")
            if ret5y is None or ret5y == 0.0:
                print(f"[PEER FILTER] Skipping {p['name']} (insufficient 5Y history)")
                continue

            ret1y = trailing.get("1Y") or 0.0
            ret3y = trailing.get("3Y") or 0.0

            peer_consistency = compute_consistency_score(peer_nav, bench_series)
            risk = compute_risk_metrics(peer_nav, bench_series, risk_free_rate=6.5)
            
            fund_pe = base_pe
            
            alpha_v = round(risk.get('alpha', 0.0), 2)
            alpha_str = f"+{alpha_v}%" if alpha_v > 0 else f"{alpha_v}%"
            
            results.append({
                "name":    p["name"],
                "symbol":  code,
                "code":    code,
                "ret1y":   ret1y,
                "ret3y":   ret3y,
                "ret5y":   ret5y,
                "expense": p["er"],
                "consistency": f"{round(peer_consistency, 1)}/10",
                "alpha_num": alpha_v,
                "alpha": alpha_str,
                "sharpe": round(risk.get('sharpe', 0.0), 2),
                "pe_ratio": fund_pe if fund_pe else "N/A",
                "amc":     _extract_amc(p["name"]),
            })
        except Exception as e:
            print(f"[PEER ERROR] Skipping {p.get('name', code)}: {e}")
            
    # Sort descending by 1-Year trailing return initially
    results.sort(key=lambda x: float(x["ret1y"] or 0), reverse=True)
    
    # Filter for AMC diversity (one fund per AMC)
    diverse_peers = []
    seen_amcs = set()
    for r in results:
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
                if code not in existing_codes and amc not in seen_amcs and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
                    existing_codes.add(code)
                    nav_s = fetch_nav_series_by_code(code, days=1825 + 90)
                    if nav_s.empty: continue
                    tr = compute_trailing_returns(nav_s)
                    if tr.get("5Y"):
                        risk_m = compute_risk_metrics(nav_s, bench_series, risk_free_rate=6.5)
                        a_v = round(risk_m.get("alpha", 0.0), 2)
                        diverse_peers.append({
                            "name": name,
                            "symbol": code,
                            "code": code,
                            "ret1y": tr.get("1Y") or 0.0,
                            "ret3y": tr.get("3Y") or 0.0,
                            "ret5y": tr.get("5Y") or 0.0,
                            "expense": fetch_fund_ter(code) or 0.65,
                            "consistency": f"{round(compute_consistency_score(nav_s, bench_series), 1)}/10",
                            "alpha_num": a_v,
                            "alpha": f"+{a_v}%" if a_v > 0 else f"{a_v}%",
                            "sharpe": round(risk_m.get("sharpe", 0.0), 2),
                            "pe_ratio": base_pe if base_pe else "N/A",
                            "amc": amc
                        })
                        seen_amcs.add(amc)
                        if len(diverse_peers) >= 5: break

    return {"peers": diverse_peers[:5]}

@router.get("/metrics")
def get_comparison_metrics(fund: str, vs: str, session_id: str = ""):
    """
    Head-to-head metrics comparison between two funds/indices.
    Scoring: Fund A beats Fund B on specific metric = 1 Win.
    """
    from services.market_data import fetch_nav_series_by_code
    from services.market_indices import fetch_benchmark_series
    from core.finance import compute_trailing_returns, compute_risk_metrics, compute_consistency_score

    # Fetch Data
    # 'fund' is always a scheme code
    s1 = fetch_nav_series_by_code(fund, days=1825 + 60)
    
    # 'vs' could be ticker or scheme code
    if vs.isdigit() and len(vs) >= 5:
        s2 = fetch_nav_series_by_code(vs, days=1825 + 60)
    else:
        s2 = fetch_benchmark_series(vs, days=1825 + 60)

    if s1.empty or s2.empty:
        return {"wins": {"A": 0, "B": 0}, "metrics": []}

    # 1. Trailing Returns
    t1 = compute_trailing_returns(s1)
    t2 = compute_trailing_returns(s2)

    # 2. Risk Metrics (using s2 as benchmark for s1)
    r1 = compute_risk_metrics(s1, s2, risk_free_rate=6.5)
    # Also need r2 (standardized to Nifty 50 for comparison)
    nifty = fetch_benchmark_series("^NSEI", 1825 + 60)
    r2 = compute_risk_metrics(s2, nifty, risk_free_rate=6.5)

    # 3. Consistency
    c1 = compute_consistency_score(s1, s2)
    
    metrics = []
    wins_a = 0
    wins_b = 0

    def add_metric(label, v1, v2, higher_better=True):
        nonlocal wins_a, wins_b
        if v1 is None or v2 is None:
            winner = None
        else:
            if higher_better:
                winner = "A" if v1 > v2 else ("B" if v2 > v1 else "Tie")
            else:
                winner = "A" if v1 < v2 else ("B" if v2 < v1 else "Tie")
        
        if winner == "A": wins_a += 1
        elif winner == "B": wins_b += 1
        
        metrics.append({
            "label": label,
            "v1": v1,
            "v2": v2,
            "winner": winner
        })

    # Population
    add_metric("1Y Return (%)", t1.get("1Y"), t2.get("1Y"))
    add_metric("3Y Return (%)", t1.get("3Y"), t2.get("3Y"))
    add_metric("5Y Return (%)", t1.get("5Y"), t2.get("5Y"))
    add_metric("Sharpe Ratio", r1.get("sharpe"), r2.get("sharpe"))
    add_metric("Sortino Ratio", r1.get("sortino"), r2.get("sortino"))
    add_metric("Jensen's Alpha (%)", r1.get("alpha"), r2.get("alpha"))
    add_metric("Volatility (%)", r1.get("vol"), r2.get("vol"), higher_better=False)
    add_metric("Max Drawdown (%)", abs(r1.get("max_dd", 0)), abs(r2.get("max_dd", 0)), higher_better=False)
    add_metric("Consistency Score", c1, 5.0) # vs baseline of 5.0

    return {
        "wins": {"A": wins_a, "B": wins_b},
        "metrics": metrics
    }
