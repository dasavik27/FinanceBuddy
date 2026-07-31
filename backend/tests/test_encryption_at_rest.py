"""
Proof that the encrypted columns actually contain ciphertext.

test_crypto.py verifies the primitive. These verify the *wiring*: that the columns
holding PAN, salary and holdings hold unreadable bytes on disk, and that the
application still reads them back correctly.

Worth having as a separate file because the failure mode is silent. A refactor that
writes plaintext to `metrics` would break nothing visible - every feature keeps
working, the data is simply exposed again. The only thing that catches it is looking
at the raw bytes, which is what these do.
"""

import uuid

import pandas as pd
import pytest

from shared import crypto, db, storage, users
from shared.identity import Caller, identity_scope

from tests.conftest import requires_db, TEST_ISSUER

pytestmark = requires_db


PAN = "ZZZZZ9999Z"
SALARY = 4_242_424
FUND = "Very Distinctive Fund Name"


@pytest.fixture
def owner(clean_db):
    return users.resolve(TEST_ISSUER, "at-rest-subject", pan=PAN)


def _raw(table: str, column: str, key_column: str, key_value) -> bytes:
    """The column exactly as the database holds it, with no application decoding."""
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT {column} FROM {table} WHERE {key_column} = %s", (key_value,)
        ).fetchone()
    assert row is not None, f"no row in {table}"
    return bytes(row[0]) if row[0] is not None else b""


def test_pan_is_not_readable_in_the_database(owner):
    stored = _raw("profiles", "pan_encrypted", "user_id", owner.user_id)

    assert stored, "no PAN stored at all - the test proves nothing"
    assert PAN.encode() not in stored
    assert PAN.lower().encode() not in stored
    assert stored.startswith(crypto.MAGIC), "column does not hold an encrypted value"

    # ...and the application still reads it.
    assert users.find_pan(owner.user_id) == PAN


def test_portfolio_metrics_are_not_readable_in_the_database(owner):
    """total_value is the user's net worth; it used to be a plain double column."""
    df_h = pd.DataFrame([{
        "Fund": FUND, "ISIN": "INF000000009", "Units": 1000.0, "NAV": 100.0,
        "Market Value": 987654.0, "Invested": 500000.0,
    }])
    sid = str(uuid.uuid4())
    storage.save_session(sid, df_h, pd.DataFrame(), pd.DataFrame(),
                         is_partial=False, user_id=owner.user_id)

    stored = _raw("sessions", "metrics", "session_id", sid)
    assert stored.startswith(crypto.MAGIC)
    assert b"987654" not in stored

    history = [h for h in storage.get_history(user_id=owner.user_id) if h["session_id"] == sid]
    assert history and history[0]["total_value"] == 987654.0


def test_holdings_are_not_readable_in_the_database(owner):
    df_h = pd.DataFrame([{
        "Fund": FUND, "ISIN": "INF000000009", "Units": 1000.0, "NAV": 100.0,
        "Market Value": 100000.0, "Invested": 90000.0,
    }])
    sid = str(uuid.uuid4())
    storage.save_session(sid, df_h, pd.DataFrame(), pd.DataFrame(),
                         is_partial=False, user_id=owner.user_id)

    stored = _raw("session_payloads", "holdings", "session_id", sid)
    assert stored.startswith(crypto.MAGIC)
    # The payload is compressed before encryption, so the fund name would not appear
    # verbatim even in plaintext - but zlib leaves short literals recoverable, and an
    # unencrypted blob decompresses trivially. Both checks, so neither alone carries it.
    assert FUND.encode() not in stored
    import zlib
    with pytest.raises(zlib.error):
        zlib.decompress(stored)

    loaded = storage.load_session(sid)
    assert loaded is not None and loaded[0]["Fund"].iloc[0] == FUND


def test_ais_document_is_not_readable_in_the_database(owner):
    """The tax payload carries salary, capital gains and deductions."""
    from domains.tax_expert import tax_sessions

    with identity_scope(owner):
        sid = tax_sessions.create_tax_session({
            "fy": "2025-26",
            "personal": {"pan": PAN, "name": "At Rest"},
            "salary": {"gross": SALARY},
        })

    stored = _raw("tax_payloads", "data", "session_id", sid)
    assert stored.startswith(crypto.MAGIC)
    assert str(SALARY).encode() not in stored
    assert PAN.encode() not in stored

    with identity_scope(owner):
        assert tax_sessions.get_tax_session(sid)["ais_data"]["salary"]["gross"] == SALARY


def test_tax_summary_metrics_are_not_readable_in_the_database(owner):
    """gross_salary is denormalised onto the registry row for the history timeline."""
    from domains.tax_expert import tax_sessions

    with identity_scope(owner):
        sid = tax_sessions.create_tax_session({
            "fy": "2025-26",
            "personal": {"pan": PAN, "name": "At Rest"},
            "salary": {"gross": SALARY},
        })

    stored = _raw("sessions", "metrics", "session_id", sid)
    assert stored.startswith(crypto.MAGIC)
    assert str(SALARY).encode() not in stored

    listed = tax_sessions.get_sessions_by_user(owner.user_id)
    assert listed and listed[0]["gross_salary"] == SALARY


def test_a_payload_moved_to_another_session_will_not_decrypt(owner):
    """
    The transplant attack, end to end.

    Someone with write access to the database but no key copies one session's
    encrypted holdings into another session's row. Encryption alone would not notice;
    the associated-data binding to session_id is what makes it fail.
    """
    df_h = pd.DataFrame([{
        "Fund": FUND, "ISIN": "INF000000009", "Units": 1.0, "NAV": 1.0,
        "Market Value": 1.0, "Invested": 1.0,
    }])
    victim = str(uuid.uuid4())
    attacker = str(uuid.uuid4())
    storage.save_session(victim, df_h, pd.DataFrame(), pd.DataFrame(),
                         is_partial=False, user_id=owner.user_id)
    storage.save_session(attacker, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                         is_partial=False, user_id=owner.user_id)

    with db.connect() as conn:
        conn.execute(
            """
            UPDATE session_payloads SET holdings = (
                SELECT holdings FROM session_payloads WHERE session_id = %s
            ) WHERE session_id = %s
            """,
            (victim, attacker),
        )

    with pytest.raises(crypto.DecryptionFailed):
        storage.load_session(attacker)
