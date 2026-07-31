import os
import uuid
from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from main import app

# ---------------------------------------------------------------------------
# Database-backed tests
# ---------------------------------------------------------------------------
# Postgres replaced SQLite, so the tests that exercise persistence now need a real
# server. Rather than let them fail with a connection error - which reads as "the
# code is broken" - they are skipped with a reason when TEST_DATABASE_URL is unset.
#
# TEST_DATABASE_URL, deliberately not DATABASE_URL: these create and drop schemas,
# and pointing them at the value already in .env would run them against whatever
# that is, which on a developer machine is production.
#
# Each session gets its own schema, so runs are isolated and a failed run leaves
# nothing behind that the next one has to clean up.

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

# With no test database, unset DATABASE_URL for the whole run so db.get_pool() raises
# immediately instead of dialling a real host. Two reasons, and the second is the one
# that actually bit: a connection attempt to an unreachable server blocks for the full
# 10 s pool timeout *per call*, which turned a one-minute suite into an unbounded one;
# and .env holds the production DSN, so any test that slipped past a skip would write
# to it.
if not TEST_DATABASE_URL:
    os.environ.pop("DATABASE_URL", None)

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="needs Postgres - set TEST_DATABASE_URL (see DEPLOYMENT.md)",
)


@pytest.fixture(scope="session")
def db_schema():
    """A throwaway schema for this test session, dropped at the end."""
    if not TEST_DATABASE_URL:
        pytest.skip("needs Postgres - set TEST_DATABASE_URL")

    from shared import db

    schema = f"test_{uuid.uuid4().hex[:12]}"
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    db.reset_pool()

    with db.connect() as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
    # search_path is set per connection, so it has to be applied on checkout rather
    # than once here - a pooled connection is not the same one next time.
    previous_configure = db._configure

    def _configure_with_schema(conn):
        previous_configure(conn)
        conn.execute(f'SET search_path TO "{schema}"')

    db._configure = _configure_with_schema
    db.reset_pool()

    from migrations import migrate
    migrate.upgrade()

    yield schema

    db._configure = previous_configure
    db.reset_pool()
    with db.connect() as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    db.close_pool()


@pytest.fixture
def clean_db(db_schema):
    """Empty every table before a test, keeping the schema."""
    from shared import db

    with db.connect() as conn:
        conn.execute("TRUNCATE users, sessions RESTART IDENTITY CASCADE")
    yield db_schema


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
