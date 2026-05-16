"""
routers/tabs/tax_strategy.py

Institutional Tax Strategy Lab & FIFO Harvesting Engine
=======================================================
Dedicated REST gateway for the Tax Strategy tab. Evaluates multi-asset FIFO capital gains across
custom financial years, enforces Budget 2024 taxation rules (12.5% LTCG, 20% STCG, ₹1.25L exemption),
and provides real-time tax harvesting simulation capabilities.
"""

from fastapi import APIRouter, HTTPException
from core.sessions import get_session
from core.config import TAX_RATES
from core.finance import compute_fifo_tax, compute_realized_tax_for_fy
from core.logic import CategorizationEngine
from datetime import datetime
import pandas as pd

router = APIRouter()

@router.get("/{session_id}/tax")
def get_tax_report(session_id: str, fy: str = "Current Portfolio"):
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    
    elss_df = df_h[df_h["Category"] == "ELSS"]
    equity_df = df_h[df_h["Category"].isin(["Equity", "ELSS", "Index"])]
    debt_df = df_h[df_h["Category"].isin(["Debt", "Liquid", "Gilt", "Bond"])]
    
    total_ltcg_gain = 0.0
    total_stcg_gain = 0.0
    total_stcg_debt_tax = 0.0
    total_withdrawals = 0.0
    
    equity_ltcg = 0.0
    debt_ltcg = 0.0
    equity_stcg = 0.0
    debt_stcg = 0.0
    ltcl = 0.0
    stcl = 0.0
    
    fund_breakdown = []
    elss_lockin_details = []

    is_current = (fy == "Current Portfolio")
    fy_start = None
    fy_end = None
    
    if not is_current:
        try:
            parts = fy.replace("FY ", "").split("-")
            start_year = int(parts[0])
            end_year = int("20" + parts[1]) if len(parts[1]) == 2 else int(parts[1])
            fy_start = datetime(start_year, 4, 1)
            fy_end = datetime(end_year, 3, 31, 23, 59, 59)
        except Exception as e:
            print(f"[TAX] Error parsing FY {fy}: {e}")
            is_current = True

    for fund_name in df_t["Fund"].unique():
        fund_txs = df_t[df_t["Fund"] == fund_name]
        
        fund_h = df_h[df_h["Fund"] == fund_name]
        if not fund_h.empty:
            cat = fund_h.iloc[0].get("Category", "Equity")
        else:
            cat = CategorizationEngine.detect_category(fund_name)
        
        debt_keywords = ["DEBT", "LIQUID", "GILT", "BOND", "INCOME", "SAVINGS"]
        is_debt = any(x in cat.upper() for x in debt_keywords) or any(x in fund_name.upper() for x in debt_keywords)

        if is_current:
            if fund_h.empty: continue
            units = float(fund_h.iloc[0]["Units"])
            nav = float(fund_h.iloc[0]["NAV"])
            result = compute_fifo_tax(fund_txs, units, nav, cat)
            
            if cat == "ELSS":
                elss_lockin_details.append({
                    "fund": fund_name, "units": result.get("lock_in_units", 0),
                    "gain": result.get("lock_in_gain", 0), "warning": result.get("lock_in_warning", "")
                })
                
            if is_debt:
                total_stcg_debt_tax += max(0, result["stcg_gain"] + result["ltcg_gain"]) * 0.30
                debt_ltcg += max(0, result["ltcg_gain"])
                debt_stcg += max(0, result["stcg_gain"])
                total_ltcg_gain += result["ltcg_gain"]
                total_stcg_gain += result["stcg_gain"]
            else:
                total_ltcg_gain += result["ltcg_gain"]
                total_stcg_gain += result["stcg_gain"]
                equity_ltcg += max(0, result["ltcg_gain"])
                equity_stcg += max(0, result["stcg_gain"])
            
            ltcl += abs(min(0, result["ltcg_gain"]))
            stcl += abs(min(0, result["stcg_gain"]))
                
            fund_breakdown.append({
                "fund": fund_name, "stcg_gain": result["stcg_gain"],
                "ltcg_gain": result["ltcg_gain"], "category": cat,
                "details": result.get("details", []), "withdrawal": 0
            })
        else:
            result = compute_realized_tax_for_fy(fund_txs, fy_start, fy_end, cat)
            
            mask = (df_t["Fund"] == fund_name) & (df_t["Date"] >= pd.to_datetime(fy_start, dayfirst=True)) & (df_t["Date"] <= pd.to_datetime(fy_end, dayfirst=True))
            period_txs = df_t[mask]
            withdrawal_amt = abs(period_txs[period_txs["Units"] < 0]["Amount"].sum())
            total_withdrawals += withdrawal_amt

            if result["ltcg_gain"] != 0 or result["stcg_gain"] != 0:
                if is_debt:
                    total_stcg_debt_tax += max(0, result["stcg_gain"] + result["ltcg_gain"]) * 0.30
                    debt_ltcg += max(0, result["ltcg_gain"])
                    debt_stcg += max(0, result["stcg_gain"])
                    total_ltcg_gain += result["ltcg_gain"]
                    total_stcg_gain += result["stcg_gain"]
                else:
                    total_ltcg_gain += result["ltcg_gain"]
                    total_stcg_gain += result["stcg_gain"]
                    equity_ltcg += max(0, result["ltcg_gain"])
                    equity_stcg += max(0, result["stcg_gain"])
                
                ltcl += abs(min(0, result["ltcg_gain"]))
                stcl += abs(min(0, result["stcg_gain"]))
                
            fund_breakdown.append({
                "fund": fund_name, "stcg_gain": result["stcg_gain"],
                "ltcg_gain": result["ltcg_gain"], "category": cat,
                "details": result.get("details", []), "withdrawal": withdrawal_amt
            })

    # Budget 2024 institutional tax slab calculations
    ltcg_equity_taxable = max(0, equity_ltcg - TAX_RATES["LTCG_EXEMPTION"])
    ltcg_equity_tax = ltcg_equity_taxable * TAX_RATES["LTCG_EQUITY"]
    
    ltcg_debt_tax = max(0, debt_ltcg) * 0.125
    stcg_equity_tax = max(0, equity_stcg) * 0.20
    stcg_debt_tax = max(0, debt_stcg) * 0.20
    
    total_tax = ltcg_equity_tax + ltcg_debt_tax + stcg_equity_tax + stcg_debt_tax
    
    return {
        "elss_value":    elss_df["Market Value"].sum(),
        "elss_invested": elss_df["Invested"].sum(),
        "elss_count":    len(elss_df),
        "equity_gain":   equity_df["Gain"].sum(),
        "debt_gain":     debt_df["Gain"].sum(),
        "ltcg_gain":     total_ltcg_gain,
        "stcg_gain":     total_stcg_gain,
        
        "ltcg_equity_tax":   ltcg_equity_tax,
        "ltcg_debt_tax":     ltcg_debt_tax,
        "stcg_equity_tax":   stcg_equity_tax,
        "stcg_debt_tax":     stcg_debt_tax,
        "total_tax":         total_tax,
        
        "equity_ltcg":   equity_ltcg,
        "debt_ltcg":     debt_ltcg,
        "equity_stcg":   equity_stcg,
        "debt_stcg":     debt_stcg,
        "ltcl":          ltcl,
        "stcl":          stcl,
        
        "total_withdrawals": total_withdrawals,
        "fund_breakdown": fund_breakdown,
        "elss_lockin":   elss_lockin_details
    }

@router.get("/{session_id}/tax/years")
def get_tax_years(session_id: str):
    """
    Compute available financial years from historical transaction ledger.
    """
    portfolio = get_session(session_id)
    df_t = portfolio.df_t
    if df_t.empty:
        return {"years": []}
        
    dates = pd.to_datetime(df_t["Date"], dayfirst=True)
    min_date = dates.min()
    max_date = datetime.now()
    
    def get_fy(d):
        if d.month >= 4: return d.year
        return d.year - 1
        
    start_fy = get_fy(min_date)
    end_fy = get_fy(max_date)
    
    fys = []
    for y in range(end_fy, start_fy - 1, -1):
        fys.append(f"FY {y}-{str(y+1)[2:]}")
        
    return {"years": fys}

@router.get("/{session_id}/tax/simulate")
def simulate_tax(session_id: str, fund: str, units_to_sell: float, nav: float = None):
    """
    Real-time FIFO tax harvesting simulation for a proposed redemption order.
    """
    portfolio = get_session(session_id)
    df_h = portfolio.df_h
    df_t = portfolio.df_t
    
    fund_h = df_h[df_h["Fund"] == fund]
    if fund_h.empty:
        raise HTTPException(status_code=404, detail="Fund not found in current holdings")
        
    effective_nav = nav if nav is not None else float(fund_h.iloc[0]["NAV"])
    cat = fund_h.iloc[0].get("Category", "Equity")
    fund_txs = df_t[df_t["Fund"] == fund]
    
    result = compute_fifo_tax(fund_txs, units_to_sell, effective_nav, cat)
    
    return {
        "fund": fund,
        "units_sold": units_to_sell,
        "nav": effective_nav,
        "ltcg_gain": round(result["ltcg_gain"], 2),
        "stcg_gain": round(result["stcg_gain"], 2),
        "total_tax": round(result["total_tax"], 2),
        "net_proceeds": round((units_to_sell * effective_nav) - result["total_tax"], 2),
        "lock_in_warning": result.get("lock_in_warning", None)
    }
