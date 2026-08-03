"""Tests for account status and role at provisioning time."""

import pytest

from shared import db, users
from tests.conftest import requires_db, TEST_ISSUER

pytestmark = requires_db


@pytest.fixture(autouse=True)
def clear_user_cache():
    users.invalidate()
    yield
    users.invalidate()


def test_new_signup_is_pending_without_approval(clean_db):
    caller = users.resolve(TEST_ISSUER, "pending-user", email="new@example.test")
    assert caller.status == "pending"
    assert caller.role == "user"


def test_approved_access_request_grants_active_status(clean_db):
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO access_requests (email, name, status)
            VALUES ('approved@example.test', 'Approved User', 'approved')
            """
        )

    caller = users.resolve(TEST_ISSUER, "approved-user", email="approved@example.test")
    assert caller.status == "active"
    assert caller.role == "user"


def test_admin_email_gets_admin_role(clean_db, monkeypatch):
    monkeypatch.setenv("FINANCEBUDDY_ADMIN_EMAILS", "admin@example.test")

    caller = users.resolve(TEST_ISSUER, "admin-user", email="admin@example.test")
    assert caller.status == "active"
    assert caller.role == "admin"


def test_activate_by_email_promotes_pending_account(clean_db):
    caller = users.resolve(TEST_ISSUER, "later-approved", email="later@example.test")
    assert caller.status == "pending"

    users.activate_by_email("later@example.test")

    caller = users.resolve(TEST_ISSUER, "later-approved", email="later@example.test")
    assert caller.status == "active"
