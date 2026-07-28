"""
core/reconciliation.py

Reconciliation Engine ("The Tax Auditor")
Cross-references trades from the government AIS against Broker Tax P&L files
to find missing cost basis, missing trades, and potential discrepancies.
"""

import difflib

def _normalize(name: str) -> str:
    """Removes generic words to create a robust string for matching."""
    words = str(name).lower().replace('-', ' ').replace('#', ' ').split()
    generic = {'fund', 'ct', 'the', 'of', 'and', 'limited', 'ltd', 'equity', 'shares', 'new', 'direct', 'plan', 'growth', 'asset'}
    return ' '.join([w for w in words if w not in generic])

def reconcile_trades(ais_data: dict, broker_trades: list) -> dict:
    """
    Reconciles AIS capital gains against a flat list of broker trades.
    Returns a dictionary of flagged discrepancies.
    """
    flags = {
        "zero_cost": [],
        "cost_mismatch": []
    }
    
    if not broker_trades:
        return flags
        
    # Combine AIS equity and mutual fund trades
    ais_trades = []
    ais_trades.extend(ais_data.get("capital_gains_equity", []))
    ais_trades.extend(ais_data.get("capital_gains_mf_equity", []))
    ais_trades.extend(ais_data.get("capital_gains_mf_other", []))
    ais_trades.extend(ais_data.get("cg_bonds_gold", []))
    ais_trades.extend(ais_data.get("cg_unlisted", []))
    ais_trades.extend(ais_data.get("cg_real_estate", []))
    
    # Aggregate AIS trades by security AND type (to handle ticker changes between STCG and LTCG)
    aggregated_ais = {}
    for at in ais_trades:
        sec = at.get("security")
        if not sec:
            amc = at.get("amc", "")
            fund = at.get("fund", "")
            sec = f"{amc} {fund}".strip()
            
        sec = str(sec).strip()
        if not sec: continue
        
        t_type = at.get("type", "UNKNOWN")
        key = f"{sec}___{t_type}"
        
        if key not in aggregated_ais:
            aggregated_ais[key] = {"security": sec, "type": t_type, "cost": 0.0, "consideration": 0.0, "has_zero_cost": False, "original": []}
            
        ais_cost = float(at.get("cost", 0))
        ais_sale = float(at.get("consideration", 0))
        
        if ais_cost == 0 and ais_sale > 0:
            aggregated_ais[key]["has_zero_cost"] = True
            
        aggregated_ais[key]["cost"] += ais_cost
        aggregated_ais[key]["consideration"] += ais_sale
        aggregated_ais[key]["original"].append(at)

    # Aggregate broker trades by security AND type
    aggregated_broker = {}
    for bt in broker_trades:
        sec = str(bt.get("security", "")).strip().lower()
        if not sec: continue
        
        t_type = bt.get("type", "UNKNOWN")
        key = f"{sec}___{t_type}"
        
        if key not in aggregated_broker:
            aggregated_broker[key] = {"security": bt.get("security"), "type": t_type, "cost": 0.0, "consideration": 0.0, "original": []}
            
        aggregated_broker[key]["cost"] += float(bt.get("cost", 0))
        aggregated_broker[key]["consideration"] += float(bt.get("consideration", 0))
        aggregated_broker[key]["original"].append(bt)

    # 1. Check AIS trades for zero cost, and see if Broker has the real cost
    for ais_key, agg_data in aggregated_ais.items():
        if agg_data["has_zero_cost"]:
            best_match = None
            best_score = 0
            n_ais = _normalize(agg_data["security"])
            for b_key, b_data in aggregated_broker.items():
                if b_data["type"] != agg_data["type"]:
                    continue
                    
                n_broker = _normalize(b_data["security"])
                is_sale_exact = abs(b_data["consideration"] - agg_data["consideration"]) <= max(10, agg_data["consideration"] * 0.005)
                score = difflib.SequenceMatcher(None, n_ais, n_broker).ratio()
                is_match = (
                    score > 0.5 or 
                    (n_broker and n_broker in n_ais) or 
                    (n_ais and n_ais in n_broker) or
                    (n_broker.replace(' ', '') in n_ais.replace(' ', '')) or
                    (is_sale_exact and score > 0.15)
                )
                
                if is_match:
                    if score > best_score:
                        best_score = score
                        best_match = b_data
            
            if best_match and best_match["cost"] > 0:
                flags["zero_cost"].append({
                    "security": agg_data["security"],
                    "type": agg_data["type"],
                    "ais_cost": 0,
                    "broker_cost": best_match["cost"],
                    "suggestion": f"Use Broker Cost of ₹{best_match['cost']:.2f}"
                })


    # 3. Check for massive cost mismatches (Grandfathering or Typo risks)
    for ais_key, agg_data in aggregated_ais.items():
        ais_cost = agg_data["cost"]
        ais_sale = agg_data["consideration"]
        
        if ais_cost > 0:
            best_match = None
            best_score = 0
            n_ais = _normalize(agg_data["security"])
            for b_key, b_data in aggregated_broker.items():
                if b_data["type"] != agg_data["type"]:
                    continue
                    
                n_broker = _normalize(b_data["security"])
                
                is_sale_exact = abs(b_data["consideration"] - ais_sale) <= max(10, ais_sale * 0.005)
                string_score = difflib.SequenceMatcher(None, n_ais, n_broker).ratio()
                
                is_match = (
                    string_score > 0.5 or 
                    (n_broker and n_broker in n_ais) or 
                    (n_ais and n_ais in n_broker) or
                    (n_broker.replace(' ', '') in n_ais.replace(' ', '')) or
                    (is_sale_exact and string_score > 0.15)
                )
                
                if is_match:
                    if is_sale_exact or abs(b_data["consideration"] - ais_sale) < (ais_sale * 0.10):
                        score = string_score
                        if score > best_score:
                            best_score = score
                            best_match = b_data
            
            if best_match:
                bt_cost = best_match["cost"]
                # If difference is > 20%
                if abs(ais_cost - bt_cost) > (ais_cost * 0.20):
                    flags["cost_mismatch"].append({
                        "security": agg_data["security"],
                        "type": agg_data["type"],
                        "ais_cost": ais_cost,
                        "broker_cost": bt_cost,
                        "suggestion": f"Large cost difference detected. Check if FMV indexation applies or if there's an error."
                    })

    return flags
