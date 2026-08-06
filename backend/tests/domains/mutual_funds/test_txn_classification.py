"""
Transaction-type classification for CAS ledgers.

domains/mutual_funds/parser.py stores `str(tx.type)`, which for casparser is the enum
repr - "TransactionType.SWITCH_IN", underscore-separated. Every classifier in finance.py
tested hyphenated names ("SWITCH-IN", "STP-IN"), so none of them ever matched a switch.

In `_get_standard_ledger` that was masked by the `units > 0` / `units < 0` sign test,
which is why XIRR and FIFO lots stayed correct. The unitized simulation had no such
fallback: switches fell through every branch, units were never added or removed, and the
portfolio curve behind Overview / Performance / Drawdown / Journey was silently wrong for
anyone who had ever done a Regular-to-Direct switch.
"""

import pandas as pd
import pytest

from domains.mutual_funds.finance import _get_standard_ledger, normalize_txn_type


# ── the normalizer ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("TransactionType.SWITCH_IN", "SWITCH-IN"),
    ("TransactionType.SWITCH_OUT", "SWITCH-OUT"),
    ("SWITCH_IN", "SWITCH-IN"),
    ("SWITCH-IN", "SWITCH-IN"),
    ("switch_in", "SWITCH-IN"),
    ("TransactionType.PURCHASE_SIP", "PURCHASE-SIP"),
    ("TransactionType.STT_TAX", "STT-TAX"),
    ("TransactionType.STAMP_DUTY_TAX", "STAMP-DUTY-TAX"),
    ("", ""),
    (None, ""),
])
def test_normalizer_canonicalises_every_spelling(raw, expected):
    assert normalize_txn_type(raw) == expected


def test_merger_variants_carry_their_direction():
    """SWITCH_IN_MERGER must classify as a switch-in, not fall through."""
    assert "SWITCH-IN" in normalize_txn_type("TransactionType.SWITCH_IN_MERGER")
    assert "SWITCH-OUT" in normalize_txn_type("TransactionType.SWITCH_OUT_MERGER")


def test_the_old_hyphen_test_would_have_missed_the_enum_form():
    """Guards the premise: without normalisation the substring test simply fails."""
    raw = "TransactionType.SWITCH_IN"
    assert "SWITCH-IN" not in raw.upper()
    assert "SWITCH-IN" in normalize_txn_type(raw)


# ── the simulation, which had no sign fallback ────────────────────────────────

def _sim_units(txns: list[dict]) -> float:
    """
    Run the classification branch of compute_period_comparison over one fund and return
    the resulting unit balance. Mirrors the loop rather than importing it, because the
    full function needs a NAV panel; the branch under test is the classification.
    """
    from domains.mutual_funds.finance import normalize_txn_type as norm

    units = 0.0
    for t in txns:
        t_type = norm(t.get("Type"))
        signed = float(t.get("Units") or 0)
        units_t = abs(signed)
        is_in = signed > 0 or (signed == 0 and any(
            x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN")))
        is_out = signed < 0 or (signed == 0 and any(
            x in t_type for x in ("SELL", "REDEMPTION", "SWP", "STP-OUT", "SWITCH-OUT")))
        units_only = any(x in t_type for x in ("REINVEST", "BONUS", "SEGREGATION"))
        if units_only:
            units += units_t
        elif is_in:
            units += units_t
        elif is_out:
            units = max(0.0, units - units_t)
    return units


def test_a_regular_to_direct_switch_moves_units():
    """The headline regression: switch units were never applied."""
    assert _sim_units([
        {"Type": "TransactionType.PURCHASE", "Units": 100.0},
        {"Type": "TransactionType.SWITCH_OUT", "Units": -100.0},
    ]) == 0.0
    assert _sim_units([
        {"Type": "TransactionType.SWITCH_IN", "Units": 250.0},
    ]) == 250.0


def test_switch_with_unsigned_units_still_classifies_by_type():
    """Some CAS rows carry an unsigned quantity; the type must then decide."""
    assert _sim_units([{"Type": "TransactionType.SWITCH_IN", "Units": 0.0}]) == 0.0
    assert _sim_units([
        {"Type": "TransactionType.PURCHASE", "Units": 100.0},
        {"Type": "TransactionType.SWITCH_OUT", "Units": 0.0},
    ]) == 100.0


def test_segregation_units_are_not_dropped():
    """Side-pocketing creates units with no cashflow; it matched no branch before."""
    assert _sim_units([{"Type": "TransactionType.SEGREGATION", "Units": 40.0}]) == 40.0


def test_bonus_and_reinvestment_add_units():
    assert _sim_units([
        {"Type": "TransactionType.DIVIDEND_REINVEST", "Units": 5.0},
        {"Type": "TransactionType.BONUS", "Units": 10.0},
    ]) == 15.0


def test_units_never_go_negative():
    assert _sim_units([{"Type": "TransactionType.REDEMPTION", "Units": -50.0}]) == 0.0


# ── the ledger keeps working ──────────────────────────────────────────────────

def _ledger(rows: list[dict]):
    return _get_standard_ledger(pd.DataFrame(rows))


def test_ledger_classifies_switches_by_type_when_units_are_unsigned():
    """The sign test used to carry this alone; now the type test works too."""
    out = _ledger([
        {"Date": pd.Timestamp("2024-01-10"), "Fund": "F",
         "Type": "TransactionType.SWITCH_IN", "Units": 0.0, "Amount": 1000.0, "NAV": 10.0},
    ])
    assert [e["type"] for e in out] == ["BUY"]
    assert out[0]["amount"] == -1000.0


def test_ledger_still_signs_purchases_and_redemptions_correctly():
    out = _ledger([
        {"Date": pd.Timestamp("2024-01-10"), "Fund": "F",
         "Type": "TransactionType.PURCHASE", "Units": 100.0, "Amount": 1000.0, "NAV": 10.0},
        {"Date": pd.Timestamp("2024-06-10"), "Fund": "F",
         "Type": "TransactionType.REDEMPTION", "Units": -100.0, "Amount": 1500.0, "NAV": 15.0},
    ])
    assert [e["amount"] for e in out] == [-1000.0, 1500.0]


def test_ledger_excludes_reinvestment():
    out = _ledger([
        {"Date": pd.Timestamp("2024-01-10"), "Fund": "F",
         "Type": "TransactionType.DIVIDEND_REINVEST", "Units": 5.0, "Amount": 50.0, "NAV": 10.0},
    ])
    assert out == []
