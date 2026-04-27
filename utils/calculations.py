"""
Financial Calculations Engine
Portfolio analytics, returns computation, and performance metrics
"""

import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf
from pyxirr import xirr
from datetime import datetime, timedelta
from config import (
    FUND_BENCH_BY_CAP, FUND_BENCH_BY_CAT, SECTOR_KEYWORDS,
    EXP_RATIOS, RISK_TIERS
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark(ticker: str, period_days: int = 365):
    """Fetch benchmark OHLCV from yfinance."""
    try:
        end = datetime.now()
        start = end - timedelta(days=max(period_days + 90, 3650))
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return pd.Series(dtype=float)
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.squeeze().dropna()
        return close
    except Exception:
        return pd.Series(dtype=float)


def compute_xirr(df_t: pd.DataFrame, current_value: float) -> float:
    """Compute portfolio XIRR from transaction ledger."""
    if df_t.empty or current_value <= 0:
        return 0.0
    try:
        ledger = []
        for _, row in df_t.iterrows():
            amt = abs(float(row.get("Amount", 0)))
            if amt == 0:
                continue
            
            t_type = str(row.get("Type", "")).upper()
            units = float(row.get("Units", 0))
            
            if "REINVEST" in t_type:
                continue
                
            if units > 0:
                ledger.append({"date": row["Date"], "amount": -amt})
            elif units < 0:
                ledger.append({"date": row["Date"], "amount": amt})
            else:
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    ledger.append({"date": row["Date"], "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    ledger.append({"date": row["Date"], "amount": -amt})

        if not ledger:
            return 0.0
            
        ledger.append({"date": datetime.now(), "amount": current_value})
        ldf = pd.DataFrame(ledger).dropna()
        
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0
            
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result):
            return 0.0
            
        return max(-100.0, min(float(result) * 100, 1000.0))
    except Exception:
        return 0.0


def compute_benchmark_xirr(df_t: pd.DataFrame, bench_series: pd.Series) -> tuple:
    """Simulate investing same cashflows into benchmark index."""
    if df_t.empty or bench_series.empty:
        return 0.0, 0.0
    try:
        total_bench_units = 0.0
        cashflows = []
        
        for _, row in df_t.iterrows():
            amt = abs(float(row.get("Amount", 0)))
            if amt == 0:
                continue
            
            t_type = str(row.get("Type", "")).upper()
            units = float(row.get("Units", 0))
            txn_date = row["Date"]
            
            if "REINVEST" in t_type:
                continue
            
            mask = bench_series.index <= txn_date
            if mask.any():
                bench_price = float(bench_series[mask].iloc[-1])
            else:
                bench_price = float(bench_series.iloc[0])
            
            if bench_price <= 0:
                continue
            
            if units > 0:
                bench_units_bought = amt / bench_price
                total_bench_units += bench_units_bought
                cashflows.append({"date": txn_date, "amount": -amt})
            elif units < 0:
                bench_units_sold = amt / bench_price
                total_bench_units = max(0, total_bench_units - bench_units_sold)
                cashflows.append({"date": txn_date, "amount": amt})
            else:
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    cashflows.append({"date": txn_date, "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    cashflows.append({"date": txn_date, "amount": -amt})
        
        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0
        
        current_bench_price = float(bench_series.iloc[-1])
        bench_current_value = total_bench_units * current_bench_price
        
        today = datetime.now()
        cashflows.append({"date": today, "amount": bench_current_value})
        
        ldf = pd.DataFrame(cashflows).dropna()
        
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0, bench_current_value
        
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result):
            return 0.0, bench_current_value
        
        bench_xirr = max(-100.0, min(float(result) * 100, 1000.0))
        return bench_xirr, bench_current_value
    except Exception:
        return 0.0, 0.0


def _get_bench_price(bench_series, target_date):
    """Get benchmark price on or before target_date."""
    if bench_series.empty:
        return 0.0
    target_ts = pd.Timestamp(target_date)
    mask = bench_series.index <= target_ts
    if mask.any():
        return float(bench_series[mask].iloc[-1])
    return float(bench_series.iloc[0])


def _build_cashflow_list(df_t):
    """Build list of (date, amount, units) tuples from transaction DataFrame."""
    cashflows = []
    if df_t.empty or "Date" not in df_t.columns:
        return cashflows
    for _, row in df_t.iterrows():
        amt = abs(float(row.get("Amount", 0)))
        if amt == 0:
            continue
        units = float(row.get("Units", 0))
        t_type = str(row.get("Type", "")).upper()
        cashflows.append((row["Date"], amt, units, t_type))
    return cashflows


def compute_period_comparison(df_t_all, total_value, bench_series, period_days):
    """Compute Portfolio vs Benchmark comparison for a given period."""
    result = {
        "port_pct": 0.0, "bench_pct": 0.0,
        "port_value": total_value, "bench_value": 0.0,
        "use_xirr": period_days >= 1095,
        "port_start_value": 0.0,
    }
    
    if bench_series.empty or total_value <= 0:
        return result
    
    bench_end_date = bench_series.index[-1]
    if period_days < 9999:
        period_start_date = bench_end_date - timedelta(days=period_days)
    else:
        if not df_t_all.empty and "Date" in df_t_all.columns:
            earliest_txn = df_t_all["Date"].min()
            period_start_date = min(earliest_txn, bench_series.index[0])
        else:
            period_start_date = bench_series.index[0]
    
    bench_after_start = bench_series[bench_series.index >= period_start_date]
    if bench_after_start.empty:
        bench_after_start = bench_series
    period_start_date = bench_after_start.index[0]
    bench_price_start = float(bench_after_start.iloc[0])
    bench_price_end = float(bench_series.iloc[-1])
    
    if bench_price_start <= 0:
        return result
    
    all_cfs = _build_cashflow_list(df_t_all)
    txns_before = [(d, a, u, t) for d, a, u, t in all_cfs if d < period_start_date]
    txns_in_period = [(d, a, u, t) for d, a, u, t in all_cfs if d >= period_start_date]
    
    net_invested_in_period = 0.0
    for d, amt, units, t_type in txns_in_period:
        if units > 0:
            net_invested_in_period += amt
        elif units < 0:
            net_invested_in_period -= amt
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                net_invested_in_period -= amt
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                net_invested_in_period += amt
    
    bench_return_ratio = bench_price_end / bench_price_start
    total_days_in_period = max((bench_end_date - period_start_date).days, 1)
    
    weighted_new_investment_value = 0.0
    for d, amt, units, t_type in txns_in_period:
        days_remaining = max((bench_end_date - d).days, 0)
        time_fraction = days_remaining / total_days_in_period
        growth = bench_return_ratio ** time_fraction
        if units > 0:
            weighted_new_investment_value += amt * growth
        elif units < 0:
            weighted_new_investment_value -= amt * growth
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                weighted_new_investment_value -= amt * growth
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                weighted_new_investment_value += amt * growth
    
    port_value_at_start = max(1.0, (total_value - weighted_new_investment_value) / bench_return_ratio)
    
    if not txns_before and period_days < 9999:
        port_value_at_start = 0.0
    
    result["port_start_value"] = port_value_at_start

    pcf_list = []
    if port_value_at_start > 0:
        pcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
    
    bcf_list = []
    bench_units = 0.0
    if port_value_at_start > 0:
        bcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
        bench_units = port_value_at_start / bench_price_start
    
    for d, amt, units, t_type in txns_in_period:
        bp = _get_bench_price(bench_series, d)
        if bp <= 0:
            bp = bench_price_start
        
        if units > 0:
            pcf_list.append({"date": d, "amount": -amt})
            bcf_list.append({"date": d, "amount": -amt})
            bench_units += amt / bp
        elif units < 0:
            pcf_list.append({"date": d, "amount": amt})
            bcf_list.append({"date": d, "amount": amt})
            bench_units = max(0, bench_units - amt / bp)
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                pcf_list.append({"date": d, "amount": amt})
                bcf_list.append({"date": d, "amount": amt})
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                pcf_list.append({"date": d, "amount": -amt})
                bcf_list.append({"date": d, "amount": -amt})
    
    today = datetime.now()
    pcf_list.append({"date": today, "amount": total_value})
    
    bench_sim_value = bench_units * bench_price_end
    bcf_list.append({"date": today, "amount": bench_sim_value})
    
    result["port_value"] = total_value
    result["bench_value"] = bench_sim_value

    if not pcf_list or len(pcf_list) < 2:
        return result
    
    total_outflow = sum(-cf["amount"] for cf in pcf_list if cf["amount"] < 0)
    total_inflow = sum(cf["amount"] for cf in pcf_list if cf["amount"] > 0)
    port_abs_ret = ((total_inflow / total_outflow) - 1) * 100 if total_outflow > 0 else 0.0
    
    bench_total_outflow = sum(-cf["amount"] for cf in bcf_list if cf["amount"] < 0)
    bench_total_inflow = sum(cf["amount"] for cf in bcf_list if cf["amount"] > 0)
    bench_abs_ret = ((bench_total_inflow / bench_total_outflow) - 1) * 100 if bench_total_outflow > 0 else 0.0
    
    use_xirr = period_days >= 1095
    
    if use_xirr:
        try:
            pcf_df = pd.DataFrame(pcf_list).dropna()
            if pcf_df["amount"].min() < 0 and pcf_df["amount"].max() > 0:
                r = xirr(pcf_df["date"], pcf_df["amount"])
                result["port_pct"] = max(-100.0, min(float(r) * 100, 1000.0)) if r and not np.isnan(r) else port_abs_ret
            else:
                result["port_pct"] = port_abs_ret
        except Exception:
            result["port_pct"] = port_abs_ret
        
        try:
            bcf_df = pd.DataFrame(bcf_list).dropna()
            if bcf_df["amount"].min() < 0 and bcf_df["amount"].max() > 0:
                r = xirr(bcf_df["date"], bcf_df["amount"])
                result["bench_pct"] = max(-100.0, min(float(r) * 100, 1000.0)) if r and not np.isnan(r) else bench_abs_ret
            else:
                result["bench_pct"] = bench_abs_ret
        except Exception:
            result["bench_pct"] = bench_abs_ret
    else:
        result["port_pct"] = port_abs_ret
        result["bench_pct"] = bench_abs_ret
    
    result["use_xirr"] = use_xirr
    return result


def compute_rolling_returns(bench_series: pd.Series, periods_days: list) -> dict:
    """Compute point-to-point returns for given periods."""
    results = {}
    if bench_series.empty:
        return results
    now_idx = bench_series.index[-1]
    last_price = float(bench_series.iloc[-1])
    for d in periods_days:
        cutoff = now_idx - timedelta(days=d)
        past = bench_series[bench_series.index >= cutoff]
        if len(past) >= 2:
            first = float(past.iloc[0])
            results[d] = ((last_price / first) - 1) * 100 if first > 0 else 0.0
        else:
            results[d] = 0.0
    return results


def estimate_expense_drag(df_h: pd.DataFrame) -> float:
    """Estimated annual expense ratio drag in INR."""
    drag = 0.0
    for _, row in df_h.iterrows():
        lo, hi = EXP_RATIOS.get(row["Category"], (0.45, 1.20))
        er = lo if row["Plan"] == "Direct" else hi
        drag += row["Market Value"] * er / 100
    return drag


def expense_leakage_20yr(df_h: pd.DataFrame, annual_growth: float = 0.12) -> dict:
    """Calculate 20-year expense ratio leakage as lost opportunity cost."""
    results = {
        "current_drag": 0.0, "direct_drag": 0.0, "regular_drag": 0.0,
        "lost_20yr_current": 0.0, "lost_20yr_if_regular": 0.0,
        "saved_by_direct": 0.0, "by_fund": []
    }
    for _, row in df_h.iterrows():
        lo, hi = EXP_RATIOS.get(row["Category"], (0.45, 1.20))
        er_current = lo if row["Plan"] == "Direct" else hi
        val = row["Market Value"]
        fv_no_exp = val * (1 + annual_growth) ** 20
        fv_with_exp = val * (1 + annual_growth - er_current / 100) ** 20
        fv_with_direct = val * (1 + annual_growth - lo / 100) ** 20
        fv_with_regular = val * (1 + annual_growth - hi / 100) ** 20
        leak_current = fv_no_exp - fv_with_exp
        leak_if_regular = fv_no_exp - fv_with_regular
        results["current_drag"] += val * er_current / 100
        results["direct_drag"] += val * lo / 100
        results["regular_drag"] += val * hi / 100
        results["lost_20yr_current"] += leak_current
        results["lost_20yr_if_regular"] += leak_if_regular
        results["saved_by_direct"] += (fv_with_direct - fv_with_exp) if row["Plan"] == "Regular" else 0
        results["by_fund"].append({
            "Fund": row["Fund"][:50], "Category": row["Category"],
            "Plan": row["Plan"], "ER%": er_current,
            "Annual Drag": val * er_current / 100,
            "20yr Leakage": leak_current,
        })
    return results


def elss_lock_in_analysis(df_h: pd.DataFrame, df_t: pd.DataFrame) -> list:
    """Analyze ELSS funds for 3-year lock-in status."""
    if df_t.empty or "Fund" not in df_t.columns:
        return []
    elss_funds = df_h[df_h["Category"] == "ELSS"]["Fund"].unique()
    results = []
    for fund in elss_funds:
        fund_txns = df_t[df_t["Fund"] == fund].sort_values("Date")
        if fund_txns.empty:
            continue
        earliest = fund_txns["Date"].min()
        lock_in_end = earliest + timedelta(days=3*365)
        now = pd.Timestamp(datetime.now())
        is_unlocked = now >= lock_in_end
        days_left = max(0, (lock_in_end - now).days) if not is_unlocked else 0
        fund_val = float(df_h[df_h["Fund"] == fund]["Market Value"].sum())
        fund_inv = float(df_h[df_h["Fund"] == fund]["Invested"].sum())
        results.append({
            "Fund": fund, "Earliest Investment": earliest,
            "Lock-in Ends": lock_in_end, "Unlocked": is_unlocked,
            "Days Left": days_left, "Value": fund_val,
            "Invested": fund_inv, "Gain": fund_val - fund_inv,
        })
    return results


def detect_sector(name: str) -> str:
    """Heuristic sector detection from fund name."""
    n = name.upper()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in n for kw in keywords):
            return sector
    return "Diversified"


def compute_portfolio_score(df_h: pd.DataFrame, xirr_val: float, bench_ret: float) -> int:
    """Composite 0-100 portfolio health score."""
    if df_h.empty:
        return 0
    score = 0
    total = df_h["Market Value"].sum()
    alpha = xirr_val - bench_ret
    score += min(30, max(0, int(30 * (1 + alpha / 20))))
    n_funds = len(df_h)
    score += 25 if n_funds >= 10 else int(25 * n_funds / 10)
    if total > 0:
        direct_pct = df_h[df_h["Plan"] == "Direct"]["Market Value"].sum() / total
        score += int(20 * direct_pct)
    weights = (df_h["Market Value"] / total).values if total > 0 else np.array([1.0])
    hhi = float(np.sum(weights**2))
    score += int(15 * (1 - hhi))
    if total > 0:
        max_cat_pct = df_h.groupby("Category")["Market Value"].sum().max() / total
        score += int(10 * (1 - max_cat_pct))
    return min(100, max(0, score))
