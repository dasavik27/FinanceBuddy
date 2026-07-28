"""
Regression tests for the AIS↔broker reconciliation engine and the broker parser's
Section 50AA slab tagging. Uses fabricated, non-PII trade data.
"""
from domains.tax_expert.reconciliation import reconcile_trades, _normalize


def test_zero_cost_ais_trade_flagged_with_broker_cost():
    ais_data = {
        "capital_gains_equity": [{
            "security": "NEWGEN SOFTWARE TECHNOLOGIES LIMITED", "type": "LTCG",
            "consideration": 19694, "cost": 0, "gain": 19694,
        }],
    }
    broker_trades = [{
        "security": "NEWGEN", "type": "LTCG",
        "consideration": 19694, "cost": 7000, "gain": 12694,
    }]
    flags = reconcile_trades(ais_data, broker_trades)
    assert len(flags["zero_cost"]) == 1
    flag = flags["zero_cost"][0]
    assert flag["ais_cost"] == 0
    assert flag["broker_cost"] == 7000


def test_no_flags_when_costs_agree():
    ais_data = {
        "capital_gains_equity": [{
            "security": "TATA CAPITAL LIMITED", "type": "STCG",
            "consideration": 15477, "cost": 14996, "gain": 481,
        }],
    }
    broker_trades = [{
        "security": "TATACAP", "type": "STCG",
        "consideration": 15477, "cost": 14996, "gain": 481,
    }]
    flags = reconcile_trades(ais_data, broker_trades)
    assert flags["zero_cost"] == []
    assert flags["cost_mismatch"] == []


def test_large_cost_mismatch_flagged():
    ais_data = {
        "capital_gains_equity": [{
            "security": "SOME SHARE", "type": "LTCG",
            "consideration": 100000, "cost": 20000, "gain": 80000,
        }],
    }
    broker_trades = [{
        "security": "SOME SHARE", "type": "LTCG",
        "consideration": 100000, "cost": 60000, "gain": 40000,   # >20% off the AIS cost
    }]
    flags = reconcile_trades(ais_data, broker_trades)
    assert len(flags["cost_mismatch"]) == 1


def test_empty_broker_returns_no_flags():
    ais_data = {"capital_gains_equity": [{"security": "X", "type": "LTCG",
                                          "consideration": 100, "cost": 0, "gain": 100}]}
    assert reconcile_trades(ais_data, []) == {"zero_cost": [], "cost_mismatch": []}


def test_normalize_strips_generic_words():
    assert _normalize("AXIS BLUECHIP FUND - DIRECT PLAN - GROWTH") == "axis bluechip"
