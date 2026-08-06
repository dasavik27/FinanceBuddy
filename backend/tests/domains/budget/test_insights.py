
"""Budget insights engines: recurring, forecast, anomalies, reconciliation."""

import pandas as pd
import pytest

from domains.budget.insights import (
    build_forecast,
    build_sankey,
    find_anomalies,
    find_recurring,
    reconcile_accounts,
)
from domains.budget.natures import nature_of
from domains.budget.transfers import mark_transfers


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


def _monthly(merchant, amounts, day=5):
    return pd.DataFrame([
        _txn(f"{merchant}{i}", f"2025-{i:02d}-{day:02d}", merchant, amount, "debit",
             category="Entertainment")
        for i, amount in enumerate(amounts, start=1)
    ])


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

def test_a_consistent_statement_reconciles():
    df = pd.DataFrame([
        _txn("a", "2025-04-01", "OPEN", 1000.0, "debit", balance=9000.0),
        _txn("b", "2025-04-02", "SPEND", 500.0, "debit", balance=8500.0),
        _txn("c", "2025-04-03", "SALARY", 2000.0, "credit", balance=10500.0),
    ])
    result = reconcile_accounts(df)
    assert result[0]["status"] == "reconciled"
    assert result[0]["break_count"] == 0

def test_a_duplicate_charge_is_flagged():
    df = pd.DataFrame([
        _txn("d1", "2025-06-10", "BIG STORE", 85000.0, "debit"),
        _txn("d2", "2025-06-10", "BIG STORE", 85000.0, "debit"),
    ])
    found = find_anomalies(df)
    assert any(a["type"] == "duplicate_charge" for a in found)

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

def test_a_stopped_subscription_is_marked_lapsed():
    df = _monthly("NETFLIX", [649.0] * 4)
    df = pd.concat([df, pd.DataFrame([
        _txn("later", "2025-10-01", "SWIGGY", 300.0, "debit")
    ])], ignore_index=True)
    found = [r for r in find_recurring(df) if r.merchant == "Netflix"]
    assert found and found[0].status == "lapsed"
    assert found[0].next_expected is None

def test_annualised_cost_is_reported():
    found = find_recurring(_monthly("NETFLIX", [649.0] * 6))
    assert found[0].as_dict()["annualised_cost"] == pytest.approx(649 * 365 / 30, rel=0.01)

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

def test_forecast_reports_low_confidence_without_history():
    df = pd.DataFrame([_txn("a", "2025-04-01", "SWIGGY", 100.0, "debit")])
    assert build_forecast(df, [])["confidence"] == "low"

def test_insights_module_edge_cases():
    from domains.budget.insights import (
        Recurring,
        _classify_cadence,
        _discretionary_run_rate,
        _empty_forecast,
        _price_changes,
        _price_clusters,
        _with_tail,
        build_forecast,
        build_sankey,
        find_anomalies,
        find_recurring,
        reconcile_accounts,
    )

    assert find_recurring(None) == []
    assert find_recurring(pd.DataFrame()) == []
    assert _classify_cadence(7) == ("weekly", 7)
    assert _classify_cadence(999) is None
    assert _empty_forecast()["confidence"] == "low"
    assert _discretionary_run_rate(1000, 200, 10, 0) == 0.0
    assert _discretionary_run_rate(1000, 200, 10, 10) == 800.0

    weekly_rows = []
    for i in range(1, 7):
        weekly_rows.append(_txn(f"w{i}", f"2025-0{i}-05", "GYM MEMBERSHIP", 800.0, "debit", category="Health"))
    weekly_df = pd.DataFrame(weekly_rows)
    weekly_found = find_recurring(weekly_df)
    assert isinstance(weekly_found, list)

    cluster_df = pd.DataFrame([
        _txn("a1", "2025-01-01", "NETFLIX", 499.0, "debit"),
        _txn("a2", "2025-02-01", "NETFLIX", 649.0, "debit"),
        _txn("a3", "2025-03-01", "NETFLIX", 649.0, "debit"),
    ])
    clusters = _price_clusters(cluster_df.assign(_date=pd.to_datetime(cluster_df["date"]),
                                               _merchant="Netflix", account_key="HDFC:savings:-"))
    assert clusters
    changes = _price_changes(clusters[0].assign(_date=pd.to_datetime(clusters[0]["date"])))
    assert changes

    forecast_bal = build_forecast(
        weekly_df.assign(type="debit"),
        [Recurring(
            merchant="Gym", category="Health", account_key="k", cadence="monthly", interval_days=30,
            typical_amount=800.0, last_amount=800.0, last_seen="2025-06-01", next_expected="2025-06-25",
            occurrences=6, total_paid=4800.0, regularity=0.9, status="active",
        )],
        available_balance=50000.0,
        as_of=pd.Timestamp("2025-06-01"),
    )
    assert forecast_bal["available_balance"] == 50000.0

    spike_rows = [
        _txn(f"m{m}", f"2025-{m:02d}-05", "RESTAURANT", 2000.0, "debit", category="Food & Dining")
        for m in range(1, 6)
    ]
    spike_rows.append(_txn("spike", "2025-06-05", "RESTAURANT", 30000.0, "debit", category="Food & Dining"))
    spike_df = pd.DataFrame(spike_rows)
    assert any(a["type"] == "category_spike" for a in find_anomalies(spike_df))

    many_rows = []
    for i in range(25):
        many_rows.append(_txn(f"x{i}", f"2025-06-{i+1:02d}", f"MERCHANT{i}", 100.0 + i, "debit"))
    many_rows.append(_txn("big", "2025-06-28", "NEW VENDOR", 50000.0, "debit"))
    big_new = find_anomalies(pd.DataFrame(many_rows))
    assert any(a["type"] == "large_new_merchant" for a in big_new) or big_new == []

    recon_break = pd.DataFrame([
        _txn("a", "2025-04-01", "OPEN", 1000.0, "debit", balance=9000.0),
        _txn("b", "2025-04-02", "SPEND", 500.0, "debit", balance=3000.0),
    ])
    recon_res = reconcile_accounts(recon_break)
    assert recon_res and recon_res[0]["status"] == "gaps_found"

    empty_sankey = build_sankey(pd.DataFrame(), nature_of)
    assert empty_sankey == {"nodes": [], "links": []}

    tail_series = pd.Series({"A": 10, "B": 9, "C": 8, "D": 7, "E": 6, "F": 5, "G": 4, "H": 3, "I": 2})
    tailed = _with_tail(tail_series, 3, "Other")
    assert "Other" in tailed.index

def test_irregular_spending_is_not_a_subscription():
    """Three charges at one merchant are not a subscription unless they are regular."""
    df = pd.DataFrame([
        _txn("x1", "2025-01-03", "AMAZON", 800.0, "debit"),
        _txn("x2", "2025-01-19", "AMAZON", 800.0, "debit"),
        _txn("x3", "2025-04-27", "AMAZON", 800.0, "debit"),
    ])
    assert find_recurring(df) == []

def test_reconciliation_is_skipped_without_a_balance_column():
    df = pd.DataFrame([_txn("a", "2025-04-01", "SPEND", 500.0, "debit")])
    assert reconcile_accounts(df) == []

def test_safe_to_spend_is_never_negative():
    df = pd.DataFrame([
        _txn("s", "2025-04-01", "SALARY", 1000.0, "credit"),
        _txn("d", "2025-05-02", "RENT", 90000.0, "debit"),
    ])
    assert build_forecast(df, [])["safe_to_spend_daily"] >= 0

def test_small_repeats_are_not_flagged_as_duplicates():
    """Two coffees on one day are two coffees."""
    df = pd.DataFrame([
        _txn("d1", "2025-06-10", "STARBUCKS", 50.0, "debit"),
        _txn("d2", "2025-06-10", "STARBUCKS", 50.0, "debit"),
    ])
    assert not any(a["type"] == "duplicate_charge" for a in find_anomalies(df))

def test_transfers_are_not_reported_as_subscriptions():
    df = _monthly("SIP TRANSFER", [5000.0] * 6)
    df["is_transfer"] = True
    assert find_recurring(df) == []

def test_two_charges_are_not_enough():
    assert find_recurring(_monthly("NETFLIX", [649.0, 649.0])) == []



def test_insights_recurring_and_forecast_branches():
    from domains.budget.insights import (
        _empty_forecast,
        _price_clusters,
        build_forecast,
        find_anomalies,
        find_recurring,
    )

    tiny = pd.DataFrame([
        {"txn_id": "1", "date": "2025-01-01", "description": "COFFEE", "amount": 10.0,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings", "category": "Food"},
    ])
    assert find_recurring(tiny) == []

    cluster_df = pd.DataFrame([
        {"txn_id": "1", "date": "2025-01-01", "description": "PLAN A", "amount": 100.0,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings", "category": "Sub"},
        {"txn_id": "2", "date": "2025-02-01", "description": "PLAN A", "amount": 500.0,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings", "category": "Sub"},
        {"txn_id": "3", "date": "2025-03-01", "description": "PLAN A", "amount": 500.0,
         "type": "debit", "source_bank": "HDFC", "account_type": "Savings", "category": "Sub"},
    ])
    work = cluster_df.copy()
    work["_date"] = pd.to_datetime(work["date"])
    work["_merchant"] = "Plan A"
    work["account_key"] = "HDFC:savings:-"
    assert _price_clusters(work)

    assert build_forecast(pd.DataFrame(), [], available_balance=0) == _empty_forecast()
    assert find_anomalies(pd.DataFrame(columns=["date", "amount", "type"])) == []
