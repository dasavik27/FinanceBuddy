"""
Dedup fingerprinting for equity uploads.

storage.compute_ledger_hash hashes transactions and only falls back to holdings when the
transaction frame is empty. That is right for a CAS, where the ledger *is* the data, and
wrong for equity in a way that quietly breaks the product: a tradebook changes only when
you trade, while holdings change with every price move. Hashing trades alone means a user
who re-syncs daily with an unchanged tradebook dedups onto their first upload forever and
never sees current holdings.

domains/equity/sessions._equity_ledger_hash hashes both frames. These tests pin the
properties that make it safe to key a unique constraint on.
"""

import pandas as pd

from domains.equity.sessions import _equity_ledger_hash as ledger_hash

TRADES = pd.DataFrame([
    {"date": pd.Timestamp("2025-06-10"), "symbol": "INFY", "type": "BUY",
     "quantity": 10, "price": 100.0},
])
HOLDINGS_A = pd.DataFrame([
    {"symbol": "INFY", "quantity": 10.0, "ltp": 100.0, "current_value": 1000.0},
])
HOLDINGS_B = pd.DataFrame([
    {"symbol": "INFY", "quantity": 99.0, "ltp": 555.0, "current_value": 54945.0},
])
EMPTY = pd.DataFrame()


def test_changed_holdings_are_not_treated_as_a_duplicate():
    """The regression this function exists for: same tradebook, different holdings."""
    assert ledger_hash(HOLDINGS_A, TRADES, "u") != ledger_hash(HOLDINGS_B, TRADES, "u")


def test_an_identical_upload_dedups():
    assert ledger_hash(HOLDINGS_A, TRADES, "u") == ledger_hash(HOLDINGS_A, TRADES, "u")


def test_holdings_only_upload_dedups_on_reupload():
    """Without a tradebook the shared helper returns a fresh uuid, so re-uploading the
    same CSV would fork a new session every time."""
    assert ledger_hash(HOLDINGS_A, EMPTY, "u") == ledger_hash(HOLDINGS_A, EMPTY, "u")


def test_the_same_portfolio_under_two_accounts_does_not_collide():
    """Dedup is a per-user optimisation; a hash match across accounts must never resolve
    to the other user's session."""
    assert ledger_hash(HOLDINGS_A, TRADES, "user-a") != ledger_hash(HOLDINGS_A, TRADES, "user-b")


def test_anonymous_uploads_are_deterministic_not_random():
    """A random hash would defeat dedup; it must still be stable for user_id=None."""
    assert ledger_hash(HOLDINGS_A, TRADES, None) == ledger_hash(HOLDINGS_A, TRADES, None)


def test_adding_a_tradebook_changes_the_fingerprint():
    assert ledger_hash(HOLDINGS_A, EMPTY, "u") != ledger_hash(HOLDINGS_A, TRADES, "u")


def test_row_order_does_not_change_the_fingerprint():
    """Brokers do not guarantee row order between exports of the same portfolio."""
    shuffled = pd.concat([HOLDINGS_A, HOLDINGS_B]).iloc[::-1]
    ordered = pd.concat([HOLDINGS_A, HOLDINGS_B])
    assert ledger_hash(shuffled, TRADES, "u") == ledger_hash(ordered, TRADES, "u")


def test_changed_trades_change_the_fingerprint():
    more = pd.concat([TRADES, pd.DataFrame([
        {"date": pd.Timestamp("2025-07-01"), "symbol": "TCS", "type": "SELL",
         "quantity": 5, "price": 300.0},
    ])], ignore_index=True)
    assert ledger_hash(HOLDINGS_A, TRADES, "u") != ledger_hash(HOLDINGS_A, more, "u")


def test_unhashable_column_content_still_produces_a_stable_hash():
    """Mixed types make hash_pandas_object raise; the fallback must be deterministic
    rather than random (which would disable dedup) or constant (which would collide)."""
    weird = pd.DataFrame([{"symbol": "X", "meta": {"a": 1}, "quantity": 1.0}])
    other = pd.DataFrame([{"symbol": "Y", "meta": {"a": 2}, "quantity": 2.0}])
    assert ledger_hash(weird, EMPTY, "u") == ledger_hash(weird, EMPTY, "u")
    assert ledger_hash(weird, EMPTY, "u") != ledger_hash(other, EMPTY, "u")


def test_hash_is_a_hex_digest_of_fixed_width():
    """It keys a unique constraint, so it must fit the column and never be empty."""
    h = ledger_hash(HOLDINGS_A, TRADES, "u")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
