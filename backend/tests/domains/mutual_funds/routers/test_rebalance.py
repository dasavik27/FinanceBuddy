"""Mutual fund rebalance router."""

import io
import math
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.models import Portfolio
from domains.mutual_funds import sessions
from domains.mutual_funds.routers import rebalance


def test_rebalance_router(sample_portfolio_session):
    sid, p = sample_portfolio_session

    # Balanced profile
    res_plan = rebalance.get_rebalance_plan(sid, profile="Balanced")
    assert "drift_score" in res_plan
    assert "orders" in res_plan

    # Auto profile (which will detect Aggressive/Balanced/Conservative)
    res_auto = rebalance.get_rebalance_plan(sid, profile="Auto")
    assert "drift_score" in res_auto
    assert "profile_used" in res_auto

    # Aggressive profile (triggers intra-equity check)
    res_agg = rebalance.get_rebalance_plan(sid, profile="Aggressive")
    assert "drift_score" in res_agg
    assert res_agg["profile_used"] == "Aggressive"

    # Empty portfolio
    from datetime import datetime
    empty_p = Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame(), df_s=pd.DataFrame())
    sessions._SESSIONS["empty_sid"] = {
        "portfolio": empty_p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    assert rebalance.get_rebalance_plan("empty_sid")["status"] == "Empty"



def test_rebalance_auto_profiles_and_sell_notes(monkeypatch):
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions as mf_sessions
    from domains.mutual_funds.routers import rebalance

    def _portfolio(equity_pct):
        eq_val = equity_pct * 1000.0
        debt_val = max(1000.0, 100000.0 - eq_val)
        df_h = pd.DataFrame([
            {"Fund": "Eq Fund", "Category": "Large Cap", "Market Value": eq_val, "Invested": eq_val * 0.9},
            {"Fund": "Debt Fund", "Category": "Liquid", "Market Value": debt_val, "Invested": debt_val * 0.9},
        ])
        return Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())

    for pct in (70, 40, 10):
        sid = f"reb_{pct}"
        mf_sessions._SESSIONS[sid] = {"portfolio": _portfolio(pct), "last_accessed": datetime.now(), "owner": None}
        out = rebalance.get_rebalance_plan(sid, profile="Auto")
        assert "drift_score" in out

    sid_empty = "reb_empty"
    mf_sessions._SESSIONS[sid_empty] = {
        "portfolio": Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame(), df_s=pd.DataFrame()),
        "last_accessed": datetime.now(), "owner": None,
    }
    assert rebalance.get_rebalance_plan(sid_empty)["status"] == "Empty"

    monkeypatch.setattr(
        rebalance, "select_sell_candidate",
        lambda df_h, df_t, mask, amount: {
            "fund_suggestion": "Sample Fund",
            "locked_note": "ELSS locked.",
            "exit_load_note": "Exit load applies.",
            "shortfall": 5000.0,
        },
    )
    mf_sessions._SESSIONS["reb_sell"] = {
        "portfolio": _portfolio(80), "last_accessed": datetime.now(), "owner": None,
    }
    out2 = rebalance.get_rebalance_plan("reb_sell", profile="Balanced")
    notes = " ".join(o.get("note", "") for o in out2.get("orders", []))
    assert "ELSS" in notes or not out2.get("orders")
    sell_orders = [o for o in out2.get("orders", []) if "Sell" in o.get("action", "")]
    if sell_orders:
        assert sell_orders[0].get("fund") == "Sample Fund"

def test_rebalance_empty_value_and_buy_notes(monkeypatch):
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions as mf_sessions
    from domains.mutual_funds.routers import rebalance

    sid = "reb_zero"
    mf_sessions._SESSIONS[sid] = {
        "portfolio": Portfolio(
            df_h=pd.DataFrame([{"Fund": "F", "Category": "Large Cap", "Market Value": 0.0, "Invested": 0.0}]),
            df_t=pd.DataFrame(), df_s=pd.DataFrame(),
        ),
        "last_accessed": datetime.now(), "owner": None,
    }
    assert rebalance.get_rebalance_plan(sid)["status"] == "Empty"

    monkeypatch.setattr(
        rebalance, "select_sell_candidate",
        lambda df_h, df_t, mask, amount: {
            "locked_note": "Locked units.",
            "exit_load_note": "Exit load.",
            "shortfall": 1000.0,
        },
    )
    sid2 = "reb_buy"
    mf_sessions._SESSIONS[sid2] = {
        "portfolio": Portfolio(
            df_h=pd.DataFrame([
                {"Fund": "Eq", "Category": "Large Cap", "Market Value": 90000.0, "Invested": 80000.0},
                {"Fund": "Debt", "Category": "Liquid", "Market Value": 10000.0, "Invested": 9000.0},
            ]),
            df_t=pd.DataFrame(), df_s=pd.DataFrame(),
        ),
        "last_accessed": datetime.now(), "owner": None,
    }
    out = rebalance.get_rebalance_plan(sid2, profile="Conservative")
    assert "orders" in out

