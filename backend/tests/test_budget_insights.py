"""
The analysis engines: transfers, accounts, recurring, forecast, anomalies,
reconciliation and the derived cache.

The transfer tests are the important ones. Without pairing, moving money between your
own accounts is counted as both income and expense, and every headline figure - savings
rate, monthly burn, the 50/30/20 split, which is a percentage *of income* - inflates
together. These pin the corrected arithmetic.
"""

import pandas as pd
import pytest

from domains.budget.accounts import (
    Account,
    account_key,
    kind_from_account_type,
    summarise_accounts,
)
from domains.budget.insights import (
    build_forecast,
    build_sankey,
    find_anomalies,
    find_recurring,
    reconcile_accounts,
)
from domains.budget.natures import nature_of
from domains.budget.planning import envelope_status
from domains.budget.transfers import detect_transfers, mark_transfers, split_real_flows


def _txn(txn_id, date, description, amount, kind, bank="HDFC",
         account_type="Savings Account", category="Uncategorized", balance=None):
    row = {
        "txn_id": txn_id, "date": date, "description": description, "amount": amount,
        "type": kind, "source_bank": bank, "account_type": account_type,
        "category": category, "notes": "",
    }
    if balance is not None:
        row["balance"] = balance
    return row


# ── transfers ─────────────────────────────────────────────────────────────────

@pytest.fixture
def multi_account():
    """Salary in, a self-transfer, a card purchase, its bill payment, a real expense."""
    return pd.DataFrame([
        _txn("a1", "2025-04-01", "SALARY APRIL", 120000.0, "credit", category="Salary/Income"),
        _txn("a2", "2025-04-02", "IMPS TRANSFER TO SELF", 50000.0, "debit"),
        _txn("b1", "2025-04-02", "IMPS FROM HDFC", 50000.0, "credit", bank="ICICI"),
        _txn("c1", "2025-04-05", "AMAZON", 8000.0, "debit",
             account_type="Credit Card", category="Shopping & Groceries"),
        _txn("a3", "2025-04-20", "CREDIT CARD PAYMENT", 8000.0, "debit"),
        _txn("c2", "2025-04-20", "PAYMENT RECEIVED", 8000.0, "credit", account_type="Credit Card"),
        _txn("a4", "2025-04-07", "SWIGGY", 1200.0, "debit", category="Food & Dining"),
    ])


def test_self_transfer_is_paired(multi_account):
    pairs = detect_transfers(multi_account)
    amounts = sorted(p.amount for p in pairs)
    assert amounts == [8000.0, 50000.0]


def test_transfers_are_excluded_from_income_and_expense(multi_account):
    df, pairs = mark_transfers(multi_account)
    real, internal = split_real_flows(df)

    income = real[real["type"] == "credit"]["amount"].sum()
    expense = real[real["type"] == "debit"]["amount"].sum()

    # Naively these are 178,000 and 67,200.
    assert income == pytest.approx(120000.0)
    assert expense == pytest.approx(9200.0)


def test_card_spend_is_counted_once_not_twice(multi_account):
    """
    The 8,000 Amazon purchase is spending. The 8,000 bill payment that settles it is
    not additional spending - it is the same money, moved.
    """
    df, _ = mark_transfers(multi_account)
    real, _ = split_real_flows(df)
    debits = real[real["type"] == "debit"]

    assert sorted(debits["description"]) == ["AMAZON", "SWIGGY"]
    assert debits["amount"].sum() == pytest.approx(9200.0)


def test_a_card_payment_is_identified_as_such(multi_account):
    pairs = detect_transfers(multi_account)
    card_payments = [p for p in pairs if p.is_card_payment]
    assert len(card_payments) == 1
    assert card_payments[0].amount == 8000.0


def test_a_payment_to_someone_else_is_not_a_transfer():
    """
    Only a matched pair reclassifies. A lone debit saying "TRANSFER" is a real expense -
    treating the narration as proof would silently delete money the user actually spent.
    """
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "IMPS TRANSFER TO RAHUL", 5000.0, "debit"),
        _txn("a2", "2025-04-01", "SALARY", 50000.0, "credit"),
    ])
    df, _ = mark_transfers(df)
    real, _ = split_real_flows(df)
    assert real[real["type"] == "debit"]["amount"].sum() == pytest.approx(5000.0)


def test_a_single_account_cannot_produce_a_transfer():
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER OUT", 5000.0, "debit"),
        _txn("a2", "2025-04-01", "TRANSFER IN", 5000.0, "credit"),
    ])
    assert detect_transfers(df) == []


def test_amounts_must_match_exactly():
    """A tolerance would pair a 5,000 rent payment with a 5,001 salary advance."""
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER", 5000.0, "debit"),
        _txn("b1", "2025-04-01", "RECEIVED", 5001.0, "credit", bank="ICICI"),
    ])
    assert detect_transfers(df) == []


def test_legs_too_far_apart_are_not_paired():
    df = pd.DataFrame([
        _txn("a1", "2025-04-01", "TRANSFER", 5000.0, "debit"),
        _txn("b1", "2025-04-30", "RECEIVED", 5000.0, "credit", bank="ICICI"),
    ])
    assert detect_transfers(df) == []


def test_a_user_override_beats_the_heuristic(multi_account):
    df, pairs = mark_transfers(multi_account, flags={"a2": "not_transfer", "b1": "not_transfer"})
    real, _ = split_real_flows(df)
    assert real[real["type"] == "debit"]["amount"].sum() == pytest.approx(59200.0)


# ── accounts and cards ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("Credit Card", "credit_card"), ("credit card", "credit_card"),
    ("Savings Account", "savings"), ("Current Account", "current"),
    ("Salary Account", "salary"), ("", "savings"), (None, "savings"),
])
def test_account_kind_mapping(label, expected):
    assert kind_from_account_type(label) == expected


def test_account_key_is_stable_and_distinguishes_accounts():
    assert account_key("HDFC", "Savings Account", "1234") == "HDFC:savings:1234"
    assert account_key("HDFC", "Savings Account", "1234") != account_key("HDFC", "Savings Account", "5678")
    assert account_key("hdfc", "Credit Card") == "HDFC:credit_card:-"


def test_card_outstanding_is_purchases_less_payments(multi_account):
    accounts = summarise_accounts(multi_account, meta={})
    card = next(a for a in accounts if a.is_card)
    assert card.outstanding == pytest.approx(0.0)  # 8000 spent, 8000 paid


def test_card_utilisation_and_status():
    card = Account(account_key="HDFC:credit_card:-", bank="HDFC", kind="credit_card",
                   credit_limit=100000.0, outflow=45000.0, inflow=0.0)
    assert card.utilisation == pytest.approx(0.45)
    assert card.utilisation_status == "warning"

    card.outflow = 60000.0
    assert card.utilisation_status == "critical"
    card.outflow = 10000.0
    assert card.utilisation_status == "healthy"


def test_a_deposit_account_has_no_outstanding():
    """A zero here would read as "nothing owed" rather than "not applicable"."""
    savings = Account(account_key="HDFC:savings:-", bank="HDFC", kind="savings")
    assert savings.outstanding is None
    assert savings.utilisation is None


def test_balance_prefers_the_printed_running_balance():
    account = Account(account_key="k", bank="HDFC", kind="savings",
                      opening_balance=1000.0, inflow=500.0, outflow=200.0,
                      closing_balance=9999.0)
    assert account.balance == pytest.approx(9999.0)


def test_balance_falls_back_to_opening_plus_flow():
    account = Account(account_key="k", bank="HDFC", kind="savings",
                      opening_balance=1000.0, inflow=500.0, outflow=200.0)
    assert account.balance == pytest.approx(1300.0)


# ── recurring ─────────────────────────────────────────────────────────────────

def _monthly(merchant, amounts, day=5):
    return pd.DataFrame([
        _txn(f"{merchant}{i}", f"2025-{i:02d}-{day:02d}", merchant, amount, "debit",
             category="Entertainment")
        for i, amount in enumerate(amounts, start=1)
    ])


def test_a_monthly_subscription_is_detected():
    found = find_recurring(_monthly("NETFLIX", [649.0] * 6))
    assert len(found) == 1
    assert found[0].cadence == "monthly"
    assert found[0].occurrences == 6


def test_a_price_rise_is_reported_not_split_into_two_subscriptions():
    """
    The whole point of the feature is "Netflix went from 499 to 649". An amount
    tolerance below that turns one subscription into two and reports no change at all.
    """
    found = find_recurring(_monthly("NETFLIX", [499.0, 499.0, 499.0, 649.0, 649.0, 649.0]))
    assert len(found) == 1
    changes = found[0].price_changes
    assert len(changes) == 1
    assert (changes[0]["from"], changes[0]["to"]) == (499.0, 649.0)
    assert changes[0]["change_pct"] == pytest.approx(30.1, abs=0.2)


def test_irregular_spending_is_not_a_subscription():
    """Three charges at one merchant are not a subscription unless they are regular."""
    df = pd.DataFrame([
        _txn("x1", "2025-01-03", "AMAZON", 800.0, "debit"),
        _txn("x2", "2025-01-19", "AMAZON", 800.0, "debit"),
        _txn("x3", "2025-04-27", "AMAZON", 800.0, "debit"),
    ])
    assert find_recurring(df) == []


def test_two_charges_are_not_enough():
    assert find_recurring(_monthly("NETFLIX", [649.0, 649.0])) == []


def test_a_stopped_subscription_is_marked_lapsed():
    df = _monthly("NETFLIX", [649.0] * 4)
    df = pd.concat([df, pd.DataFrame([
        _txn("later", "2025-10-01", "SWIGGY", 300.0, "debit")
    ])], ignore_index=True)
    found = [r for r in find_recurring(df) if r.merchant == "Netflix"]
    assert found and found[0].status == "lapsed"
    assert found[0].next_expected is None


def test_transfers_are_not_reported_as_subscriptions():
    df = _monthly("SIP TRANSFER", [5000.0] * 6)
    df["is_transfer"] = True
    assert find_recurring(df) == []


def test_annualised_cost_is_reported():
    found = find_recurring(_monthly("NETFLIX", [649.0] * 6))
    assert found[0].as_dict()["annualised_cost"] == pytest.approx(649 * 365 / 30, rel=0.01)


# ── forecast ──────────────────────────────────────────────────────────────────

def test_forecast_reports_low_confidence_without_history():
    df = pd.DataFrame([_txn("a", "2025-04-01", "SWIGGY", 100.0, "debit")])
    assert build_forecast(df, [])["confidence"] == "low"


def test_forecast_counts_upcoming_subscriptions_as_committed():
    rows = []
    for month in range(1, 7):
        rows.append(_txn(f"n{month}", f"2025-{month:02d}-25", "NETFLIX", 649.0, "debit"))
        rows.append(_txn(f"s{month}", f"2025-{month:02d}-01", "SALARY", 100000.0, "credit"))
    # Position "today" early in July, before the 25th, so July's charge is still ahead.
    rows.append(_txn("now", "2025-07-02", "SWIGGY", 300.0, "debit"))
    df = pd.DataFrame(rows)

    forecast = build_forecast(df, find_recurring(df))
    assert forecast["committed_upcoming_total"] == pytest.approx(649.0)
    assert forecast["committed_upcoming"][0]["merchant"] == "Netflix"


def test_safe_to_spend_is_never_negative():
    df = pd.DataFrame([
        _txn("s", "2025-04-01", "SALARY", 1000.0, "credit"),
        _txn("d", "2025-05-02", "RENT", 90000.0, "debit"),
    ])
    assert build_forecast(df, [])["safe_to_spend_daily"] >= 0


# ── anomalies ─────────────────────────────────────────────────────────────────

def test_a_duplicate_charge_is_flagged():
    df = pd.DataFrame([
        _txn("d1", "2025-06-10", "BIG STORE", 85000.0, "debit"),
        _txn("d2", "2025-06-10", "BIG STORE", 85000.0, "debit"),
    ])
    found = find_anomalies(df)
    assert any(a["type"] == "duplicate_charge" for a in found)


def test_small_repeats_are_not_flagged_as_duplicates():
    """Two coffees on one day are two coffees."""
    df = pd.DataFrame([
        _txn("d1", "2025-06-10", "STARBUCKS", 50.0, "debit"),
        _txn("d2", "2025-06-10", "STARBUCKS", 50.0, "debit"),
    ])
    assert not any(a["type"] == "duplicate_charge" for a in find_anomalies(df))


def test_a_category_spike_is_measured_against_its_own_history():
    rows = [
        _txn(f"m{m}", f"2025-{m:02d}-05", "RESTAURANT", 2000.0, "debit",
             category="Food & Dining")
        for m in range(1, 6)
    ]
    rows.append(_txn("spike", "2025-06-05", "RESTAURANT", 30000.0, "debit",
                     category="Food & Dining"))
    found = find_anomalies(pd.DataFrame(rows))
    assert any(a["type"] == "category_spike" and a["category"] == "Food & Dining" for a in found)


# ── reconciliation ────────────────────────────────────────────────────────────

def test_a_consistent_statement_reconciles():
    df = pd.DataFrame([
        _txn("a", "2025-04-01", "OPEN", 1000.0, "debit", balance=9000.0),
        _txn("b", "2025-04-02", "SPEND", 500.0, "debit", balance=8500.0),
        _txn("c", "2025-04-03", "SALARY", 2000.0, "credit", balance=10500.0),
    ])
    result = reconcile_accounts(df)
    assert result[0]["status"] == "reconciled"
    assert result[0]["break_count"] == 0


def test_a_missing_transaction_shows_up_as_a_break():
    """
    A gap between the printed balance and the transactions is how a dropped or
    misparsed row becomes visible instead of silently shrinking the totals.
    """
    df = pd.DataFrame([
        _txn("a", "2025-04-01", "OPEN", 1000.0, "debit", balance=9000.0),
        _txn("b", "2025-04-03", "SPEND", 500.0, "debit", balance=3000.0),
    ])
    result = reconcile_accounts(df)
    assert result[0]["status"] == "gaps_found"
    assert result[0]["unexplained_total"] == pytest.approx(5500.0)


def test_reconciliation_is_skipped_without_a_balance_column():
    df = pd.DataFrame([_txn("a", "2025-04-01", "SPEND", 500.0, "debit")])
    assert reconcile_accounts(df) == []


# ── envelopes ─────────────────────────────────────────────────────────────────

def test_envelope_pace_distinguishes_early_from_late():
    """60% of a budget is fine on the 25th and a problem on the 3rd."""
    early = pd.DataFrame([
        _txn("a", "2025-04-03", "RESTAURANT", 6000.0, "debit", category="Food & Dining")
    ])
    late = pd.DataFrame([
        _txn("a", "2025-04-25", "RESTAURANT", 6000.0, "debit", category="Food & Dining")
    ])
    caps = {"Food & Dining": 10000.0}

    assert envelope_status(early, caps)[0]["status"] == "ahead_of_pace"
    assert envelope_status(late, caps)[0]["status"] == "on_track"


def test_an_exceeded_envelope_is_over():
    df = pd.DataFrame([
        _txn("a", "2025-04-10", "RESTAURANT", 12000.0, "debit", category="Food & Dining")
    ])
    status = envelope_status(df, {"Food & Dining": 10000.0})[0]
    assert status["status"] == "over"
    assert status["remaining"] == 0.0


def test_an_untouched_envelope_still_appears():
    df = pd.DataFrame([_txn("a", "2025-04-10", "SWIGGY", 100.0, "debit", category="Other")])
    statuses = envelope_status(df, {"Travel": 5000.0})
    assert len(statuses) == 1 and statuses[0]["spent"] == 0.0


# ── natures and sankey ────────────────────────────────────────────────────────

@pytest.mark.parametrize("category,expected", [
    ("Utilities & Bills", "needs"), ("Food & Dining", "wants"),
    ("Investments", "investments"), ("Salary/Income", "income"),
    ("Interest Income", "income"),   # was dead: keyed with a capital I, looked up lowercased
    ("Credit Card Payment", "transfers"), ("Something Unseen", "wants"),
])
def test_nature_classification(category, expected):
    assert nature_of(category) == expected


def test_sankey_links_income_through_nature_to_category(multi_account):
    df, _ = mark_transfers(multi_account)
    diagram = build_sankey(df, nature_of)
    names = [n["name"] for n in diagram["nodes"]]
    assert "Income" in names
    assert diagram["links"]
    # Every link must reference a node that exists, or the diagram will not render.
    for link in diagram["links"]:
        assert 0 <= link["source"] < len(diagram["nodes"])
        assert 0 <= link["target"] < len(diagram["nodes"])
