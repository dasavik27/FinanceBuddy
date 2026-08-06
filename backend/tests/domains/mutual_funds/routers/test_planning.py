"""Mutual fund planning router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import planning


def test_planning_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session

    # get_tax_harvest
    res_tax = planning.get_tax_harvest(sid)
    assert isinstance(res_tax, dict)

    # get_sip_projection (default monthly_sip from df_s)
    # Pass Query()-backed args explicitly — FastAPI does not resolve them on direct calls.
    res_sip = planning.get_sip_projection(
        sid, years=5, annual_return=12.0, stepup_pct=10.0, monthly_sip=0.0, lumpsum=0.0
    )
    assert "projected_corpus" in res_sip or "future_value" in res_sip or "assumed_monthly_sip" in res_sip

    # get_xirr_by_fy
    monkeypatch.setattr("domains.mutual_funds.derived.cached_xirr_by_fy", lambda df_t, df_h: [{"fy": "FY24", "xirr": 15.0}])
    res_fy = planning.get_xirr_by_fy(sid)
    assert "fy_series" in res_fy

    # get_sip_attribution
    res_attr = planning.get_sip_attribution(sid)
    assert isinstance(res_attr, dict)

    # get_mandate_overlap
    res_mo = planning.get_mandate_overlap(sid)
    assert isinstance(res_mo, dict)

    # get_what_if
    monkeypatch.setattr(planning, "fetch_nav_series_by_code", lambda code, days: pd.Series([10.0, 20.0], index=pd.date_range("2020-01-01", periods=2)))
    res_whatif = planning.get_what_if(sid, scheme_code="119551", monthly_amount=5000.0, years=3)
    assert "invested" in res_whatif or "future_value" in res_whatif or "total_invested" in res_whatif or "error" not in res_whatif

    # get_what_if empty
    monkeypatch.setattr(planning, "fetch_nav_series_by_code", lambda code, days: pd.Series([], dtype=float))
    assert "error" in planning.get_what_if(
        sid, scheme_code="119551", monthly_amount=10000.0, years=5
    )


def test_planning_empty_corpus_projection(sample_portfolio_session):
    from datetime import datetime
    from domains.mutual_funds.models import Portfolio
    from domains.mutual_funds import sessions as mf_sessions
    from domains.mutual_funds.routers import planning

    p2 = Portfolio(df_h=pd.DataFrame(), df_t=pd.DataFrame(), df_s=pd.DataFrame())
    mf_sessions._SESSIONS["plan_empty"] = {"portfolio": p2, "last_accessed": datetime.now(), "owner": None}
    planning.get_sip_projection("plan_empty", years=5, annual_return=12.0, stepup_pct=0.0, monthly_sip=0.0, lumpsum=0.0, include_existing_corpus=True)
