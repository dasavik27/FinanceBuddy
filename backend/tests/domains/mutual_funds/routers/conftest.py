"""Shared fixtures for mutual fund router tests."""

import io
import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from domains.mutual_funds.models import Portfolio
from domains.mutual_funds import sessions



@pytest.fixture
def sample_portfolio_session(monkeypatch):
    """Sets up a registered mock portfolio in session memory."""
    dates = pd.date_range("2023-01-01", periods=10, freq="ME")
    df_h = pd.DataFrame([
        {
            "Fund": "HDFC Top 100 Direct Growth",
            "Category": "Large Cap",
            "Cap Type": "Large Cap",
            "Plan": "Direct",
            "ISIN": "INF179K01BE2",
            "Units": 100.0,
            "Invested": 10000.0,
            "NAV": 150.0,
            "Market Value": 15000.0,
            "Gain": 5000.0,
            "Gain%": 50.0,
            "Weight%": 30.0,
            "AMC": "HDFC",
            "NAV Date": "2024-01-10",
        },
        {
            "Fund": "Nippon India Small Cap Regular Growth",
            "Category": "Small Cap",
            "Cap Type": "Small Cap",
            "Plan": "Regular",
            "ISIN": "INF204K01E03",
            "Units": 200.0,
            "Invested": 20000.0,
            "NAV": 125.0,
            "Market Value": 25000.0,
            "Gain": 5000.0,
            "Gain%": 25.0,
            "Weight%": 50.0,
            "AMC": "Nippon",
            "NAV Date": "2024-01-10",
        },
        {
            "Fund": "SBI Liquid Direct Growth",
            "Category": "Liquid",
            "Cap Type": "Liquid",
            "Plan": "Direct",
            "ISIN": "INF200K01VA7",
            "Units": 10.0,
            "Invested": 10000.0,
            "NAV": 1000.0,
            "Market Value": 10000.0,
            "Gain": 0.0,
            "Gain%": 0.0,
            "Weight%": 20.0,
            "AMC": "SBI",
            "NAV Date": "2024-01-10",
        },
    ])

    df_t = pd.DataFrame([
        {
            "Fund": "HDFC Top 100 Direct Growth",
            "Date": pd.Timestamp("2023-01-15"),
            "Type": "PURCHASE_SIP",
            "Units": 100.0,
            "NAV": 100.0,
            "Amount": 10000.0,
        },
        {
            "Fund": "Nippon India Small Cap Regular Growth",
            "Date": pd.Timestamp("2023-02-15"),
            "Type": "PURCHASE_SIP",
            "Units": 200.0,
            "NAV": 100.0,
            "Amount": 20000.0,
        },
        {
            "Fund": "SBI Liquid Direct Growth",
            "Date": pd.Timestamp("2023-03-15"),
            "Type": "PURCHASE",
            "Units": 10.0,
            "NAV": 1000.0,
            "Amount": 10000.0,
        },
    ])

    df_s = pd.DataFrame([
        {"Fund": "HDFC Top 100 Direct Growth", "Date": "15-01-2023", "Amount": 5000.0},
        {"Fund": "Nippon India Small Cap Regular Growth", "Date": "15-02-2023", "Amount": 5000.0},
    ])

    from datetime import datetime

    p = Portfolio(df_h=df_h, df_t=df_t, df_s=df_s)
    sid = "test_mf_session_123"
    sessions._SESSIONS[sid] = {
        "portfolio": p,
        "last_accessed": datetime.now(),
        "owner": None,
    }
    return sid, p
