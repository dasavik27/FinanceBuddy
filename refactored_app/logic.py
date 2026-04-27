"""Business logic module extracted from app.py."""

import streamlit as st
import casparser
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pyxirr import xirr
from datetime import datetime, timedelta
import io, os
import warnings
warnings.filterwarnings("ignore")

BENCHMARKS = {
    "Nifty 50":      "^NSEI",
    "Sensex":        "^BSESN",
    "Nifty Midcap 150": "^NSMIDCP",
    "Nifty Smallcap 250": "^NSSMLCP",
    "Nifty Next 50": "^NSMIDCP",
}


PERIOD_MAP = {
    "1M": 30, "3M": 90, "6M": 180,
    "1Y": 365, "3Y": 1095, "5Y": 1825, "All": 9999
}


CATEGORY_COLORS = {
    "Equity": "#3B82F6", "Debt": "#10B981", "Hybrid": "#F59E0B",
    "ELSS": "#8B5CF6", "Liquid": "#06B6D4", "Index": "#6366F1",
    "FOF": "#F43F5E", "Other": "#94A3B8"
}


# ── Per-fund benchmark mapping (cap-type / category → TRI proxy) ──
FUND_BENCH_BY_CAP = {
    "Large Cap":       ("^NSEI",              "Nifty 50"),
    "Mid Cap":         ("^NSMIDCP",           "Nifty Midcap 150"),
    "Small Cap":       ("NIFTYSMALLCAP250.NS","Nifty SmallCap 250"),
    "Flexi/Multi Cap": ("^CNX500",            "Nifty 500"),
    "Index":           ("^NSEI",              "Nifty 50"),
    "Mixed":           ("^NSEI",              "Nifty 50"),
}
FUND_BENCH_BY_CAT = {
    "ELSS":   ("^NSEI",   "Nifty 50"),
    "Hybrid": ("^NSEI",   "Nifty 50"),
    "FOF":    ("^CNX500", "Nifty 500"),
    "Debt":   (None,      "CRISIL Composite Bond"),
    "Liquid": (None,      "CRISIL Liquid"),
    "Other":  ("^NSEI",   "Nifty 50"),
}


# Risk tiers (annual vol%, beta, label) — category-seeded heuristics
RISK_TIERS = {
    "Liquid":  (0.5,  0.02, "Very Low"),
    "Debt":    (3.5,  0.15, "Low"),
    "Hybrid":  (9.0,  0.55, "Moderate"),
    "ELSS":    (15.0, 0.90, "High"),
    "Index":   (13.0, 1.00, "Moderate-High"),
    "Equity":  (17.0, 1.10, "High"),
    "FOF":     (14.0, 0.80, "High"),
    "Other":   (10.0, 0.60, "Moderate"),
}
MAX_DD_ESTIMATE = {
    "Equity":45, "ELSS":42, "Index":38, "Hybrid":28,
    "FOF":38, "Debt":10, "Liquid":2, "Other":22,
}


SECTOR_COLORS = [
    "#3B82F6","#10B981","#F59E0B","#8B5CF6","#F43F5E",
    "#06B6D4","#6366F1","#EC4899","#14B8A6","#F97316"
]


# Approximate expense ratios (Direct / Regular) by category
EXP_RATIOS = {
    "Equity":  (0.50, 1.50), "ELSS":   (0.55, 1.60),
    "Index":   (0.10, 0.40), "Hybrid": (0.45, 1.40),
    "Debt":    (0.25, 0.85), "Liquid": (0.12, 0.35),
    "FOF":     (0.60, 1.70), "Other":  (0.45, 1.20),
}


# Goal-based timeline mapping
GOAL_TIMELINE = {
    "Liquid":  ("Emergency (0-6mo)", "#06B6D4", 0.5),
    "Debt":    ("Short Term (1-3yr)", "#10B981", 2),
    "Hybrid":  ("Medium Term (3-7yr)", "#F59E0B", 5),
    "ELSS":    ("Medium Term (3-7yr)", "#8B5CF6", 5),
    "Index":   ("Long Term (7yr+)", "#6366F1", 10),
    "Equity":  ("Long Term (7yr+)", "#3B82F6", 10),
    "FOF":     ("Long Term (7yr+)", "#F43F5E", 10),
    "Other":   ("Medium Term (3-7yr)", "#94A3B8", 5),
}


# Sector keywords for heuristic sector detection from fund names
SECTOR_KEYWORDS = {
    "Banking & Financial": ["BANKING", "BANK", "FINANCIAL", "PSU BANK", "NIFTY BANK"],
    "Technology": ["TECHNOLOGY", "TECH", "IT", "DIGITAL", "INNOVATION"],
    "Healthcare": ["PHARMA", "HEALTHCARE", "HEALTH"],
    "Infrastructure": ["INFRA", "INFRASTRUCTURE", "CONSTRUCTION"],
    "Consumer": ["CONSUMER", "FMCG", "CONSUMPTION", "RETAIL"],
    "Energy": ["ENERGY", "OIL", "GAS", "POWER", "PETROLEUM"],
    "Manufacturing": ["MANUFACTURING", "INDUSTRIAL", "CAPITAL GOODS", "ENGINEERING"],
    "Real Estate": ["REAL ESTATE", "REALTY", "HOUSING"],
    "Auto": ["AUTO", "AUTOMOBILE", "EV"],
    "Diversified": [],  # fallback
}


# ─────────────────────────────────────────────
# BACKEND: PARSE CAS PDF
# ─────────────────────────────────────────────
def fmt_inr(number: float) -> str:
    """Format number in Indian numbering system (Lakhs/Crores)."""
    try:
        if pd.isna(number):
            return "₹0"
        is_negative = number < 0
        num_str = str(abs(int(round(number))))
        if len(num_str) <= 3:
            res = num_str
        else:
            res = num_str[:-3]
            res = ",".join([res[max(i-2, 0):i] for i in range(len(res), 0, -2)][::-1]) + "," + num_str[-3:]
        return f"-₹{res}" if is_negative else f"₹{res}"
    except Exception:
        return "₹0"


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return val if val is not None else default
    val = getattr(obj, key, default)
    return val if val is not None else default


@st.cache_data(show_spinner=False)
def parse_cas(file_bytes: bytes, password: str):
    """Parse CAMS/KFintech CAS PDF. Zero disk retention after parsing."""
    try:
        with open("_vault_tmp.pdf", "wb") as f:
            f.write(file_bytes)


        data = casparser.read_cas_pdf("_vault_tmp.pdf", password)


        import os
        try:
            os.remove("_vault_tmp.pdf")
        except Exception:
            pass


        if "accounts" in data:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "NSDL CAS detected. FolioIQ requires a CAMS/KFintech Detailed CAS for transaction analytics."
            
        folios     = _get(data, 'folios', [])
        if not folios:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "No folios found in CAS. Make sure this is a 'Detailed' CAS."
            
        holdings   = []
        txns       = []
        sips       = []
        
        is_partial_cas = False


        for folio in folios:
            schemes = _get(folio, 'schemes', [])
            for scheme in schemes:
                name   = _get(scheme, 'scheme', "Unknown Scheme")
                isin   = _get(scheme, 'isin', "N/A") or "N/A"
                bal    = float(_get(scheme, 'close_calculated', _get(scheme, 'close', 0)) or 0)
                
                # Check for partial CAS (has opening balance but no transactions for it in this period)
                open_bal = float(_get(scheme, 'open', 0) or 0)
                if open_bal > 0:
                    is_partial_cas = True
                    
                if not bal:
                    txs = _get(scheme, 'transactions', []) or []
                    if txs:
                        bal = float(_get(txs[-1], 'balance', 0) or 0)
                val_obj = _get(scheme, 'valuation', {})
                cur_val = float(_get(val_obj, 'value', 0) or 0)
                nav    = float(_get(val_obj, 'nav', 0) or 0) if val_obj else 0
                cost   = float(_get(val_obj, 'cost', 0) or 0)


                # Derive fund metadata from scheme name
                category = _detect_category(name)
                plan     = "Regular" if any(x in name.upper() for x in ["REGULAR", "REG "]) else "Direct"
                amc      = _detect_amc(name)
                cap_type = _detect_cap_type(name)


                if bal > 0 or cur_val > 0:
                    # Use CAS cost value if available, else estimate from transactions
                    invested = cost if cost > 0 else _estimate_invested(scheme)
                    holdings.append({
                        "Fund":        name,
                        "ISIN":        isin,
                        "AMC":         amc,
                        "Category":    category,
                        "Plan":        plan,
                        "Cap Type":    cap_type,
                        "Units":       bal,
                        "NAV":         nav,
                        "Market Value": cur_val,
                        "Invested":    invested,
                        "Gain":        cur_val - invested,
                        "Gain%":       ((cur_val - invested) / invested * 100) if invested > 0 else 0,
                        "Weight%":     0.0,
                    })


                # Transactions
                txs_raw = _get(scheme, 'transactions', [])
                for tx in txs_raw:
                    t_date = _get(tx, 'date', None)
                    t_amt  = _get(tx, 'amount', 0)
                    t_type = _get(tx, 'type', 'N/A') or 'N/A'
                    t_nav  = _get(tx, 'nav', 0) or 0
                    t_units= _get(tx, 'units', 0) or 0
                    if t_date:
                        txns.append({
                            "Fund":     name,
                            "AMC":      amc,
                            "Category": category,
                            "Date":     pd.to_datetime(t_date),
                            "Amount":   float(t_amt or 0),
                            "Type":     str(t_type),
                            "NAV":      float(t_nav),
                            "Units":    float(t_units),
                        })
                        # Detect SIPs (recurring patterns)
                        if "SIP" in str(t_type).upper() or "SYSTEMATIC" in str(t_type).upper():
                            sips.append({
                                "Fund": name, "AMC": amc,
                                "Date": pd.to_datetime(t_date),
                                "Amount": abs(float(t_amt or 0)),
                                "NAV": float(t_nav),
                            })


        df_h = pd.DataFrame(holdings)
        if not df_h.empty:
            total_val = df_h["Market Value"].sum()
            if total_val > 0:
                df_h["Weight%"] = df_h["Market Value"] / total_val * 100


        df_t = pd.DataFrame(txns)
        df_s = pd.DataFrame(sips)
        return df_h, df_t, df_s, None, is_partial_cas


    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), str(e), False








def _detect_category(name: str) -> str:
    n = name.upper()
    if "ELSS" in n or "TAX SAVER" in n or "TAX SAVING" in n:
        return "ELSS"
    if any(x in n for x in ["LIQUID", "OVERNIGHT", "MONEY MARKET", "ULTRA SHORT"]):
        return "Liquid"
    if any(x in n for x in ["DEBT", "BOND", "GILT", "INCOME", "CREDIT RISK", "CORPORATE BOND", "BANKING AND PSU"]):
        return "Debt"
    if any(x in n for x in ["HYBRID", "BALANCED", "CONSERVATIVE", "AGGRESSIVE HYBRID", "EQUITY SAVINGS", "ARBITRAGE"]):
        return "Hybrid"
    if any(x in n for x in ["INDEX", "NIFTY", "SENSEX", "ETF", "FTF"]):
        return "Index"
    if "FOF" in n or "FUND OF FUND" in n or "OVERSEAS" in n or "INTERNATIONAL" in n:
        return "FOF"
    if any(x in n for x in ["EQUITY", "FLEXI", "MULTI CAP", "LARGE CAP", "MID CAP", "SMALL CAP",
                              "SECTORAL", "THEMATIC", "FOCUSED", "VALUE", "CONTRA", "DIVIDEND YIELD"]):
        return "Equity"
    return "Other"




def _detect_cap_type(name: str) -> str:
    n = name.upper()
    if "SMALL CAP" in n: return "Small Cap"
    if "MID CAP" in n or "MIDCAP" in n: return "Mid Cap"
    if "LARGE CAP" in n or "LARGECAP" in n: return "Large Cap"
    if "FLEXI CAP" in n or "MULTI CAP" in n: return "Flexi/Multi Cap"
    if "INDEX" in n or "NIFTY 50" in n or "SENSEX" in n: return "Index"
    return "Mixed"




def _detect_amc(name: str) -> str:
    amcs = {
        "Mirae": "Mirae Asset", "HDFC": "HDFC", "SBI": "SBI",
        "Axis": "Axis", "ICICI": "ICICI Prudential", "Kotak": "Kotak",
        "Nippon": "Nippon India", "DSP": "DSP", "Parag Parikh": "PPFAS",
        "Motilal": "Motilal Oswal", "Franklin": "Franklin Templeton",
        "Aditya Birla": "Aditya Birla SL", "UTI": "UTI", "Tata": "Tata",
        "Canara": "Canara Robeco", "Edelweiss": "Edelweiss",
        "Invesco": "Invesco", "L&T": "L&T", "BOI": "BOI AXA",
        "Sundaram": "Sundaram", "PGIM": "PGIM India", "Quant": "Quant",
    }
    for k, v in amcs.items():
        if k.upper() in name.upper():
            return v
    return "Other AMC"




def _estimate_invested(scheme) -> float:
    """Estimate invested amount using average cost calculation to correctly handle redemptions."""
    try:
        txs = _get(scheme, 'transactions', [])
        current_units = 0.0
        avg_cost = 0.0
        for tx in txs:
            amt   = abs(float(_get(tx, 'amount', 0) or 0))
            units = float(_get(tx, 'units', 0) or 0)
            
            if units > 0:
                new_units = current_units + units
                if new_units > 0:
                    avg_cost = (current_units * avg_cost + amt) / new_units
                current_units = new_units
            elif units < 0:
                current_units += units
                if current_units <= 1e-6:
                    current_units = 0.0
                    avg_cost = 0.0
        
        return current_units * avg_cost
    except Exception:
        return 0.0




# ─────────────────────────────────────────────
# BACKEND: MARKET DATA
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark(ticker: str, period_days: int = 365):
    """Fetch benchmark OHLCV from yfinance."""
    try:
        end   = datetime.now()
        start = end - timedelta(days=max(period_days + 90, 3650))  # At least 10 years for 5Y/ALL views
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




# ─────────────────────────────────────────────
# ANALYTICS ENGINE
# ─────────────────────────────────────────────
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
            
            # Ignore Dividend Reinvestments (no net cashflow)
            if "REINVEST" in t_type:
                continue
                
            if units > 0:
                # Purchase / Switch In -> Outflow
                ledger.append({"date": row["Date"], "amount": -amt})
            elif units < 0:
                # Redemption / Switch Out -> Inflow
                ledger.append({"date": row["Date"], "amount": amt})
            else:
                # Units == 0
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    ledger.append({"date": row["Date"], "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    ledger.append({"date": row["Date"], "amount": -amt})


        if not ledger:
            return 0.0
            
        ledger.append({"date": datetime.now(), "amount": current_value})
        ldf = pd.DataFrame(ledger).dropna()
        
        # XIRR requires at least one positive and one negative cashflow
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0
            
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result):
            return 0.0
            
        # Bound between -100% and 1000%
        return max(-100.0, min(float(result) * 100, 1000.0))
    except Exception:
        return 0.0




def compute_benchmark_xirr(df_t: pd.DataFrame, bench_series: pd.Series) -> tuple:
    """
    Simulate investing the same cash flows into the benchmark index.
    Returns (benchmark_xirr_pct, benchmark_current_value).
    
    Logic (like Zerodha/Groww/PowerUp Money):
    - For each purchase transaction, calculate how many benchmark "units" 
      you would have bought at that date's benchmark price.
    - For each redemption, calculate how many benchmark "units" you'd sell.
    - At the end, value all remaining units at today's benchmark price.
    - Calculate XIRR on these cash flows.
    """
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
            
            # Skip dividend reinvestments (no net cashflow)
            if "REINVEST" in t_type:
                continue
            
            # Find benchmark price on or before the transaction date
            mask = bench_series.index <= txn_date
            if mask.any():
                bench_price = float(bench_series[mask].iloc[-1])
            else:
                bench_price = float(bench_series.iloc[0])
            
            if bench_price <= 0:
                continue
            
            if units > 0:
                # Purchase / Switch In -> buy benchmark units
                bench_units_bought = amt / bench_price
                total_bench_units += bench_units_bought
                cashflows.append({"date": txn_date, "amount": -amt})
            elif units < 0:
                # Redemption / Switch Out -> sell benchmark units
                bench_units_sold = amt / bench_price
                total_bench_units = max(0, total_bench_units - bench_units_sold)
                cashflows.append({"date": txn_date, "amount": amt})
            else:
                # Dividends, taxes etc.
                if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                    cashflows.append({"date": txn_date, "amount": amt})
                elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                    cashflows.append({"date": txn_date, "amount": -amt})
        
        if not cashflows or total_bench_units <= 0:
            return 0.0, 0.0
        
        # Current benchmark value = remaining units × latest benchmark price
        current_bench_price = float(bench_series.iloc[-1])
        bench_current_value = total_bench_units * current_bench_price
        
        # Add final valuation as inflow
        today = datetime.now()
        cashflows.append({"date": today, "amount": bench_current_value})
        
        ldf = pd.DataFrame(cashflows).dropna()
        
        if ldf["amount"].min() >= 0 or ldf["amount"].max() <= 0:
            return 0.0, bench_current_value
        
        result = xirr(ldf["date"], ldf["amount"])
        if result is None or np.isnan(result) or not np.isfinite(float(result)):
            # Fallback: CAGR from total outflows → current bench value
            total_out = abs(ldf[ldf["amount"] < 0]["amount"].sum())
            if total_out > 0 and bench_current_value > 0:
                earliest = ldf[ldf["amount"] < 0]["date"].min()
                years_held = max((datetime.now() - pd.Timestamp(earliest)).days, 1) / 365.25
                cagr = ((bench_current_value / total_out) ** (1.0 / years_held) - 1) * 100
                return max(-99.0, min(cagr, 200.0)), bench_current_value
            return 0.0, bench_current_value

        bench_xirr = max(-100.0, min(float(result) * 100, 200.0))  # cap at 200% (realisitic max)
        return bench_xirr, bench_current_value
    except Exception:
        return 0.0, 0.0




def _get_bench_price(bench_series, target_date):
    """Get benchmark price on or before target_date. Falls back to nearest available."""
    if bench_series.empty:
        return 0.0
    target_ts = pd.Timestamp(target_date)
    mask = bench_series.index <= target_ts
    if mask.any():
        return float(bench_series[mask].iloc[-1])
    # If target_date is before all benchmark data, use earliest available
    return float(bench_series.iloc[0])




def _build_cashflow_list(df_t):
    """Build a list of (date, amount, units) tuples from a transaction DataFrame, 
    skipping dividend reinvestments and zero-amount transactions."""
    cashflows = []
    if df_t.empty or "Date" not in df_t.columns:
        return cashflows
    for _, row in df_t.iterrows():
        amt = abs(float(row.get("Amount", 0)))
        if amt == 0:
            continue
        t_type = str(row.get("Type", "")).upper()
        units = float(row.get("Units", 0))
        if "REINVEST" in t_type:
            continue
        cashflows.append((row["Date"], amt, units, t_type))
    return cashflows




def compute_period_comparison(df_t_all, total_value, bench_series, period_days):
    """
    Compute Portfolio vs Benchmark comparison for a given date-filter period.
    
    This is the CORE logic for the Overview tab. It correctly handles:
    1. Pre-existing portfolio value before the filter range (treated as lumpsum)
    2. All SIPs/redemptions within the period
    3. Benchmark simulation using index prices on transaction dates
    4. Absolute returns for <3Y, XIRR for >=3Y
    5. Cumulative growth time-series for charting
    
    Returns dict with: port_pct, bench_pct, port_value, bench_value, 
                        use_xirr, port_growth_series, bench_growth_series
    """
    result = {
        "port_pct": 0.0, "bench_pct": 0.0,
        "port_value": total_value, "bench_value": 0.0,
        "use_xirr": period_days >= 1095,
        "port_start_value": 0.0,
    }
    
    if bench_series.empty or total_value <= 0:
        return result
    
    # ── Step 1: Determine period boundaries ──
    bench_end_date = bench_series.index[-1]
    if period_days < 9999:
        period_start_date = bench_end_date - timedelta(days=period_days)
    else:
        # "ALL" — use the earliest of (first transaction, first bench data)
        if not df_t_all.empty and "Date" in df_t_all.columns:
            earliest_txn = df_t_all["Date"].min()
            period_start_date = min(earliest_txn, bench_series.index[0])
        else:
            period_start_date = bench_series.index[0]
    
    # Snap to nearest available benchmark date
    bench_after_start = bench_series[bench_series.index >= period_start_date]
    if bench_after_start.empty:
        bench_after_start = bench_series
    period_start_date = bench_after_start.index[0]
    bench_price_start = float(bench_after_start.iloc[0])
    bench_price_end = float(bench_series.iloc[-1])
    
    if bench_price_start <= 0:
        return result
    
    # ── Step 2: Split transactions into before-period and within-period ──
    all_cfs = _build_cashflow_list(df_t_all)
    
    # Transactions BEFORE the period start (used to estimate starting portfolio value)
    txns_before = [(d, a, u, t) for d, a, u, t in all_cfs if d < period_start_date]
    # Transactions WITHIN the period
    txns_in_period = [(d, a, u, t) for d, a, u, t in all_cfs if d >= period_start_date]
    
    # ── Step 3: Estimate portfolio value at period start ──
    # Method: total_value_now = port_value_at_start * (price_growth) + net_new_investments * (partial_growth)
    # Approximation: port_value_at_start ≈ total_value - sum_of_all_investments_in_period - gains_on_those_investments
    # Better: Use the invested amount before the period and apply the benchmark growth to estimate
    
    # Calculate total net cash invested during the period
    net_invested_in_period = 0.0
    for d, amt, units, t_type in txns_in_period:
        if units > 0:
            net_invested_in_period += amt  # Money put in
        elif units < 0:
            net_invested_in_period -= amt  # Money taken out
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                net_invested_in_period -= amt
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                net_invested_in_period += amt
    
    # Estimate portfolio value at start: 
    # We reverse-engineer from current value by subtracting net new investments
    # and adjusting for the approximate market growth of those investments
    # For the pre-existing portfolio part, we use benchmark return to adjust
    bench_return_ratio = bench_price_end / bench_price_start  # e.g., 1.15 for 15% return
    
    # The investments made during the period would have grown partially
    # Approximate: each investment grows by the average of (full period return, 0%)
    # Better: weight by time remaining
    total_days_in_period = max((bench_end_date - period_start_date).days, 1)
    
    weighted_new_investment_value = 0.0
    for d, amt, units, t_type in txns_in_period:
        days_remaining = max((bench_end_date - d).days, 0)
        time_fraction = days_remaining / total_days_in_period
        # Approximate growth of this particular investment
        growth = bench_return_ratio ** time_fraction  # proxy using benchmark growth
        if units > 0:
            weighted_new_investment_value += amt * growth
        elif units < 0:
            weighted_new_investment_value -= amt * growth
        else:
            if "DIVIDEND" in t_type or "PAYOUT" in t_type:
                weighted_new_investment_value -= amt * growth
            elif "TAX" in t_type or "DUTY" in t_type or "FEE" in t_type:
                weighted_new_investment_value += amt * growth
    
    # port_value_at_start = (total_value - weighted_new_investment_value) / bench_return_ratio
    # This is the value that, if grown at the benchmark rate, would give us the non-SIP portion of today's value
    port_value_at_start = max(1.0, (total_value - weighted_new_investment_value) / bench_return_ratio)
    
    # Sanity check: if there were no transactions before the period, start value should be small/zero
    if not txns_before and period_days < 9999:
        # No pre-existing investments — port_value_at_start should be 0
        # All value came from investments within the period
        port_value_at_start = 0.0
    
    result["port_start_value"] = port_value_at_start


    # ── Step 4: Build cash flow lists for XIRR ──
    # Portfolio cash flows
    pcf_list = []
    if port_value_at_start > 0:
        pcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
    
    # Benchmark cash flows & unit tracking
    bcf_list = []
    bench_units = 0.0
    if port_value_at_start > 0:
        bcf_list.append({"date": period_start_date, "amount": -port_value_at_start})
        bench_units = port_value_at_start / bench_price_start
    
    # Add transactions within the period
    for d, amt, units, t_type in txns_in_period:
        bp = _get_bench_price(bench_series, d)
        if bp <= 0:
            bp = bench_price_start
        
        if units > 0:
            # Purchase → outflow
            pcf_list.append({"date": d, "amount": -amt})
            bcf_list.append({"date": d, "amount": -amt})
            bench_units += amt / bp
        elif units < 0:
            # Redemption → inflow
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
    
    # Final values
    today = datetime.now()
    pcf_list.append({"date": today, "amount": total_value})
    
    bench_sim_value = bench_units * bench_price_end
    bcf_list.append({"date": today, "amount": bench_sim_value})
    
    result["port_value"] = total_value
    result["bench_value"] = bench_sim_value


    # ── Step 5: Compute returns ──
    if not pcf_list or len(pcf_list) < 2:
        return result
    
    # Compute absolute returns (always available)
    total_outflow = sum(-cf["amount"] for cf in pcf_list if cf["amount"] < 0)
    total_inflow = sum(cf["amount"] for cf in pcf_list if cf["amount"] > 0)
    port_abs_ret = ((total_inflow / total_outflow) - 1) * 100 if total_outflow > 0 else 0.0
    
    bench_total_outflow = sum(-cf["amount"] for cf in bcf_list if cf["amount"] < 0)
    bench_total_inflow = sum(cf["amount"] for cf in bcf_list if cf["amount"] > 0)
    bench_abs_ret = ((bench_total_inflow / bench_total_outflow) - 1) * 100 if bench_total_outflow > 0 else 0.0
    
    use_xirr = period_days >= 1095  # 3Y+
    
    if use_xirr:
        # XIRR for 3Y/5Y/ALL
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
        # Absolute returns for short periods
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
    results = {"current_drag": 0.0, "direct_drag": 0.0, "regular_drag": 0.0,
               "lost_20yr_current": 0.0, "lost_20yr_if_regular": 0.0,
               "saved_by_direct": 0.0, "by_fund": []}
    for _, row in df_h.iterrows():
        lo, hi = EXP_RATIOS.get(row["Category"], (0.45, 1.20))
        er_current = lo if row["Plan"] == "Direct" else hi
        val = row["Market Value"]
        # Compound leakage over 20 years
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
    # Alpha (30 pts)
    alpha = xirr_val - bench_ret
    score += min(30, max(0, int(30 * (1 + alpha / 20))))
    # Diversification (25 pts)
    n_funds = len(df_h)
    score += 25 if n_funds >= 10 else int(25 * n_funds / 10)
    # Direct plan % (20 pts)
    if total > 0:
        direct_pct = df_h[df_h["Plan"] == "Direct"]["Market Value"].sum() / total
        score += int(20 * direct_pct)
    # HHI concentration (15 pts)
    weights = (df_h["Market Value"] / total).values if total > 0 else np.array([1.0])
    hhi = float(np.sum(weights**2))
    score += int(15 * (1 - hhi))
    # Category balance (10 pts)
    if total > 0:
        max_cat_pct = df_h.groupby("Category")["Market Value"].sum().max() / total
        score += int(10 * (1 - max_cat_pct))
    return min(100, max(0, score))




def sip_consistency_score(df_s: pd.DataFrame) -> float:
    """0-100 score for SIP regularity."""
    if df_s.empty or len(df_s) < 2 or "Date" not in df_s.columns:
        return 0.0
    df_s = df_s.copy()
    df_s["YearMonth"] = df_s["Date"].dt.to_period("M")
    months_with_sip = df_s["YearMonth"].nunique()
    total_months = (df_s["YearMonth"].max() - df_s["YearMonth"].min()).n + 1
    if total_months <= 0:
        return 0.0
    return round(min(months_with_sip / total_months * 100, 100), 1)




def stepup_sip_projection(monthly_sip: float, years: int, annual_return: float, stepup_pct: float) -> dict:
    """Compare flat SIP vs step-up SIP future value."""
    r_monthly = annual_return / 100 / 12
    # Flat SIP
    n = years * 12
    if r_monthly > 0:
        flat_fv = monthly_sip * ((1 + r_monthly)**n - 1) / r_monthly * (1 + r_monthly)
    else:
        flat_fv = monthly_sip * n
    flat_inv = monthly_sip * n
    # Step-up SIP
    stepup_fv = 0.0
    stepup_inv = 0.0
    current_sip = monthly_sip
    for year in range(years):
        for month in range(12):
            months_remaining = (years - year) * 12 - month
            if r_monthly > 0:
                stepup_fv += current_sip * (1 + r_monthly) ** months_remaining
            else:
                stepup_fv += current_sip
            stepup_inv += current_sip
        current_sip *= (1 + stepup_pct / 100)
    return {
        "flat_fv": flat_fv, "flat_inv": flat_inv, "flat_gain": flat_fv - flat_inv,
        "stepup_fv": stepup_fv, "stepup_inv": stepup_inv, "stepup_gain": stepup_fv - stepup_inv,
        "extra_wealth": stepup_fv - flat_fv,
    }




# ─────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", size=12, color="#64748B"),
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#E2E8F0"),
    yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False, linecolor="#E2E8F0"),
)


def _layout(**kwargs) -> dict:
    return {**PLOTLY_LAYOUT, **kwargs}




def make_area_chart(x, y, color="#3B82F6", fill_color="rgba(59,130,246,0.1)", label=""):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=fill_color,
        name=label, hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f}<extra></extra>"
    ))
    fig.update_layout(**_layout(height=220))
    return fig




def make_donut(labels, values, colors):
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.68, marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        textinfo="none",
        hovertemplate="%{label}<br>%{value:,.0f} (%{percent})<extra></extra>"
    ))
    fig.update_layout(**_layout(height=260, showlegend=True,
        legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11))))
    return fig




def make_bar_chart(labels, values, colors=None, horizontal=False, title=""):
    if horizontal:
        fig = go.Figure(go.Bar(
            y=labels, x=values,
            orientation="h",
            marker=dict(color=colors or "#3B82F6", cornerradius=4),
            hovertemplate="%{y}<br>%{x:,.2f}%<extra></extra>"
        ))
        fig.update_layout(**_layout(height=max(180, len(labels)*36),
            xaxis=dict(showgrid=True, gridcolor="#F1F5F9"),
            yaxis=dict(showgrid=False)))
    else:
        fig = go.Figure(go.Bar(
            x=labels, y=values,
            marker=dict(color=colors or "#3B82F6", cornerradius=4),
            hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>"
        ))
        fig.update_layout(**_layout(height=220))
    return fig




def make_waterfall(categories, values):
    colors = ["#10B981" if v >= 0 else "#EF4444" for v in values]
    fig = go.Figure(go.Bar(
        x=categories, y=values,
        marker=dict(color=colors, cornerradius=4),
        hovertemplate="%{x}<br>%{y:+.2f}%<extra></extra>"
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", line_width=1)
    fig.update_layout(**_layout(height=220))
    return fig




def make_gauge(value, max_val=100, label="Risk Score"):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": label, "font": {"size": 12, "color": "#64748B", "family": "DM Sans"}},
        number={"font": {"size": 28, "color": "#0F172A", "family": "DM Sans"}, "suffix": "/10"},
        gauge={
            "axis": {"range": [0, 10], "tickwidth": 0, "tickcolor": "#E2E8F0", "tickvals": []},
            "bar": {"color": "#3B82F6", "thickness": 0.3},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 3], "color": "#DCFCE7"},
                {"range": [3, 6], "color": "#FEF3C7"},
                {"range": [6, 10], "color": "#FEE2E2"},
            ],
        }
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=180,
        margin=dict(l=20, r=20, t=40, b=0),
        font=dict(family="DM Sans, sans-serif"))
    return fig
