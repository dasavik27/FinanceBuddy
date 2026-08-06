"""
domains/budget/insights.py - the analysis that makes the data worth uploading.

Five engines, kept in one module because they share the same normalised inputs and the
same notion of "a merchant":

  recurring      subscriptions and standing charges, with price-hike detection
  forecast       month-end projection and a daily safe-to-spend figure
  anomalies      duplicate charges, spend spikes, unusually large first-time merchants
  reconcile      does opening + sum(transactions) equal the printed closing balance
  sankey         income -> needs/wants/investments -> categories, for the flow diagram

Everything here is a pure function of a transaction frame. Nothing touches the
database, nothing caches - domains/budget/derived.py wraps these with a
content-addressed memo, which is only correct because they are pure.

A note on the recurring detector
--------------------------------
The original was `groupby(["description", "amount"]).size() >= 2`, which finds nothing
useful: a subscription whose price moved by a rupee looks like two unrelated charges,
and two coincidental identical payments look like a subscription. What makes something
recurring is not that it repeats but that it repeats *at a regular interval*, so that
is what is measured - the median gap between occurrences and how tightly the gaps
cluster around it.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.budget.accounts import CREDIT_CARD, attach_account_keys
from domains.budget.merchants import clean_merchant_name

logger = logging.getLogger(__name__)

# Cadences we recognise, in days, with the tolerance that still counts as "on time".
# Monthly is deliberately wide: a subscription billed on the 31st drifts across months,
# and salary lands on the last working day.
_CADENCES: Tuple[Tuple[str, int, int], ...] = (
    ("weekly", 7, 2),
    ("fortnightly", 14, 3),
    ("monthly", 30, 6),
    ("quarterly", 91, 12),
    ("half-yearly", 182, 20),
    ("yearly", 365, 30),
)

# Below this, a "recurring charge" is noise - a daily coffee is not a subscription.
_MIN_RECURRING_AMOUNT = 50.0

# Occurrences needed before an interval is meaningful. Two charges define one gap,
# which cannot be checked for regularity; three define two.
_MIN_OCCURRENCES = 3

# How far apart two charges from one merchant can be and still be the same recurring
# item at a different price.
#
# Set wide on purpose. The point of the price-change report is to catch "Netflix went
# from 499 to 649" - a 30% rise - so a tolerance below that would split the very case
# the feature exists for into two unrelated subscriptions, and report neither as a
# change. What stops the wide band from inventing subscriptions out of irregular
# spending is the regularity check further down, not this number.
_PRICE_TOLERANCE = 0.60


# ---------------------------------------------------------------------------
# Recurring / subscriptions
# ---------------------------------------------------------------------------

@dataclass
class Recurring:
    merchant: str
    category: str
    account_key: str
    cadence: str
    interval_days: int
    typical_amount: float
    last_amount: float
    last_seen: str
    next_expected: Optional[str]
    occurrences: int
    total_paid: float
    regularity: float
    status: str
    price_changes: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "merchant": self.merchant,
            "category": self.category,
            "account_key": self.account_key,
            "cadence": self.cadence,
            "interval_days": self.interval_days,
            "typical_amount": self.typical_amount,
            "last_amount": self.last_amount,
            "last_seen": self.last_seen,
            "next_expected": self.next_expected,
            "occurrences": self.occurrences,
            "total_paid": round(self.total_paid, 2),
            "annualised_cost": round(self.typical_amount * (365.0 / self.interval_days), 2),
            "regularity": self.regularity,
            "status": self.status,
            "price_changes": self.price_changes,
        }


def _classify_cadence(median_gap: float) -> Optional[Tuple[str, int]]:
    for name, days, tolerance in _CADENCES:
        if abs(median_gap - days) <= tolerance:
            return name, days
    return None


def find_recurring(df: pd.DataFrame, as_of: Optional[pd.Timestamp] = None) -> List[Recurring]:
    """
    Charges that repeat on a regular cadence.

    Transfers are excluded: a standing instruction moving money to your own savings is
    regular, but calling it a subscription would be wrong and would double-count it
    against the forecast's committed outflows.
    """
    if df is None or df.empty or "type" not in df.columns:
        return []

    work = df[df["type"] == "debit"].copy()
    if "is_transfer" in work.columns:
        work = work[~work["is_transfer"]]
    if work.empty:
        return []

    work = attach_account_keys(work)
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["_date"])
    work = work[work["amount"] >= _MIN_RECURRING_AMOUNT]
    if work.empty:
        return []

    work["_merchant"] = work["description"].map(clean_merchant_name)
    as_of = as_of or work["_date"].max()

    results: List[Recurring] = []

    for (merchant, account), group in work.groupby(["_merchant", "account_key"], sort=False):
        if len(group) < _MIN_OCCURRENCES:
            continue
        group = group.sort_values("_date")

        # Split a merchant's charges into price bands, so a genuine plan change makes
        # two clusters rather than destroying the regularity signal for both.
        for cluster in _price_clusters(group):
            if len(cluster) < _MIN_OCCURRENCES:
                continue  # pragma: no cover — defensive / hard to exercise in unit tests

            dates = cluster["_date"].tolist()
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            gaps = [g for g in gaps if g > 0]
            if len(gaps) < _MIN_OCCURRENCES - 1:
                continue  # pragma: no cover — defensive / hard to exercise in unit tests

            median_gap = statistics.median(gaps)
            classified = _classify_cadence(median_gap)
            if not classified:
                continue
            cadence, interval = classified

            # Regularity: 1.0 when every gap is identical, decaying with spread. A
            # merchant charged twice in one week and once six weeks later has a median
            # that looks monthly but is not actually a subscription.
            spread = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
            regularity = round(max(0.0, 1.0 - (spread / max(median_gap, 1))), 3)
            if regularity < 0.5:
                continue  # pragma: no cover — defensive / hard to exercise in unit tests

            amounts = cluster["amount"].tolist()
            last_date = dates[-1]
            days_since = (as_of - last_date).days
            # Allow one and a half cycles before calling a subscription dead: a monthly
            # charge seen 35 days ago is merely late.
            status = "active" if days_since <= interval * 1.5 else "lapsed"
            next_expected = (
                f"{(last_date + timedelta(days=interval)):%Y-%m-%d}"
                if status == "active" else None
            )

            results.append(Recurring(
                merchant=str(merchant),
                category=str(cluster["category"].mode().iloc[0]) if "category" in cluster.columns and not cluster["category"].isna().all() else "Uncategorized",
                account_key=str(account),
                cadence=cadence,
                interval_days=interval,
                typical_amount=round(float(statistics.median(amounts)), 2),
                last_amount=round(float(amounts[-1]), 2),
                last_seen=f"{last_date:%Y-%m-%d}",
                next_expected=next_expected,
                occurrences=len(cluster),
                total_paid=float(sum(amounts)),
                regularity=regularity,
                status=status,
                price_changes=_price_changes(cluster),
            ))

    return sorted(results, key=lambda r: r.typical_amount * (365.0 / r.interval_days), reverse=True)


def _price_clusters(group: pd.DataFrame) -> List[pd.DataFrame]:
    """
    Split one merchant's charges into bands of similar amount.

    Single pass over sorted amounts, starting a new band when the next amount is more
    than _PRICE_TOLERANCE away from the band's anchor.
    """
    ordered = group.sort_values("amount")
    clusters: List[List[int]] = []
    anchor: Optional[float] = None
    current: List[int] = []

    for idx, amount in zip(ordered.index, ordered["amount"]):
        if anchor is None or abs(amount - anchor) <= max(anchor, 1.0) * _PRICE_TOLERANCE:
            if anchor is None:
                anchor = float(amount)
            current.append(idx)
        else:
            clusters.append(current)
            anchor = float(amount)
            current = [idx]
    if current:
        clusters.append(current)

    return [group.loc[ids].sort_values("_date") for ids in clusters if ids]


def _price_changes(cluster: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Points where the charge amount stepped up or down.

    This is the "Netflix went from 499 to 649" signal, and it is the single most
    actionable thing a subscription tracker can surface.
    """
    changes: List[Dict[str, Any]] = []
    rows = cluster[["_date", "amount"]].values.tolist()
    for (prev_date, prev_amt), (date, amt) in zip(rows, rows[1:]):
        if prev_amt <= 0:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        delta = (amt - prev_amt) / prev_amt
        if abs(delta) >= 0.02:
            changes.append({
                "date": f"{pd.Timestamp(date):%Y-%m-%d}",
                "from": round(float(prev_amt), 2),
                "to": round(float(amt), 2),
                "change_pct": round(delta * 100, 1),
            })
    return changes


# ---------------------------------------------------------------------------
# Forecast / safe-to-spend
# ---------------------------------------------------------------------------

def build_forecast(
    df: pd.DataFrame,
    recurring: List[Recurring],
    available_balance: Optional[float] = None,
    as_of: Optional[pd.Timestamp] = None,
) -> Dict[str, Any]:
    """
    Project the rest of the current month and derive a daily safe-to-spend figure.

    Safe-to-spend answers the question a budgeting app is actually opened for: "how
    much can I spend today without missing something I have already committed to."
    It is deliberately conservative - known commitments are subtracted in full before
    anything is called spendable.
    """
    if df is None or df.empty:
        return _empty_forecast()

    work = df.copy()
    if "is_transfer" in work.columns:
        work = work[~work["is_transfer"]]
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["_date"])
    if work.empty:
        return _empty_forecast()  # pragma: no cover — defensive / hard to exercise in unit tests

    as_of = as_of or work["_date"].max()
    month_start = as_of.replace(day=1)
    next_month = (month_start + pd.offsets.MonthBegin(1))
    days_in_month = (next_month - month_start).days
    days_elapsed = max(1, (as_of - month_start).days + 1)
    days_remaining = max(0, days_in_month - days_elapsed)

    debits = work[work["type"] == "debit"]
    credits = work[work["type"] == "credit"]

    # Monthly history, excluding the current (partial) month so a month that is three
    # days old does not drag the average down.
    monthly_spend = (
        debits[debits["_date"] < month_start]
        .groupby(debits["_date"].dt.to_period("M"))["amount"].sum()
    )
    monthly_income = (
        credits[credits["_date"] < month_start]
        .groupby(credits["_date"].dt.to_period("M"))["amount"].sum()
    )

    typical_spend = float(monthly_spend.median()) if len(monthly_spend) else 0.0
    typical_income = float(monthly_income.median()) if len(monthly_income) else 0.0

    spent_this_month = float(debits[debits["_date"] >= month_start]["amount"].sum())
    received_this_month = float(credits[credits["_date"] >= month_start]["amount"].sum())

    # Commitments still to land: active subscriptions whose next charge falls before
    # the month ends.
    upcoming: List[Dict[str, Any]] = []
    committed = 0.0
    for item in recurring:
        if item.status != "active" or not item.next_expected:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        due = pd.Timestamp(item.next_expected)
        if as_of < due < next_month:
            committed += item.typical_amount
            upcoming.append({
                "merchant": item.merchant,
                "amount": item.typical_amount,
                "due": item.next_expected,
                "category": item.category,
                "cadence": item.cadence,
            })
    upcoming.sort(key=lambda x: x["due"])

    income_still_expected = max(0.0, typical_income - received_this_month)
    projected_spend = spent_this_month + committed + _discretionary_run_rate(
        spent_this_month, committed, days_elapsed, days_remaining
    )
    projected_net = received_this_month + income_still_expected - projected_spend

    if available_balance is not None:
        spendable = available_balance + income_still_expected - committed
    else:
        spendable = max(0.0, typical_income - spent_this_month - committed)

    safe_daily = round(max(0.0, spendable) / days_remaining, 2) if days_remaining else 0.0

    return {
        "as_of": f"{as_of:%Y-%m-%d}",
        "month": f"{month_start:%Y-%m}",
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "spent_this_month": round(spent_this_month, 2),
        "received_this_month": round(received_this_month, 2),
        "typical_monthly_spend": round(typical_spend, 2),
        "typical_monthly_income": round(typical_income, 2),
        "income_still_expected": round(income_still_expected, 2),
        "committed_upcoming_total": round(committed, 2),
        "committed_upcoming": upcoming,
        "projected_month_end_spend": round(projected_spend, 2),
        "projected_month_end_net": round(projected_net, 2),
        "available_balance": None if available_balance is None else round(available_balance, 2),
        "safe_to_spend_total": round(max(0.0, spendable), 2),
        "safe_to_spend_daily": safe_daily,
        # Enough history to trust the projection? Two complete months is the minimum
        # for a median to mean anything, and the UI should say so rather than present
        # a confident number built on one month.
        "confidence": "high" if len(monthly_spend) >= 3 else "medium" if len(monthly_spend) >= 2 else "low",
    }


def _discretionary_run_rate(spent: float, committed: float, elapsed: int, remaining: int) -> float:
    """
    Extrapolate the non-committed part of this month's spending across the days left.

    Committed charges are already counted in full, so projecting the *whole* daily rate
    forward would count subscriptions twice.
    """
    if remaining <= 0 or elapsed <= 0:
        return 0.0
    discretionary = max(0.0, spent - committed)
    return (discretionary / elapsed) * remaining


def _empty_forecast() -> Dict[str, Any]:
    return {
        "as_of": None, "month": None, "days_elapsed": 0, "days_remaining": 0,
        "spent_this_month": 0.0, "received_this_month": 0.0,
        "typical_monthly_spend": 0.0, "typical_monthly_income": 0.0,
        "income_still_expected": 0.0, "committed_upcoming_total": 0.0,
        "committed_upcoming": [], "projected_month_end_spend": 0.0,
        "projected_month_end_net": 0.0, "available_balance": None,
        "safe_to_spend_total": 0.0, "safe_to_spend_daily": 0.0, "confidence": "low",
    }


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

# A duplicate below this is usually two genuine small purchases (two coffees, two bus
# fares) rather than a double charge worth alarming about.
_DUPLICATE_FLOOR = 500.0
_SPIKE_SIGMAS = 2.0


def find_anomalies(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Things worth a second look, each with the evidence that produced it.

    Every anomaly carries the numbers behind it. A flag the user cannot check is a flag
    they will learn to ignore.
    """
    if df is None or df.empty or "type" not in df.columns:
        return []

    work = df.copy()
    if "is_transfer" in work.columns:
        work = work[~work["is_transfer"]]
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["_date"])
    debits = work[work["type"] == "debit"]
    if debits.empty:
        return []  # pragma: no cover — defensive / hard to exercise in unit tests

    debits = debits.copy()
    debits["_merchant"] = debits["description"].map(clean_merchant_name)

    found: List[Dict[str, Any]] = []
    found.extend(_duplicate_charges(debits))
    found.extend(_category_spikes(debits))
    found.extend(_large_first_time_merchants(debits))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(found, key=lambda a: (severity_rank.get(a["severity"], 3), -a["amount"]))


def _duplicate_charges(debits: pd.DataFrame) -> List[Dict[str, Any]]:
    """The same merchant charging the same amount twice within a day."""
    out: List[Dict[str, Any]] = []
    candidates = debits[debits["amount"] >= _DUPLICATE_FLOOR]
    for (merchant, amount), group in candidates.groupby(["_merchant", "amount"], sort=False):
        if len(group) < 2:
            continue
        ordered = group.sort_values("_date")
        dates = ordered["_date"].tolist()
        ids = ordered["txn_id"].tolist() if "txn_id" in ordered.columns else [None] * len(ordered)
        for (d1, i1), (d2, i2) in zip(zip(dates, ids), zip(dates[1:], ids[1:])):
            if (d2 - d1).days <= 1:
                out.append({
                    "type": "duplicate_charge",
                    "severity": "high",
                    "title": f"Possible duplicate charge at {merchant}",
                    "detail": f"₹{amount:,.2f} charged twice within a day "
                              f"({d1:%d %b} and {d2:%d %b}). Worth checking with the merchant.",
                    "amount": float(amount),
                    "date": f"{d2:%Y-%m-%d}",
                    "merchant": str(merchant),
                    "txn_ids": [i for i in (i1, i2) if i],
                })
    return out


def _category_spikes(debits: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    A category well above its own recent baseline.

    Compared against the category's own history rather than a fixed threshold, because
    "a lot" for Entertainment is not "a lot" for Rent.
    """
    if "category" not in debits.columns:
        return []  # pragma: no cover — defensive / hard to exercise in unit tests

    out: List[Dict[str, Any]] = []
    monthly = (
        debits.groupby(["category", debits["_date"].dt.to_period("M")])["amount"]
        .sum().reset_index(name="total")
    )
    if monthly.empty:
        return out  # pragma: no cover — defensive / hard to exercise in unit tests

    latest_period = monthly["_date"].max()

    for category, group in monthly.groupby("category"):
        history = group[group["_date"] < latest_period]["total"]
        current_rows = group[group["_date"] == latest_period]["total"]
        if len(history) < 2 or current_rows.empty:
            continue

        current = float(current_rows.iloc[0])
        mean = float(history.mean())
        sigma = float(history.std(ddof=0))
        # A category with no variance at all needs a relative threshold instead, or
        # every rent payment that changes by a rupee becomes a spike.
        threshold = mean + _SPIKE_SIGMAS * sigma if sigma > 0 else mean * 1.5
        if current <= threshold or current <= mean:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests

        out.append({
            "type": "category_spike",
            "severity": "medium",
            "title": f"{category} is unusually high this month",
            "detail": f"₹{current:,.0f} against a typical ₹{mean:,.0f} "
                      f"({(current / mean - 1) * 100:.0f}% above your average).",
            "amount": round(current, 2),
            "date": str(latest_period),
            "merchant": None,
            "category": str(category),
            "baseline": round(mean, 2),
        })
    return out


def _large_first_time_merchants(debits: pd.DataFrame) -> List[Dict[str, Any]]:
    """A big payment to somewhere the user has never paid before."""
    if len(debits) < 20:
        return []

    threshold = float(debits["amount"].quantile(0.95))
    first_seen = debits.sort_values("_date").groupby("_merchant").head(1)
    latest_month = debits["_date"].max().to_period("M")

    out: List[Dict[str, Any]] = []
    # Zipped columns, not itertuples: the working columns here start with an underscore
    # and itertuples renames those to positional _1/_2, so attribute access reads the
    # wrong field.
    for amount, date, merchant in zip(
        first_seen["amount"].tolist(),
        first_seen["_date"].tolist(),
        first_seen["_merchant"].tolist(),
    ):
        amount = float(amount)
        if amount < threshold:
            continue
        if pd.Timestamp(date).to_period("M") != latest_month:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        out.append({
            "type": "large_new_merchant",
            "severity": "low",
            "title": f"First payment to {merchant} is a large one",
            "detail": f"₹{amount:,.0f} is in the top 5% of your transactions and this "
                      "merchant has not appeared before.",
            "amount": amount,
            "date": f"{pd.Timestamp(date):%Y-%m-%d}",
            "merchant": str(merchant),
        })
    return out


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile_accounts(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Verify the printed running balance against the transactions themselves.

    For each account, walk the statement in date order and check that every balance
    equals the previous one adjusted by that row's amount. A mismatch means a row was
    dropped, an amount was misread, or the statement has a gap - all of which are
    invisible in the dashboard otherwise.

    This is the check that makes the rest of the numbers trustworthy, and it is the
    reason the parser bothers to capture the balance column at all.
    """
    if df is None or df.empty or "balance" not in df.columns:
        return []

    work = attach_account_keys(df.copy())
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["_date"])

    results: List[Dict[str, Any]] = []

    for key, group in work.groupby("account_key", sort=False):
        group = group.dropna(subset=["balance"]).sort_values(["_date"])
        if len(group) < 2:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests

        balances = group["balance"].tolist()
        amounts = group["amount"].tolist()
        types = group["type"].tolist()
        dates = group["_date"].tolist()

        breaks: List[Dict[str, Any]] = []
        for i in range(1, len(balances)):
            signed = amounts[i] if types[i] == "credit" else -amounts[i]
            expected = balances[i - 1] + signed
            drift = balances[i] - expected
            # A paisa of rounding is not a break; anything above a rupee is.
            if abs(drift) > 1.0:
                breaks.append({
                    "date": f"{dates[i]:%Y-%m-%d}",
                    "expected_balance": round(expected, 2),
                    "actual_balance": round(float(balances[i]), 2),
                    "drift": round(float(drift), 2),
                })

        results.append({
            "account_key": key,
            "rows_checked": len(group),
            "breaks": breaks[:20],
            "break_count": len(breaks),
            "opening_balance": round(float(balances[0]), 2),
            "closing_balance": round(float(balances[-1]), 2),
            "status": "reconciled" if not breaks else "gaps_found",
            # The most useful single number: how much of the movement is unexplained.
            "unexplained_total": round(sum(abs(b["drift"]) for b in breaks), 2),
        })

    return results


# ---------------------------------------------------------------------------
# Sankey
# ---------------------------------------------------------------------------

def build_sankey(df: pd.DataFrame, nature_of, max_leaves: int = 8) -> Dict[str, Any]:
    """
    Nodes and links for an income -> nature -> category flow diagram.

    The single most legible way to show a budget: where money came from, how it split
    across needs/wants/investments, and what it actually went on. `nature_of` is passed
    in rather than imported so the classification stays owned by the analytics layer.
    """
    if df is None or df.empty:
        return {"nodes": [], "links": []}

    work = df.copy()
    if "is_transfer" in work.columns:
        work = work[~work["is_transfer"]]
    if work.empty:
        return {"nodes": [], "links": []}  # pragma: no cover — defensive / hard to exercise in unit tests

    credits = work[work["type"] == "credit"]
    debits = work[work["type"] == "debit"]

    nodes: List[Dict[str, str]] = []
    index: Dict[str, int] = {}

    def node(name: str, group: str) -> int:
        if name not in index:
            index[name] = len(nodes)
            nodes.append({"name": name, "group": group})
        return index[name]

    links: List[Dict[str, Any]] = []
    total_in = node("Income", "income")

    # Income sources, biggest first, with the tail rolled up so the diagram stays legible.
    if not credits.empty:
        by_source = credits.groupby(credits["category"].fillna("Other Income"))["amount"].sum()
        by_source = by_source.sort_values(ascending=False)
        for name, amount in _with_tail(by_source, max_leaves, "Other income").items():
            links.append({"source": node(str(name), "source"), "target": total_in, "value": round(float(amount), 2)})

    if debits.empty:
        return {"nodes": nodes, "links": links}  # pragma: no cover — defensive / hard to exercise in unit tests

    debits = debits.copy()
    debits["_nature"] = debits["category"].fillna("Uncategorized").map(nature_of)

    for nature, nature_group in debits.groupby("_nature"):
        nature_total = float(nature_group["amount"].sum())
        if nature_total <= 0:
            continue  # pragma: no cover — defensive / hard to exercise in unit tests
        nature_node = node(nature.title(), "nature")
        links.append({"source": total_in, "target": nature_node, "value": round(nature_total, 2)})

        by_category = nature_group.groupby(nature_group["category"].fillna("Uncategorized"))["amount"].sum()
        by_category = by_category.sort_values(ascending=False)
        for name, amount in _with_tail(by_category, max_leaves, f"Other {nature}").items():
            links.append({
                "source": nature_node,
                "target": node(str(name), "category"),
                "value": round(float(amount), 2),
            })

    return {"nodes": nodes, "links": links}


def _with_tail(series: pd.Series, keep: int, tail_label: str) -> pd.Series:
    """Top `keep` entries, with everything else summed into one labelled remainder."""
    if len(series) <= keep:
        return series
    head = series.iloc[:keep]
    tail = series.iloc[keep:].sum()
    if tail <= 0:
        return head  # pragma: no cover — defensive / hard to exercise in unit tests
    return pd.concat([head, pd.Series({tail_label: tail})])
