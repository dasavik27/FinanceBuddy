from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Synthetic portfolio fixture
# ---------------------------------------------------------------------------
# Entirely fabricated fund names/ISINs/PAN — NOT derived from any real user's
# CAS statement. Dates are relative to "now" (via timedelta) rather than fixed
# absolute dates, except where a fixed pre-2023 date is needed to exercise the
# Section 50AA regime-cutoff branch — 2023-04-01 is always in the past.

FUND_EQUITY = "Synthetic Flexi Growth Fund"
FUND_ELSS = "Synthetic ELSS Saver Fund"
FUND_LIQUID = "Synthetic Liquid Reserve Fund"


def _d(days_ago: int) -> datetime:
    return datetime.now() - timedelta(days=days_ago)


@pytest.fixture
def synthetic_transactions() -> pd.DataFrame:
    rows = []

    # Equity: 15 monthly SIP installments spanning the 365-day LTCG boundary —
    # the oldest ~5 installments land >365 days old (LTCG-eligible), the rest <365 (STCG).
    for i in range(15):
        days_ago = 500 - (i * 30)
        rows.append({
            "Fund": FUND_EQUITY, "Date": _d(days_ago), "Type": "TransactionType.PURCHASE_SIP",
            "Units": 200.0, "NAV": 20.0 + i * 0.3, "Amount": 200.0 * (20.0 + i * 0.3),
        })

    # ELSS: single lumpsum well within the 3-year (1095-day) statutory lock-in
    rows.append({
        "Fund": FUND_ELSS, "Date": _d(100), "Type": "TransactionType.PURCHASE",
        "Units": 1000.0, "NAV": 15.0, "Amount": 15000.0,
    })

    # Liquid/debt: one pre-Section-50AA-cutoff purchase (fixed absolute date, always
    # in the past) to exercise the pre-2023 debt-LTCG branch...
    rows.append({
        "Fund": FUND_LIQUID, "Date": datetime(2022, 1, 15), "Type": "TransactionType.PURCHASE",
        "Units": 500.0, "NAV": 100.0, "Amount": 50000.0,
    })
    # ...a post-cutoff top-up (always slab-taxed regardless of holding period)...
    rows.append({
        "Fund": FUND_LIQUID, "Date": _d(200), "Type": "TransactionType.PURCHASE",
        "Units": 100.0, "NAV": 108.0, "Amount": 10800.0,
    })
    # ...and a partial redemption to exercise FIFO lot reduction.
    rows.append({
        "Fund": FUND_LIQUID, "Date": _d(20), "Type": "TransactionType.REDEMPTION",
        "Units": -200.0, "NAV": 112.0, "Amount": -22400.0,
    })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


@pytest.fixture
def synthetic_holdings() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Fund": FUND_EQUITY, "ISIN": "INF000X00001", "Category": "Equity", "Cap Type": "Flexi Cap",
            "Units": 3000.0, "NAV": 24.0, "Market Value": 3000.0 * 24.0, "AMC": "Synthetic AMC A",
            "Plan": "Direct", "Invested": 3000.0 * 22.0,
        },
        {
            "Fund": FUND_ELSS, "ISIN": "INF000X00002", "Category": "ELSS", "Cap Type": "Flexi Cap",
            "Units": 1000.0, "NAV": 17.0, "Market Value": 1000.0 * 17.0, "AMC": "Synthetic AMC B",
            "Plan": "Direct", "Invested": 15000.0,
        },
        {
            "Fund": FUND_LIQUID, "ISIN": "INF000X00003", "Category": "Liquid", "Cap Type": None,
            "Units": 400.0, "NAV": 115.0, "Market Value": 400.0 * 115.0, "AMC": "Synthetic AMC C",
            "Plan": "Direct", "Invested": 400.0 * 105.0,
        },
    ])
