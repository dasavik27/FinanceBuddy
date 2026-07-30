"""
Differential safety net for the finance.py vectorization.

compute_benchmark_xirr(), compute_rolling_return_avg(), compute_rolling_return_series(),
compute_consistency_score() and compute_period_comparison() were day-by-day / row-by-row
Python loops being rewritten into vectorized pandas/numpy form. They had ZERO test
coverage, and every one of them is riddled with order-dependent state (running unit
balances, `searchsorted` cursor advances, break-on-empty loop exits) plus a pile of
accumulated "FIX #..." edge cases.

Each `reference_*` function below is a LITERAL transcription of the pre-vectorization
implementation (finance.py as of commit 515d9f6b) — quirks, off-by-ones and all. That
transcription is the specification: if a test here fails, the rewrite changed observable
behaviour and is wrong. Quirks that are arguably bugs are marked `QUIRK:` and deliberately
preserved; the vectorized version must reproduce them (or the change must be made
knowingly, with this file updated in the same commit).

Determinism / hermeticity notes:
  * `finance.datetime` is monkeypatched to a frozen subclass (autouse fixture) because
    compute_benchmark_xirr()/compute_period_comparison() call datetime.now(), which
    would otherwise make the reference and the real call disagree in the last digits.
  * NO network, ever: the `_hermetic` autouse fixture stubs the NAV/benchmark fetchers on
    their DEFINING modules and booby-traps requests/urllib/yfinance so a leak fails loudly
    instead of hanging. compute_period_comparison() does a function-local
    `from shared.services.market_data import ...`, so patching `finance.<name>` would do
    nothing — the name is rebound from the source module on every call.
  * `_get_standard_ledger` is transcribed too, so a change to that shared helper cannot
    silently pass through the compute_benchmark_xirr comparison.
  * Case volume is scaled by the FINEQ_SCALE env var (default 1, ~8-15s for the file).
    `FINEQ_SCALE=4 python -m pytest tests/test_finance_equivalence.py` runs ~4x the
    randomized corpus in ~30s — worth doing once against each rewrite candidate.
"""

import logging
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pytest
import requests
import urllib.request
import yfinance
from pyxirr import xirr

import shared.services.market_data as market_data
import shared.services.market_indices as market_indices
from domains.mutual_funds import finance
from domains.mutual_funds.finance import (
    compute_benchmark_xirr,
    compute_consistency_score,
    compute_period_comparison,
    compute_rolling_return_avg,
    compute_rolling_return_series,
)

# Tolerance: the rewrite is pure reordering of float arithmetic, so anything looser than
# this would let a real regression through. Most outputs are round(x, 2) at the boundary,
# which absorbs summation-order noise entirely; the raw-float paths still hold 1e-9.
RTOL = 1e-9
ATOL = 1e-12

FROZEN_NOW = datetime(2026, 7, 29, 12, 34, 56)

# Randomized case volume. Deliberately modest: both the reference and the production
# implementation are day-by-day Python loops, so every case pays for two full simulations
# and the whole file has to stay inside the suite's time budget (~10-15s here).
# For a deep soak while doing the actual rewrite: FINEQ_SCALE=10 python -m pytest ...
_SCALE = float(os.environ.get("FINEQ_SCALE", "1"))


def _n(base: int) -> int:
    return max(1, int(round(base * _SCALE)))


_NULL_LOGGER = logging.getLogger("finance_equivalence_null")
_NULL_LOGGER.addHandler(logging.NullHandler())
_NULL_LOGGER.propagate = False
_NULL_LOGGER.disabled = True


class _FrozenDateTime(datetime):
    """datetime subclass with a pinned now() — keeps xirr's final cashflow date stable."""

    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW


@pytest.fixture(autouse=True)
def _freeze_finance_clock(monkeypatch):
    monkeypatch.setattr(finance, "datetime", _FrozenDateTime)
    # finance.py logs inside its blanket `except Exception` handlers. That log call is the
    # only side effect the production path has and the reference transcription does not, so
    # silence it: a failing/slow log write would show up as a bogus "one raised, one
    # didn't" divergence rather than as a real behavioural difference.
    monkeypatch.setattr(finance, "logger", _NULL_LOGGER)
    monkeypatch.setattr(finance.logging, "raiseExceptions", False, raising=False)


def _network_forbidden(*args, **kwargs):
    raise AssertionError(
        "live network access attempted from test_finance_equivalence.py — a data-provider "
        "entry point is unstubbed (see _hermetic below)"
    )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """
    Zero network, and a loud failure rather than a 30s hang if something leaks.

    Two layers:
      1. the transport primitives (requests / urllib / yfinance), so any provider path we
         did not think of still fails fast instead of blocking on a socket;
      2. every named fetcher, patched on its DEFINING module. finance.py resolves these
         with function-local imports (`from shared.services.market_data import
         fetch_nav_series_by_isin, ...` inside compute_period_comparison), so patching
         `finance.<name>` would be a no-op — the name is re-bound on every single call.

    Tests that legitimately need NAV data re-patch the three fetchers via
    _NavStubs.install(), which runs after this fixture and therefore wins.
    """
    monkeypatch.setattr(requests.Session, "request", _network_forbidden, raising=True)
    monkeypatch.setattr(requests.Session, "get", _network_forbidden, raising=True)
    monkeypatch.setattr(requests, "get", _network_forbidden, raising=True)
    monkeypatch.setattr(urllib.request, "urlopen", _network_forbidden, raising=True)
    monkeypatch.setattr(yfinance, "download", _network_forbidden, raising=True)
    monkeypatch.setattr(yfinance, "Ticker", _network_forbidden, raising=True)

    for name in (
        "fetch_nav_series_by_isin", "fetch_nav_series_by_code", "fetch_nav_series_by_name",
        "_fetch_amfi_data_uncached", "resolve_scheme_code_from_isin",
        "_full_nav_series", "_load_full_nav_series", "_fetch_amfi_ter_all",
        "search_mutual_funds",
    ):
        monkeypatch.setattr(market_data, name, _network_forbidden, raising=True)

    for name in (
        "fetch_benchmark_series", "_fetch_benchmark_series_uncached", "_fetch_yahoo_series",
        "_fetch_mf_nav_series",
    ):
        monkeypatch.setattr(market_indices, name, _network_forbidden, raising=True)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _assert_equivalent(expected, actual, path="result"):
    """Structure compared exactly, numerics with pytest.approx."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual)}"
        assert sorted(expected.keys()) == sorted(actual.keys()), (
            f"{path}: key mismatch\nexpected={sorted(expected.keys())}\n"
            f"actual={sorted(actual.keys())}"
        )
        for k in expected:
            _assert_equivalent(expected[k], actual[k], f"{path}[{k!r}]")
        return

    if isinstance(expected, (list, tuple)):
        assert isinstance(actual, (list, tuple)), f"{path}: expected sequence, got {type(actual)}"
        assert len(expected) == len(actual), (
            f"{path}: length mismatch {len(expected)} != {len(actual)}"
        )
        for i, (e, a) in enumerate(zip(expected, actual)):
            _assert_equivalent(e, a, f"{path}[{i}]")
        return

    if isinstance(expected, pd.Series):
        assert isinstance(actual, pd.Series), f"{path}: expected Series, got {type(actual)}"
        assert len(expected) == len(actual), (
            f"{path}: series length {len(expected)} != {len(actual)}"
        )
        assert expected.index.equals(actual.index), (
            f"{path}: index mismatch\nexpected={expected.index[:8]}\nactual={actual.index[:8]}"
        )
        if len(expected):
            np.testing.assert_allclose(
                expected.to_numpy(dtype=float), actual.to_numpy(dtype=float),
                rtol=RTOL, atol=ATOL, err_msg=f"{path}: values diverged",
            )
        return

    if expected is None or isinstance(expected, (bool, str)):
        assert expected == actual, f"{path}: {expected!r} != {actual!r}"
        return

    if isinstance(expected, float) and np.isnan(expected):
        assert isinstance(actual, float) and np.isnan(actual), f"{path}: expected NaN, got {actual!r}"
        return

    assert actual == pytest.approx(expected, rel=RTOL, abs=ATOL), (
        f"{path}: {expected!r} != {actual!r}"
    )


def _call(fn, *args, **kwargs):
    """Run fn, returning ('ok', value) or ('raise', exception-type-name)."""
    try:
        return ("ok", fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - exception *type* is part of the contract
        return ("raise", type(exc).__name__)


def _assert_pair(reference, target, args, label):
    """Compare reference vs production, including which exception (if any) escapes."""
    exp_kind, exp_val = _call(reference, *args)
    act_kind, act_val = _call(target, *args)
    assert exp_kind == act_kind, (
        f"{label}: outcome kind mismatch reference={exp_kind}({exp_val!r}) "
        f"target={act_kind}({act_val!r})"
    )
    if exp_kind == "raise":
        assert exp_val == act_val, f"{label}: different exception {exp_val} vs {act_val}"
        return
    _assert_equivalent(exp_val, act_val, path=label)


# ---------------------------------------------------------------------------
# reference_get_standard_ledger — literal transcription of _get_standard_ledger()
# ---------------------------------------------------------------------------

def reference_get_standard_ledger(df_t: pd.DataFrame) -> List[Dict]:
    ledger = []
    if df_t is None or df_t.empty:
        return ledger

    for _, row in df_t.iterrows():
        raw_amt = row.get("Amount", 0)
        amt = abs(float(raw_amt)) if raw_amt is not None else 0.0

        t_type = str(row.get("Type", "")).upper().strip()
        units = float(row.get("Units", 0) or 0)
        nav = float(row.get("NAV", 0) or 0)
        d = row["Date"].date() if isinstance(row["Date"], (datetime, pd.Timestamp)) else row["Date"]

        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        if amt == 0 and not any(x in t_type for x in ("DIVIDEND", "BONUS")):
            continue

        # QUIRK: BONUS is matched by the "keep" guard above and then dropped here, so a
        # zero-amount BONUS row survives the first filter only to be skipped anyway.
        if any(x in t_type for x in ("REINVEST", "BONUS", "IDCW_REINVEST", "GROWTH_OPTION")):
            continue

        # QUIRK: `units > 0` is checked BEFORE the type keywords, so a row typed
        # REDEMPTION but carrying positive Units is booked as a BUY.
        if units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN")):
            ledger.append({"date": d, "amount": -amt, "type": "BUY"})
        elif units < 0 or any(
            x in t_type for x in ("SELL", "REDEMPTION", "SWP-OUT", "STP-OUT", "SWITCH-OUT")
        ):
            ledger.append({"date": d, "amount": amt, "type": "SELL"})
        else:
            if any(x in t_type for x in ("DIVIDEND", "PAYOUT", "IDCW_PAYOUT")):
                ledger.append({"date": d, "amount": amt, "type": "INCOME"})
            elif any(x in t_type for x in ("TAX", "DUTY", "FEE", "STT")):
                ledger.append({"date": d, "amount": -amt, "type": "EXPENSE"})

    return ledger


# ---------------------------------------------------------------------------
# reference_compute_benchmark_xirr — literal transcription of compute_benchmark_xirr()
# ---------------------------------------------------------------------------

def reference_compute_benchmark_xirr(
    df_t: pd.DataFrame,
    bench_series: pd.Series,
) -> Tuple[float, float]:
    if bench_series is None or bench_series.empty:
        return 0.0, 0.0

    ledger = reference_get_standard_ledger(df_t)
    if not ledger:
        return 0.0, 0.0

    bench_sorted = bench_series.sort_index()

    try:
        total_bench_units = 0.0
        cashflows: List[Dict] = []

        for l in ledger:
            txn_date = pd.Timestamp(l["date"])
            amt = abs(l["amount"])

            past = bench_sorted[bench_sorted.index <= txn_date]
            if past.empty:
                bench_price = float(bench_sorted.iloc[0])
            else:
                bench_price = float(past.iloc[-1])

            if bench_price <= 0:
                continue

            if l["amount"] < 0:          # Purchase
                total_bench_units += amt / bench_price
                cashflows.append({"date": txn_date, "amount": -amt})
            elif l["type"] == "SELL":    # Redemption
                units_sold = min(total_bench_units, amt / bench_price)
                total_bench_units = max(0.0, total_bench_units - units_sold)
                bench_redemption_value = units_sold * bench_price
                cashflows.append({"date": txn_date, "amount": bench_redemption_value})
            elif l["type"] == "INCOME":
                cashflows.append({"date": txn_date, "amount": amt})

        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0

        bench_current_price = float(bench_sorted.iloc[-1])
        bench_sim_value = total_bench_units * bench_current_price

        # NOTE: uses the frozen clock via FROZEN_NOW, mirroring finance.datetime.now()
        cashflows.append({"date": pd.Timestamp(FROZEN_NOW), "amount": bench_sim_value})

        ldf = pd.DataFrame(cashflows).dropna()
        ldf["date"] = pd.to_datetime(ldf["date"], dayfirst=True)

        days_held = (ldf["date"].max() - ldf["date"].min()).days
        if 0 < days_held < 365:
            total_outflows = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            total_inflows = ldf[ldf["amount"] > 0]["amount"].sum()
            if total_outflows > 0:
                abs_pct = ((total_inflows - total_outflows) / total_outflows) * 100
                return round(max(-99.0, min(abs_pct, 500.0)), 2), round(bench_sim_value, 2)

        # QUIRK: this branch returns the UNROUNDED bench_sim_value, unlike every other
        # exit path (which rounds to 2dp).
        if ldf[ldf["amount"] < 0].empty or ldf[ldf["amount"] > 0].empty:
            return 0.0, bench_sim_value

        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result) or np.isinf(result):
            return 0.0, bench_sim_value  # QUIRK: unrounded here too

        pct = round(max(-99.0, min(float(result) * 100, 500.0)), 2)
        return pct, round(bench_sim_value, 2)

    except Exception:
        # QUIRK: swallows everything — a tz-aware benchmark index raises TypeError on the
        # `index <= txn_date` comparison and silently degrades to (0.0, 0.0).
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# reference_compute_rolling_return_avg — literal transcription of compute_rolling_return_avg()
# ---------------------------------------------------------------------------

def reference_compute_rolling_return_avg(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,
) -> Optional[float]:
    if nav_series is None or nav_series.empty:
        return None

    nav_sorted = nav_series.sort_index().dropna().resample('D').ffill()
    window_days = int(window_years * 365.25)

    # QUIRK: if every value was NaN, nav_sorted is empty and index[-1] raises IndexError
    # (uncaught, propagates to the caller).
    if (nav_sorted.index[-1] - nav_sorted.index[0]).days < window_days:
        return None

    rolling_cagrs = []
    idx = nav_sorted.index

    i = 0
    while i < len(idx):
        start_date = idx[i]
        end_date_target = start_date + timedelta(days=window_days)

        future = nav_sorted[nav_sorted.index >= end_date_target]
        if future.empty:
            break

        end_nav = float(future.iloc[0])
        start_nav = float(nav_sorted.iloc[i])
        actual_end_date = future.index[0]

        if start_nav > 0 and end_nav > 0:
            actual_years = (actual_end_date - start_date).days / 365.25
            if actual_years > 0:
                cagr = ((end_nav / start_nav) ** (1.0 / actual_years) - 1) * 100
                rolling_cagrs.append(cagr)

        next_date = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        new_i = idx.searchsorted(next_candidates.index[0]) if not next_candidates.empty else i + 1
        i = max(new_i, i + 1)

    if not rolling_cagrs:
        return None

    return round(float(np.mean(rolling_cagrs)), 2)


# ---------------------------------------------------------------------------
# reference_compute_rolling_return_series — literal transcription of compute_rolling_return_series()
# ---------------------------------------------------------------------------

def reference_compute_rolling_return_series(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,
) -> pd.Series:
    if nav_series is None or nav_series.empty:
        return pd.Series(dtype=float)

    nav_sorted = nav_series.sort_index().dropna().resample('D').ffill()
    window_days = int(window_years * 365.25)

    if (nav_sorted.index[-1] - nav_sorted.index[0]).days < window_days:
        return pd.Series(dtype=float)

    dates, values = [], []
    idx = nav_sorted.index
    i = 0

    while i < len(idx):
        start_date = idx[i]
        end_date_target = start_date + timedelta(days=window_days)
        future = nav_sorted[nav_sorted.index >= end_date_target]
        if future.empty:
            break

        end_nav = float(future.iloc[0])
        start_nav = float(nav_sorted.iloc[i])
        actual_end_date = future.index[0]

        if start_nav > 0 and end_nav > 0:
            actual_years = (actual_end_date - start_date).days / 365.25
            if actual_years > 0:
                cagr = ((end_nav / start_nav) ** (1.0 / actual_years) - 1) * 100
                dates.append(actual_end_date)
                values.append(round(cagr, 2))

        next_date = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        new_i = nav_sorted.index.searchsorted(next_candidates.index[0])
        i = max(new_i, i + 1)

    # QUIRK: index is a plain list of Timestamps, so an empty result is an object-dtype
    # empty Series here but float64 on the early-return paths above.
    return pd.Series(values, index=dates)


# ---------------------------------------------------------------------------
# reference_compute_consistency_score — literal transcription of compute_consistency_score()
# ---------------------------------------------------------------------------

def reference_compute_consistency_score(
    nav_series: pd.Series,
    bench_series: pd.Series,
    window_days: int = 365,
    step_days: int = 30,
) -> float:
    if nav_series is None or nav_series.empty:
        return 5.0
    if bench_series is None or bench_series.empty:
        return 5.0
    # QUIRK: this span check reads the RAW (possibly unsorted, possibly NaN-laden) index,
    # not the sorted/cleaned one used below — an unsorted input can yield a negative span
    # and bail out with 5.0.
    if (nav_series.index[-1] - nav_series.index[0]).days < window_days:
        return 5.0

    nav_sorted = nav_series.sort_index().dropna().resample('D').ffill()
    bench_sorted = bench_series.sort_index().dropna().resample('D').ffill()

    beat_count, total = 0, 0
    idx = nav_sorted.index
    i = 0

    while i < len(idx):
        start_date = idx[i]
        end_date_target = start_date + timedelta(days=window_days)

        future_nav = nav_sorted[nav_sorted.index >= end_date_target]
        future_bench = bench_sorted[bench_sorted.index >= end_date_target]

        if future_nav.empty or future_bench.empty:
            break

        start_bench = bench_sorted[bench_sorted.index <= start_date]
        if start_bench.empty:
            # QUIRK: advances by step_days *positions*, not days — only equivalent to the
            # date-based advance below because the series was resampled to daily.
            i += step_days
            continue

        fund_ret = float(future_nav.iloc[0]) / float(nav_sorted.iloc[i]) - 1
        bench_ret = float(future_bench.iloc[0]) / float(start_bench.iloc[-1]) - 1

        if fund_ret > bench_ret:
            beat_count += 1
        total += 1

        next_date = start_date + timedelta(days=step_days)
        next_candidates = nav_sorted[nav_sorted.index >= next_date]
        if next_candidates.empty:
            break
        # QUIRK: no max(new_i, i + 1) guard here (unlike the rolling helpers).
        i = nav_sorted.index.searchsorted(next_candidates.index[0])

    if total == 0:
        return 5.0

    return round((beat_count / total) * 10, 1)


# ---------------------------------------------------------------------------
# reference_compute_period_comparison — literal transcription of compute_period_comparison()
# ---------------------------------------------------------------------------

def reference_compute_period_comparison(
    df_t_all: pd.DataFrame,
    df_h: pd.DataFrame,
    total_value: float,
    bench_series: pd.Series,
    period_days: int,
) -> Dict:
    result = {
        "port_pct": 0.0,
        "bench_pct": 0.0,
        "port_value": total_value,
        "bench_value": 0.0,
        "use_xirr": period_days >= 1095,
        "alpha": 0.0,
        "dates": [],
        "portfolio": [],
        "benchmark": [],
        "chart_mode": "indexed",
    }

    # QUIRK: every early return omits the "market_value" key that the success path adds,
    # so callers see a different dict shape depending on which branch was taken.
    if df_t_all is None or df_t_all.empty or df_h is None or df_h.empty:
        return result

    bench_sorted = pd.Series(dtype=float)
    if bench_series is not None and not bench_series.empty:
        bench_sorted = bench_series.sort_index().dropna()

    df_t = df_t_all.copy()
    df_t["Date"] = pd.to_datetime(df_t["Date"], dayfirst=True)
    all_dates = df_t["Date"].sort_values()

    start_date = all_dates.iloc[0]

    today_dt = pd.Timestamp(FROZEN_NOW.date())
    if bench_sorted.empty:
        end_date = today_dt
    else:
        end_date = bench_sorted.index[-1]

    if start_date > end_date:
        end_date = start_date

    if end_date > today_dt:
        end_date = today_dt

    calendar = pd.date_range(start_date, end_date, freq='D')

    # NOTE: production does a function-local import of these three fetchers from
    # shared.services.market_data; the test stubs live on that module, so calling them
    # through the module object here is equivalent.
    fund_metadata = {}
    for _, row in df_h.iterrows():
        f = str(row.get("Fund", ""))
        if f:
            fund_metadata[f] = (
                str(row.get("ISIN", row.get("Isin", ""))).strip(),
                str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip(),
            )

    for _, row in df_t_all.iterrows():
        f = str(row.get("Fund", ""))
        if f and f not in fund_metadata:
            fund_metadata[f] = (
                str(row.get("ISIN", row.get("Isin", ""))).strip(),
                str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip(),
            )

    fund_navs = {}
    for fn, (isin, scode) in fund_metadata.items():
        if not fn:
            continue

        navs = pd.Series(dtype=float)
        if isin and isin not in ("N/A", "", "nan", "None"):
            navs = market_data.fetch_nav_series_by_isin(isin, 9999)
        if navs.empty and scode and scode not in ("N/A", "", "nan", "None"):
            navs = market_data.fetch_nav_series_by_code(scode, 9999)
        if navs.empty and fn:
            navs = market_data.fetch_nav_series_by_name(fn, 9999)

        if not navs.empty:
            fund_navs[fn] = navs.sort_index().dropna().resample('D').ffill()

    if not fund_navs:
        return result

    fund_units = {f: 0.0 for f in fund_navs.keys()}

    global_dates = []
    global_port_nav = []
    global_bench_nav = []
    global_market_value = []

    port_units = 0.0
    port_nav = 100.0  # Base 100 on Day 1

    txns_by_date = {}
    for _, r in df_t.iterrows():
        d = r["Date"].date()
        if d not in txns_by_date:
            txns_by_date[d] = []
        txns_by_date[d].append(r)

    bench_start_global = (
        float(bench_sorted[bench_sorted.index >= start_date].iloc[0])
        if not bench_sorted[bench_sorted.index >= start_date].empty
        else 1.0
    )

    for d in calendar:
        d_obj = d.date()

        b_series = bench_sorted[bench_sorted.index <= d]
        b_curr = float(b_series.iloc[-1]) if not b_series.empty else bench_start_global
        b_idx = (b_curr / bench_start_global) * 100.0

        # A) Start-of-Day Market Value
        market_value_sod = 0.0
        for f, units in fund_units.items():
            if units > 0:
                f_navs = fund_navs[f]
                past_navs = f_navs[f_navs.index.date <= d_obj]
                nav_today = (
                    float(past_navs.iloc[-1]) if not past_navs.empty
                    else float(f_navs.iloc[0]) if not f_navs.empty else 10.0
                )
                market_value_sod += units * nav_today

        if port_units > 0:
            port_nav = market_value_sod / port_units

        # B) Process today's cashflows
        net_cashflow = 0.0
        if d_obj in txns_by_date:
            for txn in txns_by_date[d_obj]:
                f = txn["Fund"]
                if f not in fund_units:
                    continue

                t_type = str(txn.get("Type", "")).upper()
                amt = abs(float(txn.get("Amount", 0) or 0))
                units_t = abs(float(txn.get("Units", 0) or 0))
                nav_t = float(txn.get("NAV", 0) or 0)

                if amt == 0 and units_t > 0 and nav_t > 0:
                    amt = units_t * nav_t

                # QUIRK: plain substring matching on the raw Type string, buy branch first —
                # e.g. "TransactionType.SWITCH_OUT_MERGER" has no "SWITCH-OUT" (underscore,
                # not hyphen) and falls through to the no-op else.
                if "BUY" in t_type or "PURCHASE" in t_type or "SIP" in t_type or "SWITCH-IN" in t_type:
                    fund_units[f] += units_t
                    net_cashflow += amt
                elif "SELL" in t_type or "REDEMPTION" in t_type or "SWP" in t_type or "SWITCH-OUT" in t_type:
                    fund_units[f] -= units_t
                    fund_units[f] = max(0.0, fund_units[f])
                    net_cashflow -= amt
                elif "REINVEST" in t_type or "BONUS" in t_type:
                    fund_units[f] += units_t

        # C) Issue/Redeem portfolio units at current Portfolio NAV
        if net_cashflow > 0:
            port_units += net_cashflow / port_nav
        elif net_cashflow < 0:
            port_units -= abs(net_cashflow) / port_nav
            port_units = max(0.0, port_units)

        # D) End-of-Day Market Value
        market_value_eod = 0.0
        for f, units in fund_units.items():
            if units > 0:
                f_navs = fund_navs.get(f)
                if f_navs is not None:
                    past_navs = f_navs[f_navs.index.date <= d_obj]
                    nav_today = (
                        float(past_navs.iloc[-1]) if not past_navs.empty
                        else float(f_navs.iloc[0]) if not f_navs.empty else 10.0
                    )
                    market_value_eod += units * nav_today
                else:
                    market_value_eod += units * 10.0

        # QUIRK: port_nav is only refreshed while port_units > 0; once the portfolio is
        # fully redeemed the stale NAV sticks and is reused to re-issue units later.
        if port_units > 0:
            port_nav = market_value_eod / port_units

        global_dates.append(d)
        global_port_nav.append(port_nav)
        global_bench_nav.append(b_idx)
        global_market_value.append(market_value_eod)

    global_df = pd.DataFrame({
        "bench": global_bench_nav,
        "port": global_port_nav,
        "market_value": global_market_value,
    }, index=global_dates)

    bench_end_date = global_df.index[-1]
    if period_days < 9999:
        period_start = bench_end_date - timedelta(days=period_days)
    else:
        period_start = global_df.index[0]

    period_df = global_df[global_df.index >= period_start]
    if period_df.empty:
        return result

    slice_start_port = float(period_df["port"].iloc[0])
    slice_start_bench = float(period_df["bench"].iloc[0])

    if slice_start_port <= 0:
        slice_start_port = 1.0
    if slice_start_bench <= 0:
        slice_start_bench = 1.0

    period_df = period_df.copy()
    period_df["bench_scaled"] = (period_df["bench"] / slice_start_bench) * slice_start_port

    slice_end_port = float(period_df["port"].iloc[-1])
    slice_end_bench = float(period_df["bench"].iloc[-1])

    actual_days = (period_df.index[-1] - period_df.index[0]).days

    if actual_days >= 365:
        years = actual_days / 365.25
        period_port_pct = (((slice_end_port / slice_start_port) ** (1 / years)) - 1) * 100.0
        period_bench_pct = (((slice_end_bench / slice_start_bench) ** (1 / years)) - 1) * 100.0
    else:
        period_port_pct = ((slice_end_port / slice_start_port) - 1) * 100.0
        period_bench_pct = ((slice_end_bench / slice_start_bench) - 1) * 100.0

    result["port_pct"] = round(period_port_pct, 2)
    result["bench_pct"] = round(period_bench_pct, 2)
    result["alpha"] = round(period_port_pct - period_bench_pct, 2)

    # Reference XIRR on purpose: a regression inside compute_benchmark_xirr must not be
    # able to hide behind this call.
    _, bench_all_sim_value = reference_compute_benchmark_xirr(df_t_all, bench_sorted)
    result["bench_value"] = round(bench_all_sim_value, 2)

    step = max(1, len(period_df) // 60)
    chart_indices = list(range(0, len(period_df), step))
    if (len(period_df) - 1) not in chart_indices:
        chart_indices.append(len(period_df) - 1)

    dates_arr, port_vals, bench_vals, market_vals = [], [], [], []
    for idx in chart_indices:
        d = period_df.index[idx]
        dates_arr.append(d.strftime("%Y-%m-%d"))
        port_vals.append(round(period_df["port"].iloc[idx], 2))
        bench_vals.append(round(period_df["bench_scaled"].iloc[idx], 2))
        market_vals.append(round(period_df["market_value"].iloc[idx], 2))

    result["dates"] = dates_arr
    result["portfolio"] = port_vals
    result["benchmark"] = bench_vals
    result["market_value"] = market_vals

    return result


# ---------------------------------------------------------------------------
# Synthetic input generators (fixed seeds — every failure is reproducible)
# ---------------------------------------------------------------------------

FUNDS = [
    "Synthetic Flexi Growth Fund",
    "Synthetic ELSS Saver Fund",
    "Synthetic Liquid Reserve Fund",
    "Synthetic Midcap Alpha Fund",
]

BUY_TYPES = [
    "TransactionType.PURCHASE",
    "TransactionType.PURCHASE_SIP",
    "SWITCH-IN",
    "Buy",
    "STP-IN",
]
SELL_TYPES = [
    "TransactionType.REDEMPTION",
    "SWITCH-OUT",
    "SWP-OUT",
    "Sell",
    "STP-OUT",
]
ODD_TYPES = [
    "TransactionType.DIVIDEND_PAYOUT",
    "TransactionType.DIVIDEND_REINVEST",
    "TransactionType.BONUS",
    "STT_TAX",
    "STAMP_DUTY",
    "",
    "TransactionType.SWITCH_OUT_MERGER",   # underscore form: matches no branch
]

BASE = datetime(2019, 1, 7)

# Approximate calendar days covered by one point of each frequency. Used to size series
# by *calendar span* rather than by point count: every function under test resamples to
# daily internally, so a 2600-point weekly series would silently become an 18,000-row
# daily loop and make this suite take minutes.
_FREQ_DAYS = {"D": 1.0, "B": 1.45, "W-FRI": 7.0}


def _points_for(freq, span_days):
    return max(5, int(span_days / _FREQ_DAYS[freq]))


def _nav_series(rng, n_points, start_nav=100.0, start_offset_days=0, *,
                freq="D", nan_frac=0.0, tz=None, drift=0.0004, vol=0.011,
                unsorted=False):
    """
    Deterministic geometric-random-walk NAV series with a DatetimeIndex.

    The walk is drawn from a numpy Generator seeded off `rng`, so the whole corpus is
    still reproducible from the single seed at the top of each test while staying fast
    enough that input construction doesn't dominate the run.
    """
    nrng = np.random.default_rng(rng.getrandbits(63))
    idx = pd.date_range(BASE + timedelta(days=start_offset_days), periods=n_points, freq=freq)
    steps = 1.0 + drift + vol * (nrng.random(n_points) - 0.5) * 2.0
    vals = start_nav * np.cumprod(steps)
    s = pd.Series(vals, index=idx)
    if nan_frac > 0:
        s[nrng.random(n_points) < nan_frac] = np.nan
    if tz is not None:
        s.index = s.index.tz_localize(tz)
    if unsorted:
        s = s.iloc[nrng.permutation(n_points)]
    return s


def _random_ledger(rng, *, n_funds=None, n_txns=None, span_days=1500,
                   start_offset_days=0, zero_units=True):
    """Mixed Purchase/Redemption/switch/odd-type ledger across several funds."""
    n_funds = n_funds or rng.randint(1, 3)
    funds = FUNDS[:n_funds]
    n_txns = n_txns if n_txns is not None else rng.randint(1, 8)

    rows = []
    for _ in range(n_txns):
        fund = rng.choice(funds)
        day = start_offset_days + rng.randrange(0, span_days)
        kind = rng.choices(["buy", "sell", "odd"], weights=[6, 3, 2])[0]
        nav = round(rng.uniform(8.0, 250.0), 4)

        if kind == "buy":
            units = round(rng.uniform(0.5, 900.0), 3)
            amount = round(units * nav, 2)
            t_type = rng.choice(BUY_TYPES)
        elif kind == "sell":
            units = -round(rng.uniform(0.5, 900.0), 3)
            amount = -round(abs(units) * nav, 2)
            t_type = rng.choice(SELL_TYPES)
        else:
            units = 0.0 if (zero_units and rng.random() < 0.6) else round(rng.uniform(1.0, 50.0), 3)
            amount = round(rng.uniform(0.0, 5000.0), 2)
            t_type = rng.choice(ODD_TYPES)

        # Sprinkle amount-less rows so the Units*NAV imputation branch is exercised.
        if rng.random() < 0.12:
            amount = 0.0

        rows.append({
            "Fund": fund,
            "Date": BASE + timedelta(days=day),
            "Type": t_type,
            "Units": units,
            "NAV": nav,
            "Amount": amount,
        })

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def _holdings_for(df_t, rng, *, isin_mode="mixed"):
    """Holdings frame for the funds in df_t, with varied ISIN / Scheme_Code coverage."""
    rows = []
    for i, fund in enumerate(sorted(df_t["Fund"].unique())):
        mode = isin_mode
        if mode == "mixed":
            mode = rng.choice(["isin", "code", "none", "sentinel"])
        isin = f"INF000X{i:05d}" if mode == "isin" else ("N/A" if mode == "sentinel" else "")
        scode = f"1000{i}" if mode == "code" else ""
        units = df_t.loc[df_t["Fund"] == fund, "Units"].sum()
        rows.append({
            "Fund": fund,
            "ISIN": isin,
            "Scheme_Code": scode,
            "Units": float(max(units, 0.0)),
            "NAV": 100.0,
            "Market Value": float(max(units, 0.0)) * 100.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Network stubs — compute_period_comparison() must never touch HTTP
# ---------------------------------------------------------------------------

class _NavStubs:
    """
    Records lookups so tests can assert the fetchers were actually exercised.

    compute_period_comparison() resolves NAVs through a function-local
    `from shared.services.market_data import fetch_nav_series_by_isin,
    fetch_nav_series_by_name, fetch_nav_series_by_code` — the import runs on every call,
    so the patch target must be the market_data module, not finance.
    """

    def __init__(self, by_isin=None, by_code=None, by_name=None):
        self.by_isin = by_isin or {}
        self.by_code = by_code or {}
        self.by_name = by_name or {}
        self.calls = []

    def install(self, monkeypatch):
        def _isin(isin, days=1825, refresh=False):
            self.calls.append(("isin", str(isin)))
            return self.by_isin.get(str(isin), pd.Series(dtype=float)).copy()

        def _code(scheme_code, days=3650, refresh=False):
            self.calls.append(("code", str(scheme_code)))
            return self.by_code.get(str(scheme_code), pd.Series(dtype=float)).copy()

        def _name(fund_name, days=1825, refresh=False):
            self.calls.append(("name", str(fund_name)))
            return self.by_name.get(str(fund_name), pd.Series(dtype=float)).copy()

        monkeypatch.setattr(market_data, "fetch_nav_series_by_isin", _isin)
        monkeypatch.setattr(market_data, "fetch_nav_series_by_code", _code)
        monkeypatch.setattr(market_data, "fetch_nav_series_by_name", _name)
        return self


def _nav_map_for(df_t, df_h, rng, *, points=420, missing_frac=0.0):
    """Build the stub lookup tables from a holdings/transactions pair."""
    by_isin, by_code, by_name = {}, {}, {}
    for i, (_, row) in enumerate(df_h.iterrows()):
        if rng.random() < missing_frac:
            continue  # fund with no NAV data anywhere -> exercises the skip paths
        series = _nav_series(rng, points, start_nav=10.0 + 5.0 * i,
                             freq=rng.choice(["D", "B"]),
                             nan_frac=rng.choice([0.0, 0.05]))
        isin = str(row.get("ISIN", "")).strip()
        scode = str(row.get("Scheme_Code", "")).strip()
        if isin and isin not in ("N/A", "", "nan", "None"):
            by_isin[isin] = series
        elif scode and scode not in ("N/A", "", "nan", "None"):
            by_code[scode] = series
        else:
            by_name[str(row["Fund"])] = series
    for fund in df_t["Fund"].unique():
        if fund not in by_name and rng.random() < 0.3:
            by_name[str(fund)] = _nav_series(rng, points, start_nav=42.0)
    return _NavStubs(by_isin, by_code, by_name)


# ---------------------------------------------------------------------------
# compute_benchmark_xirr
# ---------------------------------------------------------------------------

def test_benchmark_xirr_matches_reference_on_random_inputs():
    rng = random.Random(20260729)
    for i in range(_n(40)):
        df_t = _random_ledger(rng, span_days=rng.choice([200, 900, 2200]))
        bench = _nav_series(
            rng,
            rng.choice([60, 200, 420]),
            start_nav=rng.uniform(50.0, 20000.0),
            freq=rng.choice(["D", "B", "W-FRI"]),
            nan_frac=rng.choice([0.0, 0.0, 0.08]),
        )
        _assert_pair(reference_compute_benchmark_xirr, compute_benchmark_xirr,
                     (df_t, bench), f"benchmark_xirr case {i} (seed 20260729)")


def test_benchmark_xirr_edge_cases():
    rng = random.Random(11)
    bench = _nav_series(rng, 300, start_nav=15000.0)
    single = _random_ledger(rng, n_funds=1, n_txns=1, span_days=30)
    all_redeemed = pd.DataFrame([
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=10), "Type": "TransactionType.PURCHASE",
         "Units": 100.0, "NAV": 20.0, "Amount": 2000.0},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=800), "Type": "TransactionType.REDEMPTION",
         "Units": -100.0, "NAV": 30.0, "Amount": -3000.0},
    ])
    zero_units = pd.DataFrame([
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=5), "Type": "TransactionType.DIVIDEND_PAYOUT",
         "Units": 0.0, "NAV": 0.0, "Amount": 500.0},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=6), "Type": "STT_TAX",
         "Units": 0.0, "NAV": 0.0, "Amount": 12.5},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=7), "Type": "TransactionType.BONUS",
         "Units": 0.0, "NAV": 0.0, "Amount": 0.0},
    ])
    negative_bench = pd.Series([-5.0, 0.0, 120.0, 130.0],
                               index=pd.date_range(BASE, periods=4, freq="D"))

    cases = [
        ("empty df_t", pd.DataFrame(), bench),
        ("None df_t", None, bench),
        ("empty bench", _random_ledger(rng, n_txns=4), pd.Series(dtype=float)),
        ("None bench", _random_ledger(rng, n_txns=4), None),
        ("single txn", single, bench),
        ("fully redeemed", all_redeemed, bench),
        ("zero-unit rows only", zero_units, bench),
        # Non-positive benchmark prices are skipped outright (continue) — no units bought.
        ("non-positive bench prices", all_redeemed, negative_bench),
        # tz-aware benchmark: `index <= naive Timestamp` raises and the blanket
        # `except Exception` turns it into (0.0, 0.0).
        ("tz-aware bench", all_redeemed, _nav_series(rng, 300, tz="Asia/Kolkata")),
        ("bench starts after all txns", all_redeemed,
         _nav_series(rng, 120, start_offset_days=1500)),
        ("all-NaN bench", all_redeemed,
         pd.Series([np.nan] * 5, index=pd.date_range(BASE, periods=5, freq="D"))),
    ]
    for label, df_t, bench_s in cases:
        _assert_pair(reference_compute_benchmark_xirr, compute_benchmark_xirr,
                     (df_t, bench_s), f"benchmark_xirr {label}")


def test_benchmark_xirr_tz_aware_bench_is_swallowed():
    """Pin the documented quirk explicitly so a rewrite can't 'fix' it unnoticed."""
    rng = random.Random(3)
    df_t = _random_ledger(rng, n_funds=1, n_txns=6, span_days=1200)
    tz_bench = _nav_series(rng, 300, tz="Asia/Kolkata")
    assert compute_benchmark_xirr(df_t, tz_bench) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# compute_rolling_return_avg / compute_rolling_return_series
# ---------------------------------------------------------------------------

def _rolling_cases(rng, n):
    for _ in range(n):
        freq = rng.choice(["D", "B", "W-FRI"])
        # Spans stay modest: cost of the loop under test is O(span^2 / step_days) and it
        # runs twice per case (reference + production).
        span = rng.choice([110, 280, 420, 560])
        series = _nav_series(
            rng, _points_for(freq, span),
            start_nav=rng.uniform(8.0, 400.0),
            freq=freq,
            nan_frac=rng.choice([0.0, 0.0, 0.1]),
            drift=rng.choice([-0.0003, 0.0002, 0.0009]),
        )
        window_years = rng.choice([1, 3, 5])
        step_days = rng.choice([7, 7, 30, 90])
        yield series, window_years, step_days


def test_rolling_return_avg_matches_reference_on_random_inputs():
    rng = random.Random(770077)
    for i, (series, wy, sd) in enumerate(_rolling_cases(rng, _n(40))):
        _assert_pair(reference_compute_rolling_return_avg, compute_rolling_return_avg,
                     (series, wy, sd), f"rolling_return_avg case {i} (seed 770077)")


def test_rolling_return_series_matches_reference_on_random_inputs():
    rng = random.Random(770077)  # same stream as the avg test: identical inputs
    for i, (series, wy, sd) in enumerate(_rolling_cases(rng, _n(40))):
        _assert_pair(reference_compute_rolling_return_series, compute_rolling_return_series,
                     (series, wy, sd), f"rolling_return_series case {i} (seed 770077)")


def test_rolling_returns_edge_cases():
    rng = random.Random(99)
    long_series = _nav_series(rng, 800)
    idx = pd.date_range(BASE, periods=800, freq="D")

    cases = [
        ("None", None, 3, 7),
        ("empty", pd.Series(dtype=float), 3, 7),
        ("single point", pd.Series([100.0], index=idx[:1]), 1, 7),
        # QUIRK: all-NaN -> dropna() empties the series -> index[-1] raises IndexError.
        ("all NaN", pd.Series([np.nan] * 40, index=idx[:40]), 1, 7),
        ("history shorter than window", long_series.iloc[:300], 3, 30),
        ("zero and negative NAVs", pd.Series(
            np.where(np.arange(800) % 137 == 0, 0.0, long_series.to_numpy()), index=idx), 1, 30),
        ("weekend gaps", long_series[long_series.index.dayofweek < 5], 1, 30),
        ("duplicate timestamps", pd.concat([long_series, long_series.iloc[500:520]]).sort_index(), 1, 30),
        ("unsorted index", _nav_series(rng, 700, unsorted=True), 1, 30),
        ("tz-aware", _nav_series(rng, 700, tz="UTC"), 1, 30),
        ("step larger than history", long_series, 1, 5000),
    ]
    for label, series, wy, sd in cases:
        _assert_pair(reference_compute_rolling_return_avg, compute_rolling_return_avg,
                     (series, wy, sd), f"rolling_return_avg {label}")
        _assert_pair(reference_compute_rolling_return_series, compute_rolling_return_series,
                     (series, wy, sd), f"rolling_return_series {label}")


# ---------------------------------------------------------------------------
# compute_consistency_score
# ---------------------------------------------------------------------------

def test_consistency_score_matches_reference_on_random_inputs():
    rng = random.Random(5150)
    for i in range(_n(35)):
        nav_freq = rng.choice(["D", "B", "W-FRI"])
        nav = _nav_series(
            rng, _points_for(nav_freq, rng.choice([140, 300, 400, 520])),
            start_nav=rng.uniform(10.0, 300.0),
            freq=nav_freq,
            nan_frac=rng.choice([0.0, 0.0, 0.07]),
            drift=rng.choice([0.0001, 0.0006]),
        )
        bench = _nav_series(
            rng, rng.choice([120, 300, 450, 560]),
            start_nav=rng.uniform(1000.0, 20000.0),
            start_offset_days=rng.choice([0, 0, 45, 200]),  # bench starting late -> start_bench empty
            freq=rng.choice(["D", "B"]),
            nan_frac=rng.choice([0.0, 0.05]),
            drift=0.0004,
        )
        window_days = rng.choice([365, 365, 180, 730])
        step_days = rng.choice([30, 30, 7, 90])
        _assert_pair(reference_compute_consistency_score, compute_consistency_score,
                     (nav, bench, window_days, step_days),
                     f"consistency_score case {i} (seed 5150)")


def test_consistency_score_edge_cases():
    rng = random.Random(424242)
    nav = _nav_series(rng, 620, start_nav=50.0)
    bench = _nav_series(rng, 620, start_nav=12000.0)
    idx = nav.index

    cases = [
        ("None nav", None, bench, 365, 30),
        ("None bench", nav, None, 365, 30),
        ("empty nav", pd.Series(dtype=float), bench, 365, 30),
        ("empty bench", nav, pd.Series(dtype=float), 365, 30),
        ("single point nav", pd.Series([10.0], index=idx[:1]), bench, 365, 30),
        ("nav shorter than window", nav.iloc[:100], bench, 365, 30),
        # QUIRK: the span pre-check reads the raw index, so an unsorted series can measure
        # a negative span and short-circuit to the neutral 5.0.
        ("unsorted nav", _nav_series(rng, 620, unsorted=True), bench, 365, 30),
        ("bench starts 400d late", nav, _nav_series(rng, 500, start_offset_days=400), 365, 30),
        ("bench ends early", nav, bench.iloc[:200], 365, 30),
        ("nav with NaNs", _nav_series(rng, 620, nan_frac=0.25), bench, 365, 30),
        ("all-NaN nav", pd.Series([np.nan] * 620, index=idx), bench, 365, 30),
        ("weekend gaps both", nav[nav.index.dayofweek < 5], bench[bench.index.dayofweek < 5], 365, 30),
        ("duplicate timestamps", pd.concat([nav, nav.iloc[10:30]]).sort_index(), bench, 365, 30),
        ("tz-aware nav vs naive bench", _nav_series(rng, 620, tz="Asia/Kolkata"), bench, 365, 30),
        ("both tz-aware", _nav_series(rng, 620, tz="UTC"), _nav_series(rng, 620, tz="UTC"), 365, 30),
        ("step 1 day", nav.iloc[:420], bench.iloc[:420], 365, 1),
        ("window 0", nav, bench, 0, 30),
    ]
    for label, nav_s, bench_s, wd, sd in cases:
        _assert_pair(reference_compute_consistency_score, compute_consistency_score,
                     (nav_s, bench_s, wd, sd), f"consistency_score {label}")


# ---------------------------------------------------------------------------
# compute_period_comparison
# ---------------------------------------------------------------------------

def test_period_comparison_matches_reference_on_random_inputs(monkeypatch):
    """
    Short calendars on purpose: the production implementation is an O(days x funds)
    Python loop with a full boolean mask per fund per day, and it is run twice per case
    (reference + target). 150 cases of 30-120 day windows keeps this a ~2s test while
    still covering the branch matrix; the long-horizon cases live in their own test.
    """
    rng = random.Random(31337)
    for i in range(_n(14)):
        span = rng.choice([12, 25, 45])
        df_t = _random_ledger(rng, n_funds=rng.randint(1, 2), n_txns=rng.randint(1, 7),
                              span_days=span)
        df_h = _holdings_for(df_t, rng)
        stubs = _nav_map_for(df_t, df_h, rng, points=span + 18,
                             missing_frac=rng.choice([0.0, 0.0, 0.34]))
        stubs.install(monkeypatch)

        bench_points = span + rng.choice([-10, 8, 25])
        bench = _nav_series(rng, max(bench_points, 5), start_nav=rng.uniform(1000.0, 20000.0),
                            freq=rng.choice(["D", "B"]),
                            nan_frac=rng.choice([0.0, 0.06]))
        total_value = round(rng.uniform(0.0, 5_000_000.0), 2)
        period_days = rng.choice([30, 90, 365, 1095, 9999])

        _assert_pair(
            reference_compute_period_comparison, compute_period_comparison,
            (df_t, df_h, total_value, bench, period_days),
            f"period_comparison case {i} (seed 31337)",
        )
        assert stubs.calls, "NAV fetchers were never called — stub wiring is broken"


def test_period_comparison_long_horizon(monkeypatch):
    """One multi-year portfolio: exercises the >=365d CAGR branch and the downsampler."""
    rng = random.Random(606)
    for i in range(_n(1)):
        df_t = _random_ledger(rng, n_funds=1, n_txns=rng.randint(6, 12), span_days=380)
        df_h = _holdings_for(df_t, rng, isin_mode="isin")
        stubs = _nav_map_for(df_t, df_h, rng, points=395).install(monkeypatch)
        bench = _nav_series(rng, 385, start_nav=11000.0)
        _assert_pair(
            reference_compute_period_comparison, compute_period_comparison,
            (df_t, df_h, 1_250_000.0, bench, rng.choice([365, 1095, 9999])),
            f"period_comparison long case {i} (seed 606)",
        )
        assert stubs.calls


def test_period_comparison_edge_cases(monkeypatch):
    rng = random.Random(8081)
    df_t = _random_ledger(rng, n_funds=2, n_txns=8, span_days=40)
    df_h = _holdings_for(df_t, rng, isin_mode="isin")
    nav_stubs = _nav_map_for(df_t, df_h, rng, points=60)
    bench = _nav_series(rng, 55, start_nav=13000.0)

    single = pd.DataFrame([{
        "Fund": FUNDS[0], "Date": BASE + timedelta(days=3), "Type": "TransactionType.PURCHASE",
        "Units": 100.0, "NAV": 10.0, "Amount": 1000.0,
    }])
    single_h = pd.DataFrame([{
        "Fund": FUNDS[0], "ISIN": "INF000X00000", "Scheme_Code": "", "Units": 100.0,
        "NAV": 12.0, "Market Value": 1200.0,
    }])
    fully_redeemed = pd.DataFrame([
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=3), "Type": "TransactionType.PURCHASE",
         "Units": 100.0, "NAV": 10.0, "Amount": 1000.0},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=25), "Type": "TransactionType.REDEMPTION",
         "Units": -100.0, "NAV": 14.0, "Amount": -1400.0},
        # Re-entry after a full exit: port_nav is stale here (see QUIRK above).
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=35), "Type": "TransactionType.PURCHASE",
         "Units": 50.0, "NAV": 15.0, "Amount": 750.0},
    ])
    zero_units = pd.DataFrame([
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=3), "Type": "TransactionType.PURCHASE",
         "Units": 0.0, "NAV": 0.0, "Amount": 0.0},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=15), "Type": "TransactionType.DIVIDEND_REINVEST",
         "Units": 5.0, "NAV": 11.0, "Amount": 0.0},
    ])
    unknown_fund = pd.concat([single, pd.DataFrame([{
        "Fund": "Fund With No NAV Data Anywhere", "Date": BASE + timedelta(days=30),
        "Type": "TransactionType.PURCHASE", "Units": 10.0, "NAV": 50.0, "Amount": 500.0,
    }])], ignore_index=True)

    # When the benchmark is missing the timeline is extended to *today*, so these cases
    # need transactions close to the frozen clock — otherwise the calendar would be a
    # 7-year day-by-day loop and this test alone would take ~10s.
    recent_off = (FROZEN_NOW.date() - BASE.date()).days - 45
    recent_t = pd.DataFrame([
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=recent_off + 2),
         "Type": "TransactionType.PURCHASE", "Units": 80.0, "NAV": 18.0, "Amount": 1440.0},
        {"Fund": FUNDS[0], "Date": BASE + timedelta(days=recent_off + 20),
         "Type": "TransactionType.PURCHASE_SIP", "Units": 25.0, "NAV": 19.0, "Amount": 475.0},
    ])
    recent_h = pd.DataFrame([{
        "Fund": FUNDS[0], "ISIN": "INF000XRECENT", "Scheme_Code": "", "Units": 105.0,
        "NAV": 19.5, "Market Value": 2047.5,
    }])
    recent_stubs = _NavStubs(by_isin={
        "INF000XRECENT": _nav_series(rng, 60, start_nav=18.0, start_offset_days=recent_off),
    })

    cases = [
        ("empty df_t", pd.DataFrame(), df_h, bench, 365, nav_stubs),
        ("None df_t", None, df_h, bench, 365, nav_stubs),
        ("empty df_h", df_t, pd.DataFrame(), bench, 365, nav_stubs),
        ("None df_h", df_t, None, bench, 365, nav_stubs),
        # bench missing -> end_date falls back to today
        ("empty bench", recent_t, recent_h, pd.Series(dtype=float), 365, recent_stubs),
        ("None bench", recent_t, recent_h, None, 365, recent_stubs),
        ("bench all NaN -> dropna empties it", recent_t, recent_h,
         pd.Series([np.nan] * 30, index=pd.date_range(BASE, periods=30, freq="D")), 9999,
         recent_stubs),
        ("single txn", single, single_h, bench, 90, nav_stubs),
        ("fully redeemed then re-entered", fully_redeemed, single_h, bench, 9999, nav_stubs),
        ("zero-unit rows", zero_units, single_h, bench, 9999, nav_stubs),
        ("txn fund missing from NAV map", unknown_fund, single_h, bench, 9999, nav_stubs),
        ("bench with weekend gaps", df_t, df_h, bench[bench.index.dayofweek < 5], 9999, nav_stubs),
        ("bench entirely before txns", df_t, df_h,
         _nav_series(rng, 30, start_offset_days=-400), 9999, nav_stubs),
        ("period_days 0", df_t, df_h, bench, 0, nav_stubs),
        ("period_days 1", df_t, df_h, bench, 1, nav_stubs),
    ]

    for label, t, h, b, pdays, stubs in cases:
        stubs.install(monkeypatch)
        _assert_pair(
            reference_compute_period_comparison, compute_period_comparison,
            (t, h, 100_000.0, b, pdays), f"period_comparison {label}",
        )


def test_period_comparison_early_return_omits_market_value_key(monkeypatch):
    """The dict-shape quirk, pinned directly."""
    _NavStubs().install(monkeypatch)
    out = compute_period_comparison(pd.DataFrame(), pd.DataFrame(), 1000.0,
                                    pd.Series(dtype=float), 365)
    assert "market_value" not in out
    assert out["port_value"] == 1000.0
    assert out["use_xirr"] is False


def test_period_comparison_makes_no_network_calls(monkeypatch):
    """Guard: with the fetchers stubbed, nothing else in market_data may be reached."""
    rng = random.Random(4)
    df_t = _random_ledger(rng, n_funds=1, n_txns=5, span_days=30)
    df_h = _holdings_for(df_t, rng, isin_mode="isin")
    stubs = _nav_map_for(df_t, df_h, rng, points=50).install(monkeypatch)

    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("live HTTP attempted from compute_period_comparison")

    monkeypatch.setattr(market_data.requests.Session, "get", _boom, raising=True)
    compute_period_comparison(df_t, df_h, 50_000.0,
                              _nav_series(rng, 45, start_nav=9000.0), 9999)
    assert stubs.calls
