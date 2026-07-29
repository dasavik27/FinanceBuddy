"""
backend/core/tab_common.py

Centralized Shared Logic for Analytical Tabs
============================================
Contains reusable business logic for extracting AMCs, generating peer universes,
and formatting standard metrics to enforce DRY principles across Tab Routers.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

import pandas as pd

from shared.config import PE_ESTIMATES, FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT
from shared.services.cache import MARKET_CACHE, ttl_for
from shared.services.market_data import search_mutual_funds, fetch_fund_ter, fetch_nav_series_by_code
from shared.services.market_indices import fetch_benchmark_series
from domains.mutual_funds.finance import compute_trailing_returns, compute_consistency_score, compute_risk_metrics

logger = logging.getLogger(__name__)

# Trailing window requested for each peer's NAV history.
_PEER_NAV_DAYS = 1825 + 90

# Concurrency for peer NAV fetches. These are network-bound, so threads help even on a
# shared vCPU - the GIL is released during the HTTP wait. Capped because the upstream
# provider is a free public API and we should not hammer it.
_PEER_FETCH_WORKERS = 8


def _extract_amc(fund_name: str) -> str:
    from domains.mutual_funds.logic import CategorizationEngine
    return CategorizationEngine.extract_amc_brand(fund_name)


def _prefetch_peer_navs(codes: List[str]) -> Dict[str, pd.Series]:
    """
    Fetch several peers' NAV histories concurrently.

    This replaces up to 30 *sequential* HTTP round-trips, which was the single largest
    remaining source of wall-clock latency in the domain. The caller still iterates
    peers in the original order afterwards, so result ordering and tie-breaking are
    unchanged - only the waiting is overlapped.
    """
    navs: Dict[str, pd.Series] = {}
    unique = list(dict.fromkeys(codes))  # de-dupe, preserve order
    if not unique:
        return navs

    with ThreadPoolExecutor(max_workers=min(_PEER_FETCH_WORKERS, len(unique))) as executor:
        futures = {
            executor.submit(fetch_nav_series_by_code, code, _PEER_NAV_DAYS): code
            for code in unique
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                navs[code] = future.result()
            except Exception as e:
                logger.error(f"[PEER NAV] fetch failed for {code}: {e}")
                navs[code] = pd.Series(dtype=float)

    return navs


def get_diverse_category_peers(category: str, base_fund_name: str = "", max_peers: int = 5) -> Tuple[List[Dict], bool]:
    """
    Fetches dynamic live category peers via real-time market search.
    Computes trailing returns, alphas, sharpe, and filters for AMC diversity.
    Returns: (list_of_peers, fallback_triggered_boolean)

    Cached and single-flighted. The result is user-independent fund data (a category's
    peer set), so one entry is shared by every caller. Previously this ran in full on
    every /compare/peers request: up to eight uncached searches, thirty sequential NAV
    fetches, and thirty risk-metric computations.
    """
    ttl = ttl_for("comparison_data")
    key = f"peers|{category}|{base_fund_name}|{max_peers}"
    return MARKET_CACHE.get_or_compute(
        key,
        lambda: _compute_diverse_category_peers(category, base_fund_name, max_peers),
        ttl,
    )


def _compute_diverse_category_peers(category: str, base_fund_name: str, max_peers: int) -> Tuple[List[Dict], bool]:
    """Uncached implementation behind get_diverse_category_peers()."""
    clean_cat = category.replace("Fund", "").strip()
    
    # 1. Broad Search
    dynamic_matches = search_mutual_funds(f"{clean_cat} Direct")
    dynamic_matches.extend(search_mutual_funds(f"{clean_cat} Growth"))
    if " " in clean_cat:
        short_cat = clean_cat.split()[0]
        dynamic_matches.extend(search_mutual_funds(f"{short_cat} Direct"))

    # 2. Extract Valid Tickers
    peers = []
    seen = set()
    fallback_triggered = False

    for item in dynamic_matches:
        code = str(item["symbol"])
        name = str(item["name"])
        if code not in seen and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
            ter = fetch_fund_ter(code) or 0.65
            peers.append({"name": name, "code": code, "er": ter})
            seen.add(code)
            if len(peers) >= 30:
                break
                
    if not peers:
        fallback_triggered = True
        fallback = search_mutual_funds("Large Cap Fund")
        for item in fallback:
            code = str(item["symbol"])
            name = str(item["name"])
            if code not in seen and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
                peers.append({"name": name, "code": code, "er": 0.65})
                seen.add(code)
                if len(peers) >= 15:
                    break

    # 3. Benchmark & PE Init
    bench_ticker, bench_display = FUND_BENCH_BY_CAP.get(category, FUND_BENCH_BY_CAT.get(category, ("^CRSLDX", "Nifty 500 TRI")))
    bench_series = fetch_benchmark_series(bench_ticker, 1825 + 30)
    is_debt = any(kw in category.lower() for kw in ["debt", "bond", "liquid", "gilt", "psu", "money"])
    base_pe = None if is_debt else PE_ESTIMATES.get(category, PE_ESTIMATES.get("Default", 22.5))

    # 4. Metric Computation
    #
    # NAV histories are fetched up front and concurrently; the loop below then works
    # from memory. Self-matches are excluded from the prefetch so we do not spend a
    # request on a fund we are about to skip.
    def _is_self(name: str) -> bool:
        return bool(base_fund_name) and base_fund_name.lower()[:20] in name.lower()

    peer_navs = _prefetch_peer_navs(
        [str(p["code"]) for p in peers if not _is_self(str(p["name"]))]
    )

    results = []
    for p in peers:
        code = str(p['code'])
        name = str(p['name'])

        # Prevent comparing fund to itself
        if _is_self(name):
            continue

        peer_nav = peer_navs.get(code)
        if peer_nav is None or peer_nav.empty:
            continue

        trailing = compute_trailing_returns(peer_nav)
        ret5y = trailing.get("5Y")
        if ret5y is None or ret5y == 0.0:
            continue

        ret1y = trailing.get("1Y") or 0.0
        ret3y = trailing.get("3Y") or 0.0
        
        peer_consistency = compute_consistency_score(peer_nav, bench_series)
        risk = compute_risk_metrics(peer_nav, bench_series, risk_free_rate=6.5)
        alpha_v = round(risk.get('alpha', 0.0), 2)
        
        results.append({
            "name": name,
            "symbol": code,
            "code": code,
            "er": p.get("er", 0.65),
            "expense": p.get("er", 0.65),  # Legacy fallback name
            "returns": trailing,           # Legacy payload
            "ret1y": ret1y,
            "ret3y": ret3y,
            "ret5y": ret5y,
            "consistency": round(peer_consistency, 1),
            "consistency_str": f"{round(peer_consistency, 1)}/10",
            "alpha": alpha_v,
            "alpha_str": f"+{alpha_v}%" if alpha_v > 0 else f"{alpha_v}%",
            "sharpe": round(risk.get('sharpe', 0.0), 2),
            "pe_ratio": base_pe if base_pe else "N/A",
            "amc": _extract_amc(name)
        })
        
    # 5. Sort by 1Y Trailing and Enforce Diversity
    results.sort(key=lambda x: x["ret1y"], reverse=True)
    
    diverse_peers = []
    seen_amcs = set()
    for r in results:
        if r["amc"] not in seen_amcs:
            diverse_peers.append(r)
            seen_amcs.add(r["amc"])
        if len(diverse_peers) >= max_peers:
            break
            
    # 6. Fallback Veteran Harvesting
    if len(diverse_peers) < max_peers:
        backup_queries = ["Flexi Cap Direct", "Large Cap Direct", "Multi Cap Direct", "Value Fund Direct", "Index Fund Direct"]
        for bq in backup_queries:
            if len(diverse_peers) >= max_peers: break
            b_matches = search_mutual_funds(bq)
            for bm in b_matches:
                code = str(bm["symbol"])
                name = str(bm["name"])
                amc = _extract_amc(name)
                
                if base_fund_name and base_fund_name.lower()[:20] in name.lower():
                    continue

                if code not in seen and amc not in seen_amcs and any(x in name.lower() for x in ["direct", "dir"]) and any(x in name.lower() for x in ["growth", "gr"]):
                    seen.add(code)
                    nav_s = fetch_nav_series_by_code(code, days=1825 + 90)
                    if nav_s.empty: continue
                    tr = compute_trailing_returns(nav_s)
                    
                    if tr.get("5Y"):
                        risk_m = compute_risk_metrics(nav_s, bench_series, risk_free_rate=6.5)
                        a_v = round(risk_m.get("alpha", 0.0), 2)
                        ter_val = fetch_fund_ter(code) or 0.65
                        # Computed once: this was previously called twice with identical
                        # arguments, once for the number and once for the display string.
                        b_consistency = round(compute_consistency_score(nav_s, bench_series), 1)

                        diverse_peers.append({
                            "name": name,
                            "symbol": code,
                            "code": code,
                            "er": ter_val,
                            "expense": ter_val,
                            "returns": tr,
                            "ret1y": tr.get("1Y") or 0.0,
                            "ret3y": tr.get("3Y") or 0.0,
                            "ret5y": tr.get("5Y") or 0.0,
                            "consistency": b_consistency,
                            "consistency_str": f"{b_consistency}/10",
                            "alpha": a_v,
                            "alpha_str": f"+{a_v}%" if a_v > 0 else f"{a_v}%",
                            "sharpe": round(risk_m.get('sharpe', 0.0), 2),
                            "pe_ratio": base_pe if base_pe else "N/A",
                            "amc": amc
                        })
                        seen_amcs.add(amc)
                        if len(diverse_peers) >= max_peers: break

    return diverse_peers, fallback_triggered


# ── Extracted Router Helpers ──

def compare_metric(label: str, v1: float, v2: float, higher_better: bool = True) -> dict:
    if v1 is None or v2 is None:
        winner = None
    else:
        if higher_better:
            winner = "A" if v1 > v2 else ("B" if v2 > v1 else "Tie")
        else:
            winner = "A" if v1 < v2 else ("B" if v2 < v1 else "Tie")
    return {"label": label, "v1": v1, "v2": v2, "winner": winner}

def series_to_list(ser) -> list:
    import numpy as np
    return [{"date": str(idx.date()), "value": float(val)} for idx, val in ser.items() if not np.isnan(val)]

def get_goal_value(df_h, c: str) -> float:
    from shared.config import get_standard_category
    if c == "ELSS": return float(df_h[df_h["Category"] == "ELSS"]["Market Value"].sum())
    if c == "Liquid": 
        mask = (df_h["Category"].str.contains("Liquid", case=False, na=False)) | (df_h["Fund"].str.upper().str.contains("LIQUID", na=False))
        return float(df_h[mask]["Market Value"].sum())
    if c == "Index": return float(df_h[df_h["Category"].str.contains("Index", case=False, na=False)]["Market Value"].sum())
    if c in ["Mid Cap", "Small Cap"] and "Cap Type" in df_h.columns:
        return float(df_h[df_h["Cap Type"] == c]["Market Value"].sum())
    if c == "Debt":
        mask = df_h["Category"].apply(get_standard_category) == "Debt"
        liq_mask = (df_h["Category"].str.contains("Liquid", case=False, na=False)) | (df_h["Fund"].str.upper().str.contains("LIQUID", na=False))
        mask = mask & ~liq_mask
        return float(df_h[mask]["Market Value"].sum())
    if c == "Equity":
        mask = df_h["Category"].apply(get_standard_category) == "Equity"
        mask = mask & (df_h["Category"] != "ELSS")
        mask = mask & ~df_h["Category"].str.contains("Index", case=False, na=False)
        if "Cap Type" in df_h.columns:
            mask = mask & ~df_h["Cap Type"].isin(["Mid Cap", "Small Cap"])
        return float(df_h[mask]["Market Value"].sum())
    return 0.0

def rebalance_roll_up(cat: str) -> str:
    from shared.config import get_standard_category
    c = get_standard_category(cat)
    if c in ["Equity", "Debt", "Hybrid"]: return c
    return "Other"
