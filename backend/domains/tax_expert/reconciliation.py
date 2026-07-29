"""
core/reconciliation.py

Reconciliation Engine ("The Tax Auditor")
Cross-references trades from the government AIS against Broker Tax P&L files
to find missing cost basis, missing trades, and potential discrepancies.
"""

import difflib

_GENERIC_WORDS = frozenset({
    'fund', 'ct', 'the', 'of', 'and', 'limited', 'ltd', 'equity', 'shares',
    'new', 'direct', 'plan', 'growth', 'asset',
})


def _normalize(name: str) -> str:
    """Removes generic words to create a robust string for matching."""
    words = str(name).lower().replace('-', ' ').replace('#', ' ').split()
    return ' '.join([w for w in words if w not in _GENERIC_WORDS])


def _is_name_match(n_ais: str, n_ais_ns: str, n_broker: str, n_broker_ns: str,
                   score: float, is_sale_exact: bool) -> bool:
    """Shared match predicate.

    Takes pre-normalized names and their space-stripped variants so callers can
    hoist that work out of their loops.
    """
    return (
        score > 0.5
        or (n_broker and n_broker in n_ais)
        or (n_ais and n_ais in n_broker)
        or (n_broker_ns in n_ais_ns)
        or (is_sale_exact and score > 0.15)
    )

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

    # Aggregate broker trades by security AND type, bucketed by type.
    #
    # Bucketing matters: the matching loops below only ever compare same-type
    # entries, but previously scanned every broker key and `continue`d on a type
    # mismatch. Names are normalized once here instead of once per AIS row — the
    # old code called _normalize(broker) inside the inner loop, so B
    # normalizations were repeated A times.
    broker_by_type = {}
    for bt in broker_trades:
        sec = str(bt.get("security", "")).strip().lower()
        if not sec:
            continue

        t_type = bt.get("type", "UNKNOWN")
        bucket = broker_by_type.setdefault(t_type, {})

        entry = bucket.get(sec)
        if entry is None:
            entry = bucket[sec] = {
                "security": bt.get("security"), "type": t_type,
                "cost": 0.0, "consideration": 0.0, "original": [],
            }
        entry["cost"] += float(bt.get("cost", 0))
        entry["consideration"] += float(bt.get("consideration", 0))
        entry["original"].append(bt)

    # Precompute the normalized forms for every broker entry, once. The exact-name
    # index is kept in its own structure rather than inside the bucket, so bucket
    # iteration stays a clean pass over real entries.
    broker_norm_index = {}
    for t_type, bucket in broker_by_type.items():
        for entry in bucket.values():
            n = _normalize(entry["security"])
            entry["_norm"] = n
            entry["_norm_ns"] = n.replace(' ', '')
        broker_norm_index[t_type] = {
            e["_norm"]: e for e in bucket.values() if e["_norm"]
        }

    # Single pass over AIS aggregates handling BOTH checks.
    #
    # This was two separate loops over the same data, each O(A x B) with a
    # difflib.SequenceMatcher call per pair (itself O(len_a x len_b)) — so the
    # whole thing was O(A x B x L^2) and the second loop redid the first loop's
    # normalization and scoring from scratch. The two checks are not mutually
    # exclusive (an aggregate can hold both zero-cost and priced trades), so both
    # candidate matches are tracked in one traversal.
    #
    # The two checks use different acceptance rules and therefore need separate
    # candidates: `loose` is the plain name/sale match used for zero-cost fills;
    # `strict` additionally requires the broker sale value to be within 10% of the
    # AIS sale value before a cost mismatch is reported.
    for agg_data in aggregated_ais.values():
        ais_cost = agg_data["cost"]
        ais_sale = agg_data["consideration"]
        needs_zero_cost = agg_data["has_zero_cost"]
        needs_mismatch = ais_cost > 0
        if not (needs_zero_cost or needs_mismatch):
            continue

        bucket = broker_by_type.get(agg_data["type"])
        if not bucket:
            continue

        n_ais = _normalize(agg_data["security"])
        n_ais_ns = n_ais.replace(' ', '')
        sale_tolerance = max(10, ais_sale * 0.005)

        loose_match, loose_score = None, 0
        strict_match, strict_score = None, 0

        def _passes_sale_gate(delta: float) -> bool:
            """The cost-mismatch gate, matching the original expression exactly."""
            return delta <= sale_tolerance or delta < ais_sale * 0.10

        # Fast path, valid ONLY when an exactly-equal normalized name also clears
        # the sale gate. Then both candidates score 1.0 and nothing can beat them,
        # so the scan is provably redundant. If the exact match fails the gate we
        # must still scan, because a lower-scored but sale-proximate entry can
        # legitimately become the strict match.
        exact = broker_norm_index.get(agg_data["type"], {}).get(n_ais) if n_ais else None
        if exact is not None and _passes_sale_gate(abs(exact["consideration"] - ais_sale)):
            loose_match, loose_score = exact, 1.0
            strict_match, strict_score = exact, 1.0
        else:
            for b_data in bucket.values():
                n_broker = b_data["_norm"]
                sale_delta = abs(b_data["consideration"] - ais_sale)
                is_sale_exact = sale_delta <= sale_tolerance
                score = difflib.SequenceMatcher(None, n_ais, n_broker).ratio()

                if not _is_name_match(n_ais, n_ais_ns, n_broker, b_data["_norm_ns"],
                                      score, is_sale_exact):
                    continue

                if score > loose_score:
                    loose_score, loose_match = score, b_data
                # Cost-mismatch reporting additionally gates on sale proximity.
                if _passes_sale_gate(sale_delta) and score > strict_score:
                    strict_score, strict_match = score, b_data

        if needs_zero_cost and loose_match and loose_match["cost"] > 0:
            flags["zero_cost"].append({
                "security": agg_data["security"],
                "type": agg_data["type"],
                "ais_cost": 0,
                "broker_cost": loose_match["cost"],
                "suggestion": f"Use Broker Cost of ₹{loose_match['cost']:.2f}"
            })

        if needs_mismatch and strict_match:
            bt_cost = strict_match["cost"]
            # If difference is > 20%
            if abs(ais_cost - bt_cost) > (ais_cost * 0.20):
                flags["cost_mismatch"].append({
                    "security": agg_data["security"],
                    "type": agg_data["type"],
                    "ais_cost": ais_cost,
                    "broker_cost": bt_cost,
                    "suggestion": "Large cost difference detected. Check if FMV indexation applies or if there's an error."
                })

    return flags
