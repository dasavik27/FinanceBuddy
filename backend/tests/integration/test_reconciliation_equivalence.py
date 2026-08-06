"""
Differential test for the reconciliation rewrite.

reconcile_trades() was restructured from two O(A x B x L^2) passes into a single
pass with hoisted normalization and an exact-name fast path. The matching rules
are fiddly (a loose name/sale predicate plus a separate sale-proximity gate), so
this pins the optimized version against a literal transcription of the original
algorithm over randomized inputs.

If this fails, the optimization changed behaviour and is wrong — the reference
below is the specification.
"""

import difflib
import random

from domains.tax_expert.reconciliation import reconcile_trades, _normalize


def reference_reconcile(ais_data: dict, broker_trades: list) -> dict:
    """Literal transcription of the pre-optimization implementation."""
    flags = {"zero_cost": [], "cost_mismatch": []}
    if not broker_trades:
        return flags

    ais_trades = []
    for key in ("capital_gains_equity", "capital_gains_mf_equity", "capital_gains_mf_other",
                "cg_bonds_gold", "cg_unlisted", "cg_real_estate"):
        ais_trades.extend(ais_data.get(key, []))

    aggregated_ais = {}
    for at in ais_trades:
        sec = at.get("security")
        if not sec:
            sec = f"{at.get('amc', '')} {at.get('fund', '')}".strip()
        sec = str(sec).strip()
        if not sec:
            continue
        t_type = at.get("type", "UNKNOWN")
        key = f"{sec}___{t_type}"
        if key not in aggregated_ais:
            aggregated_ais[key] = {"security": sec, "type": t_type, "cost": 0.0,
                                   "consideration": 0.0, "has_zero_cost": False, "original": []}
        ais_cost = float(at.get("cost", 0))
        ais_sale = float(at.get("consideration", 0))
        if ais_cost == 0 and ais_sale > 0:
            aggregated_ais[key]["has_zero_cost"] = True
        aggregated_ais[key]["cost"] += ais_cost
        aggregated_ais[key]["consideration"] += ais_sale
        aggregated_ais[key]["original"].append(at)

    aggregated_broker = {}
    for bt in broker_trades:
        sec = str(bt.get("security", "")).strip().lower()
        if not sec:
            continue
        t_type = bt.get("type", "UNKNOWN")
        key = f"{sec}___{t_type}"
        if key not in aggregated_broker:
            aggregated_broker[key] = {"security": bt.get("security"), "type": t_type,
                                      "cost": 0.0, "consideration": 0.0, "original": []}
        aggregated_broker[key]["cost"] += float(bt.get("cost", 0))
        aggregated_broker[key]["consideration"] += float(bt.get("consideration", 0))
        aggregated_broker[key]["original"].append(bt)

    for agg_data in aggregated_ais.values():
        if agg_data["has_zero_cost"]:
            best_match, best_score = None, 0
            n_ais = _normalize(agg_data["security"])
            for b_data in aggregated_broker.values():
                if b_data["type"] != agg_data["type"]:
                    continue
                n_broker = _normalize(b_data["security"])
                is_sale_exact = abs(b_data["consideration"] - agg_data["consideration"]) <= max(
                    10, agg_data["consideration"] * 0.005)
                score = difflib.SequenceMatcher(None, n_ais, n_broker).ratio()
                is_match = (
                    score > 0.5
                    or (n_broker and n_broker in n_ais)
                    or (n_ais and n_ais in n_broker)
                    or (n_broker.replace(' ', '') in n_ais.replace(' ', ''))
                    or (is_sale_exact and score > 0.15)
                )
                if is_match and score > best_score:
                    best_score, best_match = score, b_data
            if best_match and best_match["cost"] > 0:
                flags["zero_cost"].append({
                    "security": agg_data["security"], "type": agg_data["type"],
                    "ais_cost": 0, "broker_cost": best_match["cost"],
                    "suggestion": f"Use Broker Cost of ₹{best_match['cost']:.2f}",
                })

    for agg_data in aggregated_ais.values():
        ais_cost = agg_data["cost"]
        ais_sale = agg_data["consideration"]
        if ais_cost > 0:
            best_match, best_score = None, 0
            n_ais = _normalize(agg_data["security"])
            for b_data in aggregated_broker.values():
                if b_data["type"] != agg_data["type"]:
                    continue
                n_broker = _normalize(b_data["security"])
                is_sale_exact = abs(b_data["consideration"] - ais_sale) <= max(10, ais_sale * 0.005)
                string_score = difflib.SequenceMatcher(None, n_ais, n_broker).ratio()
                is_match = (
                    string_score > 0.5
                    or (n_broker and n_broker in n_ais)
                    or (n_ais and n_ais in n_broker)
                    or (n_broker.replace(' ', '') in n_ais.replace(' ', ''))
                    or (is_sale_exact and string_score > 0.15)
                )
                if is_match:
                    if is_sale_exact or abs(b_data["consideration"] - ais_sale) < (ais_sale * 0.10):
                        if string_score > best_score:
                            best_score, best_match = string_score, b_data
            if best_match:
                bt_cost = best_match["cost"]
                if abs(ais_cost - bt_cost) > (ais_cost * 0.20):
                    flags["cost_mismatch"].append({
                        "security": agg_data["security"], "type": agg_data["type"],
                        "ais_cost": ais_cost, "broker_cost": bt_cost,
                        "suggestion": "Large cost difference detected. Check if FMV indexation applies or if there's an error.",
                    })

    return flags


NAMES = [
    "RELIANCE INDUSTRIES LIMITED", "Reliance Industries", "TCS", "TATA CONSULTANCY SERVICES LTD",
    "HDFC BANK", "HDFC Bank Limited", "AXIS BLUECHIP FUND DIRECT PLAN GROWTH",
    "Axis Bluechip", "SBI SMALL CAP FUND", "INFOSYS LTD", "Infy", "ITC LIMITED",
    "NIPPON INDIA GOLD ETF", "", "   ", "ZOMATO",
]
TYPES = ["LTCG", "STCG", "UNKNOWN"]


def _random_case(rng):
    def trade():
        cost = rng.choice([0, 0, rng.randrange(1000, 500000)])
        sale = rng.choice([0, rng.randrange(1000, 800000)])
        return {"security": rng.choice(NAMES), "type": rng.choice(TYPES),
                "cost": cost, "consideration": sale}

    ais = {
        "capital_gains_equity": [trade() for _ in range(rng.randrange(0, 6))],
        "capital_gains_mf_equity": [trade() for _ in range(rng.randrange(0, 4))],
        "capital_gains_mf_other": [trade() for _ in range(rng.randrange(0, 3))],
        "cg_bonds_gold": [], "cg_unlisted": [], "cg_real_estate": [],
    }
    broker = [trade() for _ in range(rng.randrange(0, 8))]
    return ais, broker


def test_optimized_matches_reference_on_random_inputs():
    rng = random.Random(20260729)  # fixed seed: reproducible failures
    for i in range(400):
        ais, broker = _random_case(rng)
        expected = reference_reconcile(ais, broker)
        actual = reconcile_trades(ais, broker)
        assert actual == expected, (
            f"divergence on case {i}\nais={ais}\nbroker={broker}\n"
            f"expected={expected}\nactual={actual}"
        )


def test_handles_empty_broker():
    assert reconcile_trades({"capital_gains_equity": []}, []) == {
        "zero_cost": [], "cost_mismatch": []
    }


def test_detects_zero_cost_fill():
    ais = {"capital_gains_equity": [
        {"security": "RELIANCE INDUSTRIES LIMITED", "type": "LTCG",
         "cost": 0, "consideration": 500_000},
    ]}
    broker = [{"security": "Reliance Industries", "type": "LTCG",
               "cost": 300_000, "consideration": 500_000}]
    flags = reconcile_trades(ais, broker)
    assert len(flags["zero_cost"]) == 1
    assert flags["zero_cost"][0]["broker_cost"] == 300_000


def test_detects_cost_mismatch():
    ais = {"capital_gains_equity": [
        {"security": "TCS", "type": "LTCG", "cost": 100_000, "consideration": 500_000},
    ]}
    broker = [{"security": "TCS", "type": "LTCG",
               "cost": 400_000, "consideration": 500_000}]
    flags = reconcile_trades(ais, broker)
    assert len(flags["cost_mismatch"]) == 1
    assert flags["cost_mismatch"][0]["ais_cost"] == 100_000
