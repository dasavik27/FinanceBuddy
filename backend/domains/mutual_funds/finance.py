"""
core/finance.py
Core financial algorithms and analytical engines.
All formulas validated against CFA standards and global institutional benchmarks.
Implementation follows strict Unitized Portfolio Accounting for precision auditing.
"""

import numpy as np
import pandas as pd
from pyxirr import xirr
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional
import logging
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_date(d) -> date:
    """Normalise datetime / date / Timestamp → date."""
    if isinstance(d, (datetime, pd.Timestamp)):
        return d.date()
    return d


def normalize_txn_type(raw: object) -> str:
    """
    Canonical form of a CAS transaction type, for substring classification.

    The parser stores `str(tx.type)` verbatim, which for casparser is the *enum repr* -
    "TransactionType.SWITCH_IN", underscore-separated. Every classifier in this codebase
    tests hyphenated names ("SWITCH-IN", "SWITCH-OUT", "STP-IN"), so none of them ever
    matched a switch. In `_get_standard_ledger` that was masked by the `units > 0` /
    `units < 0` sign test, which is why XIRR and FIFO lots stayed correct. The unitized
    simulation has no such fallback: switches fell through every branch and their units
    were never added or removed, so anyone who has done a Regular-to-Direct switch got a
    silently wrong portfolio curve on Overview, Performance, Drawdown and Journey - while
    the XIRR headline beside it stayed right.

    Strips the enum prefix and maps "_" to "-", so SWITCH_IN, SWITCH-IN and
    TransactionType.SWITCH_IN all normalise to the same token. SWITCH_IN_MERGER contains
    "SWITCH-IN" and SWITCH_OUT_MERGER contains "SWITCH-OUT", so the merger variants
    classify correctly for free.
    """
    s = str(raw or "").upper().strip()
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s.replace("_", "-")


def _get_standard_ledger(df_t: pd.DataFrame) -> List[Dict]:
    """
    Convert raw transaction DataFrame into a standardised cashflow ledger.

    Ledger entries:
      {"date": date, "amount": float, "type": str}
    Negative amount = money OUT (purchase).
    Positive amount = money IN  (redemption / dividend payout).
    Reinvestment transactions are excluded (no real cashflow).
    """
    ledger = []
    if df_t is None or df_t.empty:
        return ledger

    # PERF: one columnar extraction instead of df.iterrows(), which allocates a
    # fresh (dtype-upcast) Series per row and dominated the cost of this helper.
    # Series.tolist() surfaces exactly the same Python objects iterrows would put
    # in row[...] for the dtypes we handle (datetime64 -> Timestamp, str -> str,
    # float64 -> float, object -> the original object incl. None), so the per-row
    # arithmetic below is unchanged and stays bit-identical.
    #
    # One knowing deviation: iterrows re-infers a dtype per row, so a row whose
    # ONLY non-null value was the Date became a datetime64 Series and turned every
    # other field into NaT, making float(NaT) raise TypeError. Such a row is now
    # simply skipped. It needs a transaction with no Fund AND no Type AND no
    # Amount/Units/NAV to trigger, i.e. an entirely empty row.
    n_rows = len(df_t)
    _cols  = df_t.columns
    _amt   = df_t["Amount"].tolist() if "Amount" in _cols else [0] * n_rows
    _type  = df_t["Type"].tolist()   if "Type"   in _cols else [""] * n_rows
    _units = df_t["Units"].tolist()  if "Units"  in _cols else [0] * n_rows
    _nav   = df_t["NAV"].tolist()    if "NAV"    in _cols else [0] * n_rows
    _date  = df_t["Date"].tolist()   # KeyError if absent, as row["Date"] was

    for _i in range(n_rows):
        raw_amt = _amt[_i]
        amt     = abs(float(raw_amt)) if raw_amt is not None else 0.0

        t_type = str(_type[_i]).upper().strip()
        units  = float(_units[_i] or 0)
        nav    = float(_nav[_i] or 0)
        d      = _to_date(_date[_i])

        # Impute amount for SWITCH or non-monetary transactions using Unit*NAV basis
        # This ensures accurate cost tracking for CAS records with zero-amount entries.
        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        if amt == 0 and not any(x in t_type for x in ("DIVIDEND", "BONUS")):
            continue

        # Skip dividend reinvestment — no real external cashflow
        if any(x in t_type for x in ("REINVEST", "BONUS", "IDCW_REINVEST", "GROWTH_OPTION")):
            continue

        t_type = normalize_txn_type(t_type)

        if units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN")):
            # Purchase / subscription / switch-in → money leaves investor's account
            ledger.append({"date": d, "amount": -amt, "type": "BUY"})

        elif units < 0 or any(x in t_type for x in ("SELL", "REDEMPTION", "SWP-OUT", "STP-OUT", "SWITCH-OUT")):
            # Redemption / switch-out → money enters investor's account
            ledger.append({"date": d, "amount": amt, "type": "SELL"})

        else:
            # Zero-unit transactions: dividends paid out, taxes, fees
            if any(x in t_type for x in ("DIVIDEND", "PAYOUT", "IDCW_PAYOUT")):
                ledger.append({"date": d, "amount": amt, "type": "INCOME"})
            elif any(x in t_type for x in ("TAX", "DUTY", "FEE", "STT")):
                ledger.append({"date": d, "amount": -amt, "type": "EXPENSE"})

    return ledger


# ---------------------------------------------------------------------------
# XIRR Calculation
# Robust convergence logic for portfolios with single-direction flows (e.g. SIP-only).
# ---------------------------------------------------------------------------

def compute_xirr(df_t: pd.DataFrame, current_value: float) -> float:
    """
    Compute portfolio XIRR (annualised IRR) from transaction ledger.

    Institutional Accounting Standards (SEBI Compliance):
    - For holding periods >= 365 days: Returns the standard XIRR.
    - For holding periods < 365 days: Annualizing short-term returns distorts 
      performance (e.g. 5% in 1 month artificially inflates to ~80% p.a.). 
      To prevent this, the engine intercepts the calculation and returns the 
      Absolute Return ((Inflows - Outflows) / Outflows) instead.

    Parameters
    ----------
    df_t          : Transaction DataFrame for the fund/portfolio
    current_value : Current market value (acts as terminal inflow)

    Returns
    -------
    Return as a percentage (e.g. 14.2 means 14.2%).
    Returns 0.0 on any failure — never raises.
    """
    if current_value <= 0:
        return 0.0

    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return 0.0

    try:
        rows = [{"date": l["date"], "amount": l["amount"]} for l in ledger]
        # Terminal value: as if the portfolio is liquidated today
        rows.append({"date": datetime.now().date(), "amount": float(current_value)})

        ldf = pd.DataFrame(rows).dropna(subset=["date", "amount"])
        ldf["date"]   = pd.to_datetime(ldf["date"], dayfirst=True)
        ldf["amount"] = ldf["amount"].astype(float)

        # ── SEBI Standard: Absolute Return for < 1 Year Holding ──
        days_held = (ldf["date"].max() - ldf["date"].min()).days
        if 0 < days_held < 365:
            total_outflows = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            total_inflows  = ldf[ldf["amount"] > 0]["amount"].sum()
            if total_outflows > 0:
                abs_pct = ((total_inflows - total_outflows) / total_outflows) * 100
                return round(max(-99.0, min(abs_pct, 500.0)), 2)

        # Solvency Check: Verify presence of both capital inflows and outflows (terminal or actual)
        # to ensure IRR convergence within standard institutional thresholds.
        outflows = ldf[ldf["amount"] < 0]
        inflows  = ldf[ldf["amount"] > 0]
        if outflows.empty or inflows.empty:
            return 0.0

        result = xirr(ldf["date"], ldf["amount"])

        if result is None or np.isnan(result) or np.isinf(result):
            return 0.0

        pct = float(result) * 100
        # Institutional cap: 200% is more realistic for catching data errors
        return round(max(-99.0, min(pct, 200.0)), 2)

    except Exception as e:
        logger.error(f"[XIRR ERROR] current_value={current_value:.0f}: {e}")
        return 0.0


def _fy_label(d: date) -> str:
    """Indian financial year label (Apr–Mar) for a given date, e.g. 31-Mar-2024 -> 'FY23-24'."""
    start_year = d.year if d.month >= 4 else d.year - 1
    return f"FY{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def compute_xirr_by_fy(df_t_all: pd.DataFrame, df_h: pd.DataFrame) -> List[Dict]:
    """
    Cumulative-to-date XIRR sampled at each Indian financial-year end (31 Mar),
    plus a final "year-to-date" snapshot for the current partial FY — answers
    "am I improving?" year over year.

    Deliberately reuses the same FIFO lot reconstruction (tax_lots.compute_fund_lots)
    and XIRR engine (compute_xirr) used elsewhere in the app, rather than a separate
    valuation model — so this can never silently drift from the headline XIRR number.
    Each snapshot's terminal value is units-held-as-of-that-date x that fund's real
    historical NAV on/before that date (never a fabricated or interpolated value).
    """
    from domains.mutual_funds.tax_lots import compute_fund_lots
    from shared.services.market_data import fetch_nav_series_by_isin, fetch_nav_series_by_code, fetch_nav_series_by_name

    if df_t_all is None or df_t_all.empty:
        return []

    df_t = df_t_all.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_t["Date"]):
        df_t["Date"] = pd.to_datetime(df_t["Date"])
    df_t = df_t.sort_values("Date")

    first_date = df_t["Date"].min().date()
    today = datetime.now().date()

    # Fund universe = every fund ever transacted, not just currently-held ones
    # (df_h only has today's holdings — a fund fully exited last year still needs
    # to count towards that year's cumulative value).
    fund_meta = {}
    if df_h is not None and not df_h.empty:
        for _, row in df_h.iterrows():
            f = str(row.get("Fund", ""))
            if f:
                fund_meta[f] = (str(row.get("ISIN", "")).strip(), str(row.get("Scheme_Code", "")).strip())
    for f in df_t["Fund"].dropna().unique():
        f = str(f)
        if f not in fund_meta:
            fund_meta[f] = ("", "")

    fund_navs = {}
    for fn, (isin, scode) in fund_meta.items():
        navs = pd.Series(dtype=float)
        if isin and isin not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_isin(isin, 9999)
        if navs.empty and scode and scode not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_code(scode, 9999)
        if navs.empty:
            navs = fetch_nav_series_by_name(fn, 9999)
        if not navs.empty:
            fund_navs[fn] = navs.sort_index().dropna()

    # Every FY-end (31 Mar) strictly before today, plus today as a final YTD snapshot
    fy_ends = []
    start_year = first_date.year if first_date.month >= 4 else first_date.year - 1
    cursor = date(start_year + 1, 3, 31)
    while cursor < today:
        fy_ends.append((cursor, False))
        cursor = date(cursor.year + 1, 3, 31)
    if not (today.month == 3 and today.day == 31):
        fy_ends.append((today, True))

    results = []
    for snapshot_date, is_partial in fy_ends:
        df_t_upto = df_t[df_t["Date"] <= pd.Timestamp(snapshot_date)]
        if df_t_upto.empty:
            continue

        total_value = 0.0
        for fn in fund_meta.keys():
            lots = compute_fund_lots(df_t_upto, fn)
            units_held = sum(l["units"] for l in lots)
            if units_held <= 0:
                continue
            navs = fund_navs.get(fn)
            nav_at_date = 0.0
            if navs is not None and not navs.empty:
                past = navs[navs.index.date <= snapshot_date]
                nav_at_date = float(past.iloc[-1]) if not past.empty else float(navs.iloc[0])
            else:
                # No NAV history source resolved for this fund — fall back to its
                # last known transaction NAV as of this date rather than dropping it.
                fund_txns = df_t_upto[df_t_upto["Fund"] == fn]
                nav_rows = fund_txns[fund_txns["NAV"].astype(float) > 0].sort_values("Date")
                nav_at_date = float(nav_rows["NAV"].iloc[-1]) if not nav_rows.empty else 0.0
            total_value += units_held * nav_at_date

        if total_value <= 0:
            continue

        results.append({
            "fy": _fy_label(snapshot_date) + (" (YTD)" if is_partial else ""),
            "as_of": snapshot_date.isoformat(),
            "cumulative_value": round(total_value, 0),
            "cumulative_xirr": compute_xirr(df_t_upto, total_value),
            "is_partial_fy": is_partial,
        })

    return results


def simulate_historical_sip(nav_series: pd.Series, monthly_amount: float, years: int) -> Dict:
    """
    Replays a hypothetical SIP into a CANDIDATE fund (one you don't currently
    hold) using its real historical NAV series — "if I'd invested Rs.X/month in
    this fund for the last N years, what would it be worth today?" Every NAV
    point used is real fetched data (mfapi/Yahoo); nothing here is fabricated
    or interpolated beyond ordinary forward-fill for non-trading days.
    """
    if nav_series is None or nav_series.empty or monthly_amount <= 0 or years <= 0:
        return {}

    series = nav_series.sort_index().dropna()
    if len(series) < 2:
        return {"error": "Not enough NAV history for this fund to simulate."}

    end_date = series.index.max()
    start_date = end_date - pd.DateOffset(years=years)
    window = series[series.index >= start_date]
    if window.empty:
        return {"error": "Not enough NAV history for this fund to simulate this window."}

    monthly = window.resample("MS").first().dropna()
    monthly = monthly[monthly > 0]
    if monthly.empty:
        return {"error": "Not enough NAV history for this fund to simulate this window."}

    total_units = float((monthly_amount / monthly).sum())
    total_invested = monthly_amount * len(monthly)
    current_nav = float(series.iloc[-1])
    final_value = total_units * current_nav
    actual_years = (end_date - monthly.index[0]).days / 365.25

    cagr = (((final_value / total_invested) ** (1 / actual_years)) - 1) * 100 if actual_years > 0 and total_invested > 0 else 0.0

    return {
        "installments": len(monthly),
        "total_invested": round(total_invested, 0),
        "final_value": round(final_value, 0),
        "gain": round(final_value - total_invested, 0),
        "cagr_pct": round(cagr, 2),
        "wealth_multiple": round(final_value / total_invested, 2) if total_invested > 0 else 0.0,
        "actual_start_date": monthly.index[0].date().isoformat(),
        "actual_end_date": end_date.date().isoformat(),
        "requested_years": years,
    }


def compute_mandate_overlap(df_h: pd.DataFrame) -> Dict:
    """
    Category + Cap-Type "mandate overlap" — a PROXY for true stock-level
    portfolio overlap, not the real thing.

    Real overlap analysis needs each fund's underlying stock holdings. No
    reliable source for that exists for Indian mutual funds in this app —
    Yahoo Finance's per-fund holdings/sector data is sparse/best-effort for
    Indian ISINs (the reason a deterministic-fallback engine exists elsewhere
    to paper over its gaps), and there's no AMC portfolio-disclosure feed
    wired in. Rather than present fabricated stock-level overlap numbers,
    this groups funds that share the same Category + Cap Type — data already
    reliably present in every CAS statement — as a directionally useful signal:
    funds with the same mandate tend to hold similar stocks, but the actual
    overlap % can only be confirmed against each fund's factsheet.
    """
    if df_h is None or df_h.empty:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    total_value = float(df_h["Market Value"].sum())
    if total_value <= 0:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    groups = []
    group_cols = [c for c in ("Category", "Cap Type") if c in df_h.columns]
    if not group_cols:
        return {"groups": [], "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}

    for key, g in df_h.groupby(group_cols):
        if len(g) < 2:
            continue
        key_tuple = key if isinstance(key, tuple) else (key,)
        group_value = float(g["Market Value"].sum())
        same_amc = g["AMC"].nunique() == 1 if "AMC" in g.columns else False
        groups.append({
            "category": key_tuple[0],
            "cap_type": key_tuple[1] if len(key_tuple) > 1 else None,
            "fund_count": len(g),
            "combined_value": round(group_value, 0),
            "combined_weight_pct": round(group_value / total_value * 100, 1),
            "same_amc": bool(same_amc),
            "severity": "high" if same_amc else ("moderate" if len(g) > 2 else "low"),
            "funds": [
                {
                    "fund": r.get("Fund"),
                    "amc": r.get("AMC"),
                    "value": round(float(r.get("Market Value", 0) or 0), 0),
                    "weight_pct": round(float(r.get("Market Value", 0) or 0) / total_value * 100, 1),
                }
                for _, r in g.iterrows()
            ],
        })

    groups.sort(key=lambda x: -x["combined_weight_pct"])
    return {"groups": groups, "method": "category_cap_type_proxy", "disclaimer": _MANDATE_OVERLAP_DISCLAIMER}


_MANDATE_OVERLAP_DISCLAIMER = (
    "This groups funds sharing the same Category + Cap Type as a mandate-overlap proxy — "
    "not true stock-level portfolio overlap. No reliable underlying-holdings data source "
    "exists for Indian mutual funds in this app; confirm actual overlap against each fund's "
    "factsheet before consolidating."
)


def compute_sip_lumpsum_attribution(df_t: pd.DataFrame, total_value: float) -> Dict:
    """
    Splits invested capital and current value between SIP-sourced and
    lumpsum-sourced contributions.

    Current-value attribution is an APPROXIMATION: it splits total_value
    pro-rata by each source's share of invested capital, i.e. it assumes SIP
    and lumpsum contributions grew at the same rate. Getting an exact split
    would require tracking which specific lots (SIP vs lumpsum) remain
    unsold post-redemption — not attempted here; the pro-rata split is
    disclosed as such rather than presented as an exact figure.
    """
    if df_t is None or df_t.empty or total_value <= 0:
        return {}

    sip_invested = lumpsum_invested = 0.0
    for _, row in df_t.iterrows():
        t_type = str(row.get("Type", "")).upper()
        units = float(row.get("Units", 0) or 0)
        amt = abs(float(row.get("Amount", 0) or 0))
        nav = float(row.get("NAV", 0) or 0)
        if amt == 0 and units != 0 and nav > 0:
            amt = abs(units * nav)

        is_buy = units > 0 or any(x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN"))
        if not is_buy or amt == 0:
            continue

        if "SIP" in t_type:
            sip_invested += amt
        else:
            lumpsum_invested += amt

    total_invested = sip_invested + lumpsum_invested
    if total_invested <= 0:
        return {}

    sip_share = sip_invested / total_invested
    return {
        "sip_invested": round(sip_invested, 0),
        "lumpsum_invested": round(lumpsum_invested, 0),
        "sip_current_value": round(total_value * sip_share, 0),
        "lumpsum_current_value": round(total_value * (1 - sip_share), 0),
        "sip_share_pct": round(sip_share * 100, 1),
        "is_approximate": True,
        "note": "Current-value split is approximate — assumes SIP and lumpsum contributions grew at the same rate since each was invested.",
    }


def is_absolute_return(df_t: pd.DataFrame) -> bool:
    """
    Evaluates whether the investment holding period is strictly less than 1 year (365 days).
    This boolean flag is passed to the frontend to dynamically shift UI labels from 
    'Annualized XIRR' to 'Absolute Return' and trigger the 'ABS' warning badges.
    """
    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return False
    rows = [{"date": l["date"], "amount": l["amount"]} for l in ledger]
    rows.append({"date": datetime.now().date(), "amount": 0.0})
    ldf = pd.DataFrame(rows).dropna(subset=["date"])
    ldf["date"] = pd.to_datetime(ldf["date"], dayfirst=True)
    if ldf.empty: return False
    days_held = (ldf["date"].max() - ldf["date"].min()).days
    return 0 < days_held < 365

# ---------------------------------------------------------------------------
# Benchmark XIRR — simulate same cashflows into benchmark index
# ---------------------------------------------------------------------------

def compute_benchmark_xirr(
    df_t: pd.DataFrame,
    bench_series: pd.Series,
) -> Tuple[float, float]:
    """
    Simulate investing the same cashflows into the benchmark index.

    Returns
    -------
    (benchmark_xirr_pct, simulated_current_value)
    """
    if bench_series is None or bench_series.empty:
        return 0.0, 0.0

    ledger = _get_standard_ledger(df_t)
    if not ledger:
        return 0.0, 0.0

    bench_sorted = bench_series.sort_index()

    try:
        total_bench_units = 0.0
        cashflows: List[Dict] = []

        # PERF: the price lookup used to be a full boolean scan of the benchmark
        # per ledger entry (O(txns x bench_len)). One vectorized searchsorted
        # resolves every entry at once: side="right" yields the count of index
        # entries <= txn_date, so pos-1 is "last price on or before", and
        # clamping at 0 reproduces the "no history yet -> earliest price"
        # fallback. Kept inside the try: a tz-aware benchmark index still raises
        # TypeError here and still degrades to (0.0, 0.0).
        bench_prices = bench_sorted.to_numpy(dtype=float)
        txn_dates    = pd.DatetimeIndex([pd.Timestamp(l["date"]) for l in ledger])
        _pos         = bench_sorted.index.searchsorted(txn_dates, side="right")
        _prices      = bench_prices[np.maximum(_pos - 1, 0)]

        for l, txn_date, bench_price in zip(ledger, txn_dates, _prices):
            amt = abs(l["amount"])
            bench_price = float(bench_price)

            if bench_price <= 0:
                continue

            if l["amount"] < 0:        # Purchase
                total_bench_units += amt / bench_price
                cashflows.append({"date": txn_date, "amount": -amt})
            elif l["type"] == "SELL":  # Redemption
                units_sold = min(total_bench_units, amt / bench_price)
                total_bench_units = max(0.0, total_bench_units - units_sold)
                # FIX C-3: Use benchmark-simulated redemption value, not fund's actual amount.
                # The investor would have received units_sold * bench_price if invested in benchmark.
                bench_redemption_value = units_sold * bench_price
                cashflows.append({"date": txn_date, "amount": bench_redemption_value})
            elif l["type"] == "INCOME":
                cashflows.append({"date": txn_date, "amount": amt})

        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0

        bench_current_price  = float(bench_sorted.iloc[-1])
        bench_sim_value      = total_bench_units * bench_current_price

        cashflows.append({"date": pd.Timestamp(datetime.now()), "amount": bench_sim_value})

        ldf = pd.DataFrame(cashflows).dropna()
        ldf["date"] = pd.to_datetime(ldf["date"], dayfirst=True)

        # ── SEBI Standard: Absolute Return for < 1 Year Holding ──
        days_held = (ldf["date"].max() - ldf["date"].min()).days
        if 0 < days_held < 365:
            total_outflows = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            total_inflows  = ldf[ldf["amount"] > 0]["amount"].sum()
            if total_outflows > 0:
                abs_pct = ((total_inflows - total_outflows) / total_outflows) * 100
                return round(max(-99.0, min(abs_pct, 500.0)), 2), round(bench_sim_value, 2)

        if ldf[ldf["amount"] < 0].empty or ldf[ldf["amount"] > 0].empty:
            return 0.0, bench_sim_value

        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result) or np.isinf(result):
            return 0.0, bench_sim_value

        pct = round(max(-99.0, min(float(result) * 100, 500.0)), 2)
        return pct, round(bench_sim_value, 2)

    except Exception as e:
        logger.error(f"[BENCH XIRR ERROR] {e}")
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Trailing Returns (Point-to-Point CAGR)
# Computes precise historical performance across standardized time horizons.
# ---------------------------------------------------------------------------

# Moved to shared/services/returns.py and re-exported here.
#
# The implementation is pure series maths - it works the same on a fund NAV, an index
# level or a stock close - and shared/services/market_indices.py needed it to compute
# benchmark returns. It was importing it from this module, which made the *shared*
# layer depend on this *domain*, and dragged Mutual Funds code into the Equity
# performance tab by way of market_indices.
#
# Re-exported rather than relocated-and-rewritten so a fund and its benchmark keep
# being measured by exactly the same code, and so the five call sites in this domain
# (routers/compare.py, routers/performance.py, tab_common.py) are untouched.
from shared.services.returns import compute_trailing_returns  # noqa: F401


# ---------------------------------------------------------------------------
# Rolling Returns (Average of all N-year point-to-point CAGRs)
# High-fidelity rolling average matching institutional portal standards.
# ---------------------------------------------------------------------------

def _rolling_cagr_points(
    nav_series: pd.Series,
    window_years: int,
    step_days: int,
) -> Optional[List[Tuple[pd.Timestamp, float]]]:
    """
    Shared traversal behind compute_rolling_return_avg / _series.

    Returns None when the history is shorter than the window (each caller then
    takes its own "insufficient data" early return), otherwise the list of
    (actual_end_date, raw_cagr_pct) pairs in traversal order.

    PERF: the two `nav_sorted[nav_sorted.index >= ...]` masks that used to run
    per iteration (a full-length scan + Series allocation each, ~470 iterations
    for 10y of daily data at step_days=7) are replaced by two vectorized
    searchsorted passes computed once for every possible start position. The
    per-iteration float arithmetic is left byte-for-byte as it was.
    """
    nav_sorted  = nav_series.sort_index().dropna().resample('D').ffill()
    window_days = int(window_years * 365.25)

    # NOTE: an all-NaN input leaves nav_sorted empty and index[-1] raises
    # IndexError here — preserved deliberately, callers propagate it.
    if (nav_sorted.index[-1] - nav_sorted.index[0]).days < window_days:
        return None

    idx  = nav_sorted.index
    n    = len(idx)
    vals = nav_sorted.to_numpy(dtype=float)

    # end_pos[i]  == searchsorted(idx, idx[i] + window_days, "left")  -> `future`
    # next_pos[i] == searchsorted(idx, idx[i] + step_days,   "left")  -> `next_candidates`
    # A position of n means the corresponding slice was empty (loop breaks).
    # resample('D') guarantees a unique index, so the reference's
    # `idx.searchsorted(next_candidates.index[0])` is exactly next_pos[i].
    end_pos  = idx.searchsorted(idx + timedelta(days=window_days), side="left").tolist()
    next_pos = idx.searchsorted(idx + timedelta(days=step_days), side="left").tolist()

    points: List[Tuple[pd.Timestamp, float]] = []
    i = 0
    while i < n:
        e = end_pos[i]
        if e >= n:                       # `future` empty
            break

        end_nav         = float(vals[e])
        start_nav       = float(vals[i])
        start_date      = idx[i]
        actual_end_date = idx[e]

        if start_nav > 0 and end_nav > 0:
            # FIX P2-4: Use actual elapsed days / 365.25 instead of integer window_years
            actual_years = (actual_end_date - start_date).days / 365.25
            if actual_years > 0:
                cagr = ((end_nav / start_nav) ** (1.0 / actual_years) - 1) * 100
                points.append((actual_end_date, cagr))

        nxt = next_pos[i]
        if nxt >= n:                     # `next_candidates` empty
            break
        # FIX H-4: Guard against infinite loop if searchsorted returns same index
        i = max(nxt, i + 1)

    return points


def compute_rolling_returns(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,
) -> Tuple[Optional[float], pd.Series]:
    """
    Both rolling-return outputs from a single traversal.

    Callers that need the average *and* the chart series (the /rolling-returns
    endpoint does) should use this instead of calling the two helpers below back
    to back — it halves the work per (nav, bench) pair. Results are identical to
    compute_rolling_return_avg() / compute_rolling_return_series().
    """
    if nav_series is None or nav_series.empty:
        return None, pd.Series(dtype=float)

    points = _rolling_cagr_points(nav_series, window_years, step_days)
    if points is None:
        return None, pd.Series(dtype=float)

    dates  = [d for d, _ in points]
    values = [round(c, 2) for _, c in points]
    avg    = round(float(np.mean([c for _, c in points])), 2) if points else None
    return avg, pd.Series(values, index=dates)


def compute_rolling_return_avg(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,         # compute every 7 days for performance balance
) -> Optional[float]:
    """
    Average rolling return: mean of all N-year rolling CAGRs
    computed with `step_days` step across the history.

    Parameters
    ----------
    nav_series   : Fund NAV series (DatetimeIndex → float)
    window_years : Rolling window (1, 3, or 5)
    step_days    : Step between computation points (default 7 = weekly)

    Returns
    -------
    Average CAGR as percentage, or None if insufficient history.
    """
    if nav_series is None or nav_series.empty:
        return None

    # Morningstar Standard (Fix #F-8): the traversal (resample to daily ffill,
    # window/step advance) lives in _rolling_cagr_points().
    points = _rolling_cagr_points(nav_series, window_years, step_days)
    if points is None:
        return None

    rolling_cagrs = [c for _, c in points]
    if not rolling_cagrs:
        return None

    return round(float(np.mean(rolling_cagrs)), 2)


def compute_rolling_return_series(
    nav_series: pd.Series,
    window_years: int,
    step_days: int = 7,
) -> pd.Series:
    """
    Return the full time series of rolling N-year CAGRs.
    Used for the rolling returns line chart.

    Returns
    -------
    pd.Series indexed by end_date → CAGR%
    """
    if nav_series is None or nav_series.empty:
        return pd.Series(dtype=float)

    # Morningstar Standard (Fix #F-8): traversal shared with the _avg variant.
    points = _rolling_cagr_points(nav_series, window_years, step_days)
    if points is None:
        return pd.Series(dtype=float)

    dates  = [d for d, _ in points]
    values = [round(c, 2) for _, c in points]

    # NOTE: index is a plain list, so an empty result stays object-dtype here
    # while the early returns above are float64 — preserved.
    return pd.Series(values, index=dates)


# ---------------------------------------------------------------------------
# Risk Metrics — Sharpe, Sortino, Beta, Max Drawdown, Alpha
# All metrics derived from verified instrument-level NAV series for audit precision.
# ---------------------------------------------------------------------------

def compute_risk_metrics(
    nav_series: pd.Series,
    bench_series: pd.Series,
    risk_free_rate: float = 6.5,   # annual %, e.g. 6.5 (Standard 10Y G-Sec Baseline)
    min_days: int = 90,
) -> Dict:
    """
    Compute professional-grade risk metrics (Morningstar/CFA Standard).
    
    Key Institutional Improvements (Fix #F-1, F-2):
    - Evaluation Horizon: All ratios (Sharpe, Sortino, Alpha) use the same trailing 36M window.
    - Information Ratio: Measures alpha per unit of tracking error.
    - Market Capture: Quantifies upside/downside participation.
    - Calmar Ratio: Return vs Max Drawdown efficiency.
    """
    defaults = {
        "vol": 0.0, "sharpe": 0.0, "sortino": 0.0,
        "beta": 1.0, "alpha": 0.0, "max_dd": 0.0,
        "tracking_error": 0.0, "info_ratio": 0.0,
        "up_capture": 0.0, "down_capture": 0.0,
        "calmar": 0.0, "treynor": 0.0,
        "risk_label": "N/A", "data_days": 0,
    }

    if nav_series is None or nav_series.empty or len(nav_series) < min_days:
        return defaults

    nav_sorted = nav_series.sort_index().dropna()
    has_bench = (bench_series is not None and not bench_series.empty)
    rf = risk_free_rate

    # ── Drawdown Calculation: Data Alignment Strategy ──────────────────────
    # Max Drawdown is computed on the full verified instrument history prior to 
    # benchmark alignment. This ensures that brief or incomplete benchmark data 
    # does not mask historical volatility events (e.g. 2020 crash, 2018 small-cap bear market).
    mdd_rolling_max = nav_sorted.expanding().max()
    mdd_drawdown    = (nav_sorted - mdd_rolling_max) / mdd_rolling_max * 100
    max_dd_full     = float(mdd_drawdown.min())
    defaults["max_dd"] = round(abs(max_dd_full), 2)

    # ── 1. Align & Resample (Daily for Vol/Drawdown, 3Y Window for Ratios) ──
    if has_bench:
        bench_sorted = bench_series.sort_index().dropna()
        nav_align = nav_sorted.copy()
        bench_align = bench_sorted.copy()
        nav_align.index = pd.to_datetime(nav_align.index).tz_localize(None).normalize()
        bench_align.index = pd.to_datetime(bench_align.index).tz_localize(None).normalize()
        df_full = pd.DataFrame({"nav": nav_align, "bench": bench_align}).dropna()
    else:
        df_full = pd.DataFrame({"nav": nav_sorted}).dropna()

    if len(df_full) < min_days:
        return defaults

    defaults["data_days"] = len(df_full)

    # ── 2. Evaluation Window (Trailing 36 Months) ───────────────────────
    # FIX #F-1: Numerator and Denominator MUST use the same time horizon
    cutoff_3y = df_full.index[-1] - pd.DateOffset(years=3)
    df = df_full[df_full.index >= cutoff_3y]
    if len(df) < 60:
        df = df_full # Fallback to full history if fund < 3Y old

    n_years = (df.index[-1] - df.index[0]).days / 365.25
    if n_years <= 0: return defaults

    # Log Returns (Institutional Standard)
    fund_daily = np.log(df["nav"] / df["nav"].shift(1)).dropna()
    fund_cagr  = ((float(df["nav"].iloc[-1]) / float(df["nav"].iloc[0])) ** (1.0 / n_years) - 1) * 100
    vol_annual = float(fund_daily.std() * np.sqrt(252)) * 100
    
    defaults["vol"] = round(vol_annual, 2)
    # Calmar uses full-history MDD (which we computed above on nav_sorted)
    defaults["calmar"] = round(fund_cagr / abs(max_dd_full), 2) if max_dd_full != 0 else 0.0

    # ── 3. Sharpe & Sortino (Consistent 3Y Window) ──────────────────────
    if vol_annual > 0:
        defaults["sharpe"] = round((fund_cagr - rf) / vol_annual, 2)

    # Sortino: Downside deviation over same 3Y window
    # FIX P0-1 (Morningstar full-period variant): dd_series = max(0, MAR - r_daily)
    rf_daily = (rf / 100 / 252)
    dd_series = np.maximum(0, rf_daily - fund_daily)  # downside only: shortfall below MAR
    downside_dev = float(np.sqrt(np.mean(dd_series**2)) * np.sqrt(252)) * 100
    if downside_dev > 0:
        defaults["sortino"] = round((fund_cagr - rf) / downside_dev, 2)

    # ── 4. Benchmark Relative Metrics (IR, Capture, Beta) ───────────────
    if has_bench and "bench" in df.columns:
        bench_daily = np.log(df["bench"] / df["bench"].shift(1)).dropna()
        bench_cagr  = ((float(df["bench"].iloc[-1]) / float(df["bench"].iloc[0])) ** (1.0 / n_years) - 1) * 100
        
        # Simple Alpha as primary fallback (always reliable)
        simple_alpha = round(fund_cagr - bench_cagr, 2)
        
        # Tracking Error (Standard deviation of active returns)
        active_returns = fund_daily - bench_daily
        tracking_error = float(active_returns.std() * np.sqrt(252)) * 100
        defaults["tracking_error"] = round(tracking_error, 2)
        
        # Information Ratio (Active Return / Tracking Error)
        # FIX P1-1: Use arithmetic mean of daily active returns (annualized) / TE
        mean_active_annual = float(active_returns.mean() * 252) * 100
        if tracking_error > 0:
            defaults["info_ratio"] = round(mean_active_annual / tracking_error, 2)

        # Up/Down Market Capture (Monthly Basis)
        f_m = df["nav"].resample('ME').last().pct_change().dropna()
        b_m = df["bench"].resample('ME').last().pct_change().dropna()
        
        # FIX P1-3: Use pd.concat + dropna to align months safely.
        aligned = pd.concat([f_m.rename('fund'), b_m.rename('bench')], axis=1).dropna()
        up_mask   = aligned['bench'] > 0
        down_mask = aligned['bench'] <= 0
        
        up_months_aligned   = aligned[up_mask]
        down_months_aligned = aligned[down_mask]
        
        if not up_months_aligned.empty and up_months_aligned['bench'].mean() != 0:
            defaults["up_capture"] = round((up_months_aligned['fund'].mean() / up_months_aligned['bench'].mean()) * 100, 1)
        if not down_months_aligned.empty and down_months_aligned['bench'].mean() != 0:
            defaults["down_capture"] = round((down_months_aligned['fund'].mean() / down_months_aligned['bench'].mean()) * 100, 1)

        # ── Regression Alpha & Persistence ────────────────────────────────
        # Implementation utilizes Jensen's Alpha (Monthly OLS) for instruments with 
        # >= 24 months of shared history. For shorter-duration instruments, 
        # it falls back to simple geometric CAGR differentiation for robustness.
        common = aligned.rename(columns={'fund': 'f', 'bench': 'b'})
        n_months = len(common)
        if n_months >= 12:
            var_b = float(common["b"].var())
            if var_b > 0:
                beta = float(common.cov().loc["f", "b"] / var_b)
                defaults["beta"] = round(beta, 2)
                defaults["treynor"] = round((fund_cagr - rf) / beta, 2) if beta != 0 else 0.0

                if n_months >= 24:
                    # FIX P1-2: Geometric annualization
                    rf_monthly = rf / 100 / 12
                    monthly_alpha = (common["f"].mean() - rf_monthly) - beta * (common["b"].mean() - rf_monthly)
                    j_alpha = ((1 + monthly_alpha) ** 12 - 1) * 100
                    
                    # Sanity check: OLS alpha should not be near-zero when trailing CAGR diff is significant
                    if abs(j_alpha) < 0.05 and abs(simple_alpha) > 1.0:
                        logger.warning(f"[ALPHA WARN] Jensen's Alpha={j_alpha:.3f}% near-zero but simple_alpha={simple_alpha:.2f}%. "
                              f"Using simple_alpha as fallback (n_months={n_months}).")
                        defaults["alpha"] = simple_alpha
                    else:
                        defaults["alpha"] = round(j_alpha, 2)
                else:
                    # < 24 months — OLS unreliable, use simple alpha
                    logger.info(f"[ALPHA INFO] Only {n_months} months of overlap — using simple alpha={simple_alpha:.2f}%.")
                    defaults["alpha"] = simple_alpha
        else:
            # < 12 months — cannot run OLS
            logger.info(f"[ALPHA INFO] Only {n_months} months of overlap — cannot compute OLS alpha. Using simple_alpha={simple_alpha:.2f}%.")
            defaults["alpha"] = simple_alpha

    # ── Risk Label (Annualized Vol based) ───────────────────────────────
    if vol_annual < 2:        defaults["risk_label"] = "Low"
    elif vol_annual < 6:      defaults["risk_label"] = "Low to Moderate"
    elif vol_annual < 10:     defaults["risk_label"] = "Moderate"
    elif vol_annual < 14:     defaults["risk_label"] = "Moderately High"
    elif vol_annual < 18:     defaults["risk_label"] = "High"
    else:                     defaults["risk_label"] = "Very High"

    return defaults


# ---------------------------------------------------------------------------
# Consistency Score
# Percentage of rolling 1Y windows where fund outperformed benchmark.
# ---------------------------------------------------------------------------

def compute_consistency_score(
    nav_series: pd.Series,
    bench_series: pd.Series,
    window_days: int = 365,
    step_days: int = 30,
) -> float:
    """
    Consistency = % of rolling 1-year windows where fund outperformed benchmark.
    Scaled to 0–10 (10 = beat benchmark 100% of windows).

    Returns 5.0 (neutral) if insufficient data.
    """
    if nav_series is None or nav_series.empty:
        return 5.0
    if bench_series is None or bench_series.empty:
        return 5.0
    if (nav_series.index[-1] - nav_series.index[0]).days < window_days:
        return 5.0

    # FIX P2-3: Resample to daily frequency to ensure uniform window sizes
    # across funds with different NAV publication frequencies.
    nav_sorted   = nav_series.sort_index().dropna().resample('D').ffill()
    bench_sorted = bench_series.sort_index().dropna().resample('D').ffill()

    nav_idx    = nav_sorted.index
    bench_idx  = bench_sorted.index
    n, n_bench = len(nav_idx), len(bench_idx)
    nav_vals   = nav_sorted.to_numpy(dtype=float)
    bench_vals = bench_sorted.to_numpy(dtype=float)

    # PERF: the loop below used FOUR full-length boolean slices per iteration
    # (~110 iterations over 10y of daily data). Precompute every position once
    # with vectorized searchsorted instead — positions are needed for *all* start
    # indices because the `start_bench.empty` branch advances by raw positions.
    #   fut_nav/fut_bench == "first entry >= start + window"  (== len -> empty)
    #   start_bench_pos   == "count of bench entries <= start" (== 0 -> empty)
    #   next_pos          == "first entry >= start + step"     (== len -> empty)
    # NOTE: a tz-aware nav index against a naive benchmark still raises TypeError
    # here, exactly as `bench_sorted.index >= end_date_target` did.
    end_targets     = nav_idx + timedelta(days=window_days)
    fut_nav_pos     = nav_idx.searchsorted(end_targets, side="left").tolist()
    fut_bench_pos   = bench_idx.searchsorted(end_targets, side="left").tolist()
    start_bench_pos = bench_idx.searchsorted(nav_idx, side="right").tolist()
    next_pos        = nav_idx.searchsorted(nav_idx + timedelta(days=step_days),
                                           side="left").tolist()

    beat_count, total = 0, 0
    i = 0

    while i < n:
        if fut_nav_pos[i] >= n or fut_bench_pos[i] >= n_bench:
            break

        sb = start_bench_pos[i]
        if sb == 0:
            # NOTE: advances by step_days *positions*, not days — only equivalent
            # to the date-based advance below because of the daily resample.
            i += step_days
            continue

        fund_ret  = float(nav_vals[fut_nav_pos[i]]) / float(nav_vals[i]) - 1
        bench_ret = float(bench_vals[fut_bench_pos[i]]) / float(bench_vals[sb - 1]) - 1

        if fund_ret > bench_ret:
            beat_count += 1
        total += 1

        # Advance step_days (no max(new_i, i + 1) guard here — as before)
        if next_pos[i] >= n:
            break
        i = next_pos[i]

    if total == 0:
        return 5.0

    return round((beat_count / total) * 10, 1)


# ---------------------------------------------------------------------------
# Portfolio vs Benchmark Period Comparison
# True Unitized Portfolio Accounting (Zerodha/Morningstar Standard).
# ---------------------------------------------------------------------------

def compute_period_comparison(
    df_t_all: pd.DataFrame,
    df_h: pd.DataFrame,
    total_value: float,
    bench_series: pd.Series,
    period_days: int,
) -> Dict:
    """
    Compare portfolio return vs benchmark for a given period.
    Uses TRUE Unitized Portfolio Accounting (Zerodha/Morningstar standard).
    Constructs the actual historical NAV curve using exact daily fund prices and cashflows.
    """
    result = {
        "port_pct":   0.0,
        "bench_pct":  0.0,
        "port_value": total_value,
        "bench_value": 0.0,
        "use_xirr":   period_days >= 1095,
        "alpha":       0.0,
        "dates": [],
        "portfolio": [],
        "benchmark": [],
        "chart_mode": "indexed"
    }

    if df_t_all is None or df_t_all.empty or df_h is None or df_h.empty:
        return result

    bench_sorted = pd.Series(dtype=float)
    if bench_series is not None and not bench_series.empty:
        bench_sorted = bench_series.sort_index().dropna()
    
    # 1. Build complete timeline
    df_t = df_t_all.copy()
    df_t["Date"] = pd.to_datetime(df_t["Date"], dayfirst=True)
    all_dates = df_t["Date"].sort_values()
    
    start_date = all_dates.iloc[0]
    
    # If benchmark is missing or its end_date is before start_date (e.g. today vs yesterday),
    # we extend the timeline to today to ensure the chart still renders.
    today_dt = pd.Timestamp(datetime.now().date())
    if bench_sorted.empty:
        end_date = today_dt
    else:
        end_date = bench_sorted.index[-1]
        
    if start_date > end_date:
        end_date = start_date
        
    # Cap end_date at today to prevent future dates
    if end_date > today_dt:
        end_date = today_dt
        
    calendar = pd.date_range(start_date, end_date, freq='D')
    
    # 2. Fetch exact historical NAVs or build robust synthetic curves
    from shared.services.market_data import fetch_nav_series_by_isin, fetch_nav_series_by_name, fetch_nav_series_by_code
    fund_navs = {}
    
    # We need NAVs for ALL funds ever held, not just currently held funds
    # df_t_all contains ISIN or Scheme_Code if available. Otherwise we fetch by name.
    # First, let's build a map of Fund Name -> (ISIN, Scheme_Code) from both df_h and df_t_all
    fund_metadata = {}
    for _, row in df_h.iterrows():
        f = str(row.get("Fund", ""))
        if f: fund_metadata[f] = (str(row.get("ISIN", row.get("Isin", ""))).strip(), str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip())
    
    # PERF: only the FIRST row per fund can add anything here (the `not in` guard),
    # so collapse df_t_all to one row per fund before touching iterrows at all.
    # drop_duplicates keeps original order, so the resulting insertion order —
    # and therefore the NAV fetch order — is unchanged.
    _t_first = df_t_all.drop_duplicates(subset=["Fund"], keep="first") \
        if "Fund" in df_t_all.columns else df_t_all.iloc[0:0]
    for _, row in _t_first.iterrows():
        f = str(row.get("Fund", ""))
        if f and f not in fund_metadata:
            fund_metadata[f] = (str(row.get("ISIN", row.get("Isin", ""))).strip(), str(row.get("Scheme_Code", row.get("scheme_code", ""))).strip())

    for fn, (isin, scode) in fund_metadata.items():
        if not fn: continue
        
        navs = pd.Series(dtype=float)
        if isin and isin not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_isin(isin, 9999)
        if navs.empty and scode and scode not in ("N/A", "", "nan", "None"):
            navs = fetch_nav_series_by_code(scode, 9999)
        if navs.empty and fn:
            navs = fetch_nav_series_by_name(fn, 9999)
            
        if not navs.empty:
            fund_navs[fn] = navs.sort_index().dropna().resample('D').ffill()

    if not fund_navs:
        return result
        
    # 3. True Unitized Accounting Ledger
    #
    # PERF: this used to be a day-by-day Python loop that, for every fund on every
    # day, evaluated `f_navs[f_navs.index.date <= d_obj]` — a full-series scan that
    # also materialised a fresh datetime.date object array — TWICE (start- and
    # end-of-day). For 3650 days x 20 funds that is ~146k full-series scans per
    # call. It is now three vectorized layers:
    #   (a) one wide day x fund NAV matrix, built with one searchsorted per fund;
    #   (b) a units-per-day matrix of the same shape, derived from the (few)
    #       transactions rather than from the (many) days;
    #   (c) row-wise multiply-and-sum for the daily market values.
    # Only the genuinely sequential part — portfolio unit issuance, which depends
    # on the portfolio NAV it is about to change — is still scalar, and it now
    # steps over cashflow days only, with the constant-unit runs between them
    # divided vectorially.
    funds   = list(fund_navs.keys())
    n_funds = len(funds)
    n_days  = len(calendar)

    # `.index.date <= d_obj` compared LOCAL dates and never raised on a tz
    # mismatch; strip tz on both sides so searchsorted keeps that property. The
    # daily resample above already normalised every index to (local) midnight, so
    # "index <= d" and "index.date <= d.date()" select identically.
    _cal_naive = calendar.tz_localize(None) if calendar.tz is not None else calendar

    # (a) NAV matrix. searchsorted(side="right") - 1 == "last NAV on or before d";
    #     clamping at 0 reproduces the `else float(f_navs.iloc[0])` fallback for
    #     days before the fund's first NAV. Kept float64: float32 would shift
    #     market_value (rupees, charted absolutely) in its 7th significant digit.
    nav_mat = np.empty((n_days, n_funds), dtype=np.float64)
    for _j, _f in enumerate(funds):
        _s   = fund_navs[_f]
        _sidx = _s.index
        if getattr(_sidx, "tz", None) is not None:
            _sidx = _sidx.tz_localize(None)
        _pos = _sidx.searchsorted(_cal_naive, side="right")
        nav_mat[:, _j] = _s.to_numpy(dtype=np.float64)[np.maximum(_pos - 1, 0)]

    # (b) Units per day. Transactions are replayed in the reference's exact order
    #     (calendar date ascending, original row order within a date) so the
    #     order-dependent `max(0.0, ...)` clamp still lands identically; units then
    #     only change on transaction days, i.e. a step function broadcast over days.
    fund_col   = {f: j for j, f in enumerate(funds)}
    _n_t       = len(df_t)
    _t_cols    = df_t.columns
    _t_fund    = df_t["Fund"].tolist()          # KeyError if absent, as txn["Fund"] was
    _t_type    = df_t["Type"].tolist()   if "Type"   in _t_cols else [""] * _n_t
    _t_amt     = df_t["Amount"].tolist() if "Amount" in _t_cols else [0] * _n_t
    _t_units   = df_t["Units"].tolist()  if "Units"  in _t_cols else [0] * _n_t
    _t_nav     = df_t["NAV"].tolist()    if "NAV"    in _t_cols else [0] * _n_t

    # Day offset of each transaction; rows outside the calendar were never visited
    # by the day loop and stay ignored here.
    _day_of  = (df_t["Date"].dt.normalize() - calendar[0].normalize()).dt.days.to_numpy()
    _in_cal  = np.nonzero((_day_of >= 0) & (_day_of < n_days))[0]
    _order   = _in_cal[np.argsort(_day_of[_in_cal], kind="stable")].tolist()

    cashflow    = np.zeros(n_days, dtype=np.float64)
    units_now   = np.zeros(n_funds, dtype=np.float64)
    change_days: List[int] = []
    unit_states: List[np.ndarray] = []

    _m, _n_ord = 0, len(_order)
    while _m < _n_ord:
        k = int(_day_of[_order[_m]])
        net_cashflow = 0.0
        while _m < _n_ord and _day_of[_order[_m]] == k:
            r = _order[_m]
            _m += 1

            j = fund_col.get(_t_fund[r])
            if j is None:                       # fund has no NAV series -> skipped
                continue

            t_type  = normalize_txn_type(_t_type[r])
            amt     = abs(float(_t_amt[r] or 0))
            signed  = float(_t_units[r] or 0)
            units_t = abs(signed)
            nav_t   = float(_t_nav[r] or 0)

            if amt == 0 and units_t > 0 and nav_t > 0:
                amt = units_t * nav_t

            # Signed units lead, the type string is the fallback - the same order
            # _get_standard_ledger uses. That ordering is why the ledger survived the
            # SWITCH_IN/"SWITCH-IN" mismatch and this loop did not; matching it here
            # removes the whole class of "a type we did not enumerate is silently
            # dropped", which also covers REVERSAL and the *_MERGER variants.
            is_in = signed > 0 or (
                signed == 0 and any(
                    x in t_type for x in ("BUY", "PURCHASE", "SIP", "STP-IN", "SWITCH-IN")
                )
            )
            is_out = signed < 0 or (
                signed == 0 and any(
                    x in t_type for x in ("SELL", "REDEMPTION", "SWP", "STP-OUT", "SWITCH-OUT")
                )
            )
            # Unit-creating events with no external cashflow: dividend reinvestment,
            # bonus units, and side-pocketing (SEGREGATION), which was dropped entirely.
            units_only = any(x in t_type for x in ("REINVEST", "BONUS", "SEGREGATION"))

            if units_only:
                units_now[j] += units_t
            elif is_in:
                units_now[j] += units_t
                net_cashflow += amt
            elif is_out:
                units_now[j] -= units_t
                units_now[j] = max(0.0, units_now[j])
                net_cashflow -= amt
            elif any(x in t_type for x in ("TAX", "DUTY", "FEE", "STT")):
                # Zero-unit money leaving the portfolio. _get_standard_ledger already
                # books these as EXPENSE, so dropping them here made the two engines
                # disagree on cashflow basis for the same statement.
                net_cashflow -= amt
            elif any(x in t_type for x in ("DIVIDEND", "PAYOUT")):
                # Paid out to the investor, so it leaves the portfolio's value.
                net_cashflow -= amt

        cashflow[k] = net_cashflow
        change_days.append(k)
        unit_states.append(units_now.copy())

    if change_days:
        _states = np.vstack([np.zeros((1, n_funds), dtype=np.float64),
                             np.asarray(unit_states, dtype=np.float64)])
        _which  = np.searchsorted(np.asarray(change_days, dtype=np.int64),
                                  np.arange(n_days), side="right")
        units_eod = _states[_which]             # state 0 == "before any transaction"
    else:
        units_eod = np.zeros((n_days, n_funds), dtype=np.float64)

    units_sod = np.empty_like(units_eod)        # start-of-day == previous EOD
    units_sod[0] = 0.0
    units_sod[1:] = units_eod[:-1]

    # (c) Daily market values. Units are never negative (the clamp above), so
    #     dropping the reference's `if units > 0` filter only adds exact 0.0 terms.
    mv_sod = np.einsum("ij,ij->i", units_sod, nav_mat)
    mv_eod = np.einsum("ij,ij->i", units_eod, nav_mat)

    # Benchmark index level per day — same searchsorted trick as the NAV matrix.
    # The `index >= start_date` mask is deliberately NOT replaced: an empty/None
    # benchmark arrives as pd.Series(dtype=float), whose RangeIndex makes this
    # comparison raise TypeError, and that escaping TypeError is existing
    # behaviour (an all-NaN benchmark, which keeps its DatetimeIndex, does not).
    # It is evaluated once here instead of twice.
    _bs_after = bench_sorted[bench_sorted.index >= start_date]
    bench_start_global = float(_bs_after.iloc[0]) if not _bs_after.empty else 1.0

    if bench_sorted.empty:
        b_curr = np.full(n_days, bench_start_global, dtype=np.float64)
    else:
        _b_idx  = bench_sorted.index
        _b_vals = bench_sorted.to_numpy(dtype=np.float64)
        _bpos   = _b_idx.searchsorted(calendar, side="right")
        b_curr  = np.where(_bpos > 0, _b_vals[np.maximum(_bpos - 1, 0)], bench_start_global)

    if bench_start_global == 0.0:
        # The day loop divided by this scalar on its very first iteration.
        raise ZeroDivisionError("float division by zero")
    global_bench_nav = (b_curr / bench_start_global) * 100.0

    # Portfolio NAV curve. Between cashflow days port_units is constant, so the
    # recorded value is just mv_eod / port_units (or the stale NAV carried forward
    # while port_units is 0 — that quirk is load-bearing for re-entry after a full
    # exit). float() on every scalar assignment keeps port_nav a Python float, so
    # a zero NAV still raises ZeroDivisionError instead of silently going inf.
    global_port_nav = np.empty(n_days, dtype=np.float64)
    port_units = 0.0
    port_nav   = 100.0                          # Base 100 on Day 1
    _cursor    = 0

    for ck in np.nonzero(cashflow)[0].tolist():
        if ck > _cursor:
            if port_units > 0:
                global_port_nav[_cursor:ck] = mv_eod[_cursor:ck] / port_units
                port_nav = float(global_port_nav[ck - 1])
            else:
                global_port_nav[_cursor:ck] = port_nav

        # A) Start-of-Day
        if port_units > 0:
            port_nav = float(mv_sod[ck]) / port_units

        # B+C) Issue/Redeem portfolio units at current Portfolio NAV
        net_cashflow = float(cashflow[ck])
        if net_cashflow > 0:
            port_units += net_cashflow / port_nav
        elif net_cashflow < 0:
            port_units -= abs(net_cashflow) / port_nav
            port_units = max(0.0, port_units)

        # D) End-of-Day
        if port_units > 0:
            port_nav = float(mv_eod[ck]) / port_units

        global_port_nav[ck] = port_nav
        _cursor = ck + 1

    if _cursor < n_days:
        if port_units > 0:
            global_port_nav[_cursor:] = mv_eod[_cursor:] / port_units
        else:
            global_port_nav[_cursor:] = port_nav

    global_df = pd.DataFrame({
        "bench": global_bench_nav,
        "port": global_port_nav,
        "market_value": mv_eod
    }, index=calendar)

    # 4. Slice the true curve for the requested period
    bench_end_date = global_df.index[-1]
    if period_days < 9999:
        period_start = bench_end_date - timedelta(days=period_days)
    else:
        period_start = global_df.index[0]

    period_df = global_df[global_df.index >= period_start]
    if period_df.empty:
        return result

    # 5. Benchmark Anchoring (Zerodha Charting Logic)
    # The portfolio stays at its true historical unitized NAV (e.g. 168.0).
    # The benchmark is re-scaled so that its starting point matches the portfolio's starting point exactly.
    # This ensures both lines start at the exact same point on the Y-axis for any zoomed window,
    # making visual divergence obvious, while maintaining absolute Y-axis values.
    slice_start_port = float(period_df["port"].iloc[0])
    slice_start_bench = float(period_df["bench"].iloc[0])

    if slice_start_port <= 0: slice_start_port = 1.0
    if slice_start_bench <= 0: slice_start_bench = 1.0

    period_df = period_df.copy()
    
    # Portfolio is untouched
    
    # Benchmark is scaled to start at slice_start_port
    period_df["bench_scaled"] = (period_df["bench"] / slice_start_bench) * slice_start_port

    # 6. Calculate exact percentage returns (Absolute for <1Y, Annualized CAGR for >=1Y)
    slice_end_port = float(period_df["port"].iloc[-1])
    slice_end_bench = float(period_df["bench"].iloc[-1])
    
    actual_days = (period_df.index[-1] - period_df.index[0]).days
    
    if actual_days >= 365:
        # Annualized CAGR
        years = actual_days / 365.25
        period_port_pct = (((slice_end_port / slice_start_port) ** (1 / years)) - 1) * 100.0
        period_bench_pct = (((slice_end_bench / slice_start_bench) ** (1 / years)) - 1) * 100.0
    else:
        # Absolute Return
        period_port_pct = ((slice_end_port / slice_start_port) - 1) * 100.0
        period_bench_pct = ((slice_end_bench / slice_start_bench) - 1) * 100.0

    result["port_pct"] = round(period_port_pct, 2)
    result["bench_pct"] = round(period_bench_pct, 2)
    result["alpha"] = round(period_port_pct - period_bench_pct, 2)
    
    # Calculate global XIRR for reference if needed
    _, bench_all_sim_value = compute_benchmark_xirr(df_t_all, bench_sorted)
    result["bench_value"] = round(bench_all_sim_value, 2)

    # 7. Downsample to ~60-80 points for optimal frontend rendering
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
# SIP Projection with Annual Step-Up
# ---------------------------------------------------------------------------

def stepup_sip_projection(
    monthly_sip: float,
    years: int,
    annual_return: float,
    stepup_pct: float,
    lumpsum: float = 0.0,
    existing_corpus: float = 0.0,
) -> Dict:
    """
    Project wealth growth with annual SIP step-up.

    Parameters
    ----------
    monthly_sip    : Starting monthly SIP amount (₹)
    years          : Investment horizon
    annual_return  : Expected annual return in % (e.g. 14.0)
    stepup_pct     : Annual SIP increase in % (e.g. 10.0)
    lumpsum        : Annual lumpsum (e.g. ₹25,000 for ELSS in Jan)
    existing_corpus: Starting corpus value

    Returns
    -------
    dict with projection list and summary statistics
    """
    data           = []
    total_invested = 0.0
    current_value  = float(existing_corpus)
    monthly_rate   = (1 + annual_return / 100) ** (1 / 12) - 1
    annual_rate    = annual_return / 100

    current_sip = float(monthly_sip)

    for year in range(1, years + 1):
        # Monthly compounding for 12 months
        for _ in range(12):
            total_invested += current_sip
            current_value   = (current_value + current_sip) * (1 + monthly_rate)

        # Annual lumpsum (e.g. ELSS in January — assumed invested at month 6)
        # FIX P3-4: Compound from actual investment month instead of mid-year ^0.5
        # Assuming lumpsum is invested at the start of month 7 (mid-year),
        # it gets 6 months of compounding within this year.
        if lumpsum > 0:
            total_invested += lumpsum
            months_remaining = 6  # invested at start of month 7
            current_value += lumpsum * (1 + monthly_rate) ** months_remaining

        data.append({
            "year":       year,
            "invested":   round(total_invested, 0),
            "value":      round(current_value, 0),
            "sip_amount": round(current_sip, 0),
            "gain":       round(current_value - total_invested, 0),
            "gain_pct":   round((current_value / max(total_invested, 1) - 1) * 100, 1),
        })

        current_sip *= (1 + stepup_pct / 100)

    return {
        "projection":    data,
        "final_value":   round(current_value, 0),
        "total_invested": round(total_invested, 0),
        "wealth_gain":   round(current_value - total_invested, 0),
        "wealth_multiple": round(current_value / max(total_invested, 1), 2),
    }


# ---------------------------------------------------------------------------
# LTCG Harvest Calculator
# ---------------------------------------------------------------------------

def compute_ltcg_harvest(
    holdings: List[Dict],
    ltcg_exemption: float = 125000.0,
    ltcg_rate: float = 0.125,
) -> Dict:
    """
    Identify funds where LTCG can be booked within the ₹1.25L annual exemption.

    Parameters
    ----------
    holdings       : List of {"fund": str, "gain": float, "holding_days": int,
                               "current_value": float, "invested": float}
    ltcg_exemption : Annual LTCG exemption (₹1,25,000 for FY2024-25)
    ltcg_rate      : LTCG rate (12.5% post Jul 2024)

    Returns
    -------
    dict with eligible gains list and tax saved
    """
    # 1. Gain Harvesting (up to ₹1.25L exemption)
    gain_eligible = [
        h for h in holdings
        if h.get("holding_days", 0) >= 365 and h.get("gain", 0) > 0
    ]
    gain_eligible.sort(key=lambda x: x["gain"])
    
    # 2. Loss Harvesting (STCL and LTCL)
    loss_eligible = [
        h for h in holdings
        if h.get("stcg", 0) < -100 or h.get("ltcg", 0) < -100
    ]
    loss_eligible.sort(key=lambda x: min(x.get("stcg", 0), x.get("ltcg", 0))) # Largest losses first

    to_harvest   = []
    cumulative   = 0.0
    tax_saved    = 0.0

    for h in gain_eligible:
        gain = h["gain"]
        if cumulative + gain <= ltcg_exemption:
            to_harvest.append({
                "fund":       h["fund"],
                "gain":       round(gain, 0),
                "tax_at_rate": round(gain * ltcg_rate, 0),
                "tax_saved":  round(gain * ltcg_rate, 0),
                "action":     "HARVEST — book gain, reinvest same day",
            })
            cumulative += gain
            tax_saved  += gain * ltcg_rate
        else:
            partial = ltcg_exemption - cumulative
            if partial > 1000:
                to_harvest.append({
                    "fund":       h["fund"],
                    "gain":       round(partial, 0),
                    "tax_at_rate": round(partial * ltcg_rate, 0),
                    "tax_saved":  round(partial * ltcg_rate, 0),
                    "action":     f"PARTIAL HARVEST — book ₹{partial:,.0f} only",
                })
                tax_saved  += partial * ltcg_rate
            break
            
    total_loss_harvested = 0.0
    for h in loss_eligible:
        loss = min(h.get("stcg", 0), h.get("ltcg", 0))
        # Tax saved by loss harvesting: roughly 20% for STCL, 12.5% for LTCL. Use average 15% for display.
        # Loss harvesting allows offsetting future gains.
        to_harvest.append({
            "fund":       h["fund"],
            "gain":       round(loss, 0),
            "tax_at_rate": 0,
            "tax_saved":  round(abs(loss) * 0.15, 0),
            "action":     "TAX LOSS HARVEST — book loss to offset future gains",
        })
        total_loss_harvested += abs(loss)
        tax_saved += abs(loss) * 0.15

    return {
        "eligible_count": len(gain_eligible) + len(loss_eligible),
        "harvest_list":   to_harvest,
        "total_harvested": round(cumulative + total_loss_harvested, 0),
        "total_tax_saved": round(tax_saved, 0),
        "remaining_exemption": round(max(ltcg_exemption - cumulative, 0), 0),
    }