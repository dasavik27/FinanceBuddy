"""Mutual fund insights router."""

import io
import math
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import insights


def test_insights_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    res_ins = insights.get_insights(sid)
    assert "score" in res_ins
    assert "score_breakdown" in res_ins
    assert "nudges" in res_ins
    assert len(res_ins["score_breakdown"]) == 5



def test_insights_nudges_and_summary_fallback(monkeypatch):
    from domains.mutual_funds.routers import insights
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions

    rows = []
    for i in range(16):
        rows.append({
            "Fund": f"Fund {i} Direct Growth",
            "Category": "Large Cap",
            "Cap Type": "Large Cap",
            "Plan": "Direct",
            "Market Value": 40000.0,
            "Invested": 35000.0,
            "Weight%": 6.0,
            "AMC": f"AMC{i % 3}",
        })
    df_h = pd.DataFrame(rows)
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())
    monkeypatch.setattr(p, "get_summary", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(p, "compute_expense_drag", MagicMock(return_value=5000.0))
    sid = "insights_sweep"
    sessions._SESSIONS[sid] = {"portfolio": p, "last_accessed": datetime.now(), "owner": None}
    out = insights.get_insights(sid)
    assert any("16 funds" in n["message"] for n in out["nudges"])
    assert out["expense_drag"] == 5000.0

def test_insights_liquid_and_alpha_score_branches(monkeypatch):
    from domains.mutual_funds.routers import insights
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions

    df_h = pd.DataFrame([
        {"Fund": "Big Fund", "Category": "Large Cap", "Cap Type": "Large Cap", "Plan": "Direct",
         "Market Value": 600000.0, "Invested": 500000.0, "Weight%": 30.0, "AMC": "AMC1"},
        {"Fund": "Liquid Reserve", "Category": "Liquid", "Cap Type": "Liquid", "Plan": "Direct",
         "Market Value": 10000.0, "Invested": 10000.0, "Weight%": 1.5, "AMC": "AMC2"},
        {"Fund": "Small Agg", "Category": "Small Cap", "Cap Type": "Small Cap", "Plan": "Direct",
         "Market Value": 200000.0, "Invested": 150000.0, "Weight%": 35.0, "AMC": "AMC3"},
    ])
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame([{"Fund": "X", "Amount": 1000}]))
    monkeypatch.setattr(p, "get_summary", lambda **kw: {"alpha": 3.0, "expense_drag": 1000.0})
    sid = "insights_alpha"
    sessions._SESSIONS[sid] = {"portfolio": p, "last_accessed": datetime.now(), "owner": None}
    out = insights.get_insights(sid)
    assert any("liquid reserves" in n["message"].lower() for n in out["nudges"])
    assert out["score_breakdown"][0]["score"] == 22
    assert "expense_available" in out

def test_insights_alpha_extreme_branches(monkeypatch):
    from domains.mutual_funds.routers import insights
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions

    df_h = pd.DataFrame([
        {"Fund": "F1", "Category": "Large Cap", "Cap Type": "Large Cap", "Plan": "Direct",
         "Market Value": 100000.0, "Invested": 80000.0, "Weight%": 100.0, "AMC": "AMC1"},
    ])
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())
    monkeypatch.setattr(p, "get_summary", lambda **kw: {"alpha": 6.0, "expense_drag": 100.0})
    sid = "insights_alpha_hi"
    sessions._SESSIONS[sid] = {"portfolio": p, "last_accessed": datetime.now(), "owner": None}
    hi = insights.get_insights(sid, benchmark="Nifty 50")
    assert hi["score_breakdown"][0]["score"] == 30
    assert hi["benchmark"] == "Nifty 50"

    monkeypatch.setattr(p, "get_summary", lambda **kw: {"alpha": -1.0, "expense_drag": 100.0})
    lo = insights.get_insights(sid)
    assert lo["score_breakdown"][0]["score"] == 8


def test_insights_ter_coverage_when_ter_column_present(monkeypatch):
    from domains.mutual_funds.routers import insights
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions

    df_h = pd.DataFrame([
        {
            "Fund": "Covered Fund",
            "Category": "Large Cap",
            "Cap Type": "Large Cap",
            "Plan": "Direct",
            "Market Value": 80000.0,
            "Invested": 70000.0,
            "Weight%": 80.0,
            "AMC": "AMC1",
            "TER": 0.8,
        },
        {
            "Fund": "Missing TER",
            "Category": "Mid Cap",
            "Cap Type": "Mid Cap",
            "Plan": "Direct",
            "Market Value": 20000.0,
            "Invested": 18000.0,
            "Weight%": 20.0,
            "AMC": "AMC2",
            "TER": None,
        },
    ])
    p = Portfolio(df_h=df_h, df_t=pd.DataFrame(), df_s=pd.DataFrame())
    monkeypatch.setattr(p, "get_summary", lambda **kw: {"alpha": 1.0, "expense_drag": 200.0})
    sid = "insights_ter_cov"
    sessions._SESSIONS[sid] = {"portfolio": p, "last_accessed": datetime.now(), "owner": None}
    out = insights.get_insights(sid)
    assert out["expense_available"] is True
    assert out["ter_coverage_pct"] == pytest.approx(80.0)

