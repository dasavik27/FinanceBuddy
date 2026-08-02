import base64
import os
import uuid
from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Set before `from main import app`: IdentityMiddleware builds its verifier
# (shared.oidc.from_env()) the first time ANY request goes through the app, which
# can be triggered by an unrelated test file elsewhere in the session. These have to
# exist from the very start so a real (if fake-shaped) OidcJwtVerifier is always
# constructed - fake_bearer_auth below patches its verify() method, which works
# regardless of when the instance was built, but only if it was built at all.
os.environ.setdefault("AUTH_JWKS_URL", "https://example-test-issuer.invalid/jwks.json")
os.environ.setdefault("AUTH_ISSUER", "https://example-test-issuer.invalid/auth/v1")
os.environ.setdefault("AUTH_AUDIENCE", "authenticated")

# A fixed, obviously-fake key so the storage tests can round-trip encrypted columns.
# setdefault, not a plain assignment: test_crypto.py drives its own keyring through
# monkeypatch and must not be pinned to this one.
os.environ.setdefault(
    "FINANCEBUDDY_ENCRYPTION_KEYS",
    "test:" + base64.b64encode(b"financebuddy-test-key-do-not-use").decode(),
)

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
    reason="needs Postgres - set TEST_DATABASE_URL (see ONBOARDING.md)",
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
        # `public` stays on the path as a fallback so extension functions remain
        # resolvable - gen_random_uuid() comes from pgcrypto, which is installed
        # once per database into public, not per schema. Tables still land in the
        # test schema because unqualified CREATE uses the first entry.
        conn.execute(f'SET search_path TO "{schema}", public')
        # Same reason as db._configure: the pool discards a connection returned
        # INTRANS, which surfaces as every checkout timing out.
        conn.commit()

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
    """
    Empty every table before a test, keeping the schema.

    Also clears the in-process caches that mirror those tables. Truncating alone is
    not enough: users.resolve() memoises (issuer, subject) -> user_id, so the next
    resolve returns a uuid whose row has just been deleted, and the first insert
    referencing it fails on the foreign key - several frames from the truncate that
    caused it. The session stores hold the same kind of stale state.
    """
    from shared import db, users
    from domains.mutual_funds import sessions as mf_sessions
    from domains.equity import sessions as eq_sessions
    from domains.tax_expert import tax_sessions

    with db.connect() as conn:
        conn.execute("TRUNCATE users, sessions RESTART IDENTITY CASCADE")

    users.invalidate()
    mf_sessions.clear_all()
    eq_sessions.clear_all()
    tax_sessions.clear_all()
    yield db_schema


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# HTTP-level authentication for route tests
# ---------------------------------------------------------------------------
# There is exactly one credential now: Authorization: Bearer <verified OIDC token>.
# Real signature verification (JWKS fetch, RS256, algorithm pinning, required
# exp/iss/aud) is exercised for real in test_oidc_verifier.py, which mints and
# verifies genuine RS256 tokens against a locally-generated key. Route-level tests
# want a *resolved identity*, not a second run through the crypto path, so
# OidcJwtVerifier.verify is replaced here with a parser for a fixed test scheme.

TEST_ISSUER = os.environ["AUTH_ISSUER"]


@pytest.fixture
def fake_bearer_auth(monkeypatch):
    """
    Returns `header(subject, email="", issuer=TEST_ISSUER) -> {"Authorization": ...}`.

    The fake "token" is `issuer|subject|email` - never a real JWT, and rejected
    outright by the real verify() if this fixture is not requested, so a test that
    forgets to authenticate gets a genuine 401 rather than an accidental pass.

    `issuer` defaults to TEST_ISSUER but can be overridden to match whatever a test
    already passed to `users.resolve(issuer, subject, ...)` directly.
    """
    from shared import oidc

    def fake_verify(self, token):
        if not token or token.count("|") != 2:
            return None
        issuer, subject, email = token.split("|")
        if not issuer or not subject:
            return None
        return oidc.Principal(issuer=issuer, subject=subject, email=email or None)

    monkeypatch.setattr(oidc.OidcJwtVerifier, "verify", fake_verify)

    def _header(subject: str, email: str = "", issuer: str = TEST_ISSUER) -> dict:
        return {"Authorization": f"Bearer {issuer}|{subject}|{email}"}

    return _header


@pytest.fixture
def signed_in(monkeypatch):
    """
    Authenticate without a database. Returns headers to pass to the client.

    For tests whose subject is not identity - cache counters, response headers -
    but which sit behind an auth check anyway. fake_bearer_auth is not usable
    there: it resolves a real account, which needs Postgres, and would drag
    otherwise-DB-free tests behind TEST_DATABASE_URL.

    Stubs the resolution step rather than the check, so the middleware, the
    ContextVar and the route's own `current_user_id()` all still run for real.
    """
    from shared import oidc, users
    from shared.identity import Caller

    caller = Caller(user_id="00000000-0000-0000-0000-0000000000ff", pan=None)
    monkeypatch.setattr(users, "resolve", lambda *a, **k: caller)
    monkeypatch.setattr(
        oidc.OidcJwtVerifier, "verify",
        lambda self, token: oidc.Principal(issuer=TEST_ISSUER, subject="stub-subject"),
    )
    return {"Authorization": "Bearer stub-token"}


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
