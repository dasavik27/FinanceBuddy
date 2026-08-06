"""Mutual fund overview router."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

from domains.mutual_funds.routers import overview


def test_overview_router(sample_portfolio_session, monkeypatch):
    sid, p = sample_portfolio_session
    bench_series = pd.Series([100.0, 105.0, 110.0], index=pd.date_range("2023-01-01", periods=3))
    monkeypatch.setattr(overview, "fetch_benchmark_series", lambda t, d, refresh=False: bench_series)
    monkeypatch.setattr(
        overview,
        "cached_period_comparison",
        lambda *args, **kwargs: {
            "dates": ["2023-01-01", "2023-01-02"],
            "portfolio": [100.0, 110.0],
            "benchmark": [100.0, 105.0],
            "port_pct": 10.0,
            "bench_pct": 5.0,
            "port_value": 50000.0,
            "bench_value": 45000.0,
            "use_xirr": False,
        },
    )

    # get_summary
    resp_sum = overview.get_summary(sid, "Nifty 50")
    assert resp_sum.status_code == 200

    # get_overview
    resp_ov = overview.get_overview(sid, period="1Y", benchmark="Nifty 50")
    assert resp_ov.status_code == 200

    # get_benchmark_overlay (with benchmarks)
    resp_bm = overview.get_benchmark_overlay(sid, period="1Y", benchmarks="Nifty 50,S&P 500")
    assert resp_bm.status_code == 200

    # get_benchmark_overlay (empty benchmarks)
    resp_bm_empty = overview.get_benchmark_overlay(sid, period="1Y", benchmarks="")
    assert resp_bm_empty.status_code == 200

    # get_allocation
    resp_alloc = overview.get_allocation(sid)
    assert resp_alloc.status_code == 200


def test_overview_empty_benchmark_curve(monkeypatch, sample_portfolio_session):
    sid, _ = sample_portfolio_session
    monkeypatch.setattr(overview, "fetch_benchmark_series", lambda *a, **k: pd.Series(dtype=float))
    monkeypatch.setattr(
        overview,
        "cached_period_comparison",
        lambda *a, **k: {"dates": [], "portfolio": [], "benchmark": []},
    )
    resp = overview.get_overview(sid, period="1Y", benchmark="", refresh=False)
    assert resp.status_code == 200
