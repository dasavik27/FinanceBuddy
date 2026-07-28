from fastapi import APIRouter
from domains.mutual_funds.sessions import get_session
import pandas as pd
from typing import Dict, Any
from domains.mutual_funds.finance import compute_period_comparison
from shared.services.market_indices import fetch_benchmark_series
import logging
logger = logging.getLogger(__name__)


router = APIRouter()

@router.get("/{session_id}")
def get_journey_data(session_id: str) -> Dict[str, Any]:
    """
    Returns data for the Wealth Journey timeline.
    - Monthly/Yearly SIP & flow aggregations.
    - Capital accumulation curve over time.
    - Historical Market Value curve.
    - Best and worst performing funds.
    """
    portfolio = get_session(session_id)
    df_t = portfolio.df_t
    df_h = portfolio.df_h
    
    # 1. Capital Accumulation Curve & Monthly/Yearly Flows
    monthly_flows = {}
    yearly_flows = {}
    capital_curve_raw = []
    
    if not df_t.empty and 'Date' in df_t.columns:
        # Sort chronologically
        df_t_sorted = df_t.sort_values(by="Date").copy()
        
        cumulative_invested = 0.0
        
        for _, row in df_t_sorted.iterrows():
            date = row['Date']
            if pd.isnull(date): continue
            
            amount = float(row.get('Amount', 0.0))
            units = float(row.get('Units', 0.0))
            tx_type = str(row.get('Type', '')).lower()
            
            if "opening" in tx_type or "closing" in tx_type:
                continue
                
            is_inflow = units > 0 or "purchase" in tx_type or "sip" in tx_type or "reinvestment" in tx_type or "switch in" in tx_type
            is_outflow = units < 0 or "redemption" in tx_type or "switch out" in tx_type
            
            flow_amt = 0.0
            if is_inflow:
                flow_amt = abs(amount)
            elif is_outflow:
                flow_amt = -abs(amount)
                
            if flow_amt != 0:
                cumulative_invested += flow_amt
                
                month_key = date.strftime("%b %Y")  
                year_key = date.strftime("%Y")      
                
                if month_key not in monthly_flows:
                    monthly_flows[month_key] = {"period": month_key, "invested": 0, "withdrawn": 0, "net": 0}
                if year_key not in yearly_flows:
                    yearly_flows[year_key] = {"period": year_key, "invested": 0, "withdrawn": 0, "net": 0}
                
                if flow_amt > 0:
                    monthly_flows[month_key]["invested"] += flow_amt
                    yearly_flows[year_key]["invested"] += flow_amt
                else:
                    monthly_flows[month_key]["withdrawn"] += abs(flow_amt)
                    yearly_flows[year_key]["withdrawn"] += abs(flow_amt)
                    
                monthly_flows[month_key]["net"] += flow_amt
                yearly_flows[year_key]["net"] += flow_amt
                
                capital_curve_raw.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "invested": round(cumulative_invested, 2)
                })
                
    monthly_arr = list(monthly_flows.values())
    yearly_arr = list(yearly_flows.values())
    
    # Generate True Market Value Curve using Core Finance Engine
    # We fetch a dummy benchmark (e.g. Nifty 50) just to satisfy the comparison engine's need for an index,
    # but we will only extract the portfolio's absolute market value.
    try:
        bench_data = fetch_benchmark_series("^NSEI", 9999)
        comp = compute_period_comparison(df_t, df_h, portfolio.total_value, bench_data, 9999)
        
        market_dates = comp.get("dates", [])
        market_values = comp.get("market_value", [])
        
        # Merge Capital Invested with Market Value chronologically
        merged_curve = []
        pt_idx = 0
        curr_inv = 0.0
        for i in range(len(market_dates)):
            d_str = market_dates[i]
            
            # Fast-forward capital curve to include all transactions on or before this market date
            while pt_idx < len(capital_curve_raw) and capital_curve_raw[pt_idx]["date"] <= d_str:
                curr_inv = capital_curve_raw[pt_idx]["invested"]
                pt_idx += 1
                
            merged_curve.append({
                "date": d_str,
                "invested": curr_inv,
                "value": market_values[i]
            })
            
        # Downsample to weekly or monthly to avoid massive payload size for 5+ years
        # But wait, Recharts can handle 1000-2000 points. Let's just group by end of month
        curve_by_month = {}
        for pt in merged_curve:
            m_key = pt["date"][:7] # YYYY-MM
            curve_by_month[m_key] = {"date": m_key, "invested": pt["invested"], "value": pt["value"]}
            
        final_curve = list(curve_by_month.values())
        final_curve.sort(key=lambda x: x["date"])
        
        if not final_curve:
            raise Exception("Market curve is empty")
            
    except Exception as e:
        logger.error(f"Error computing market value curve: {e}")
        # Fallback to just capital invested
        curve_by_month = {}
        for pt in capital_curve_raw:
            m_key = pt["date"][:7]
            curve_by_month[m_key] = {"date": m_key, "invested": pt["invested"], "value": pt["invested"]}
        final_curve = list(curve_by_month.values())
        final_curve.sort(key=lambda x: x["date"])
    
    # 2. Hall of Fame & Shame (Best and Worst Funds)
    best_funds = []
    worst_funds = []
    
    if not df_h.empty and 'Gain%' in df_h.columns and 'Gain' in df_h.columns:
        # Sort by Gain% 
        # (Alternatively, could sort by Absolute Gain, but Gain% is a better performance metric)
        df_h_valid = df_h.dropna(subset=['Gain%']).copy()
        
        # Best funds (highest gain %)
        df_best = df_h_valid.sort_values(by="Gain%", ascending=False).head(5)
        # Worst funds (lowest gain %)
        df_worst = df_h_valid.sort_values(by="Gain%", ascending=True).head(5)
        
        for _, r in df_best.iterrows():
            best_funds.append({
                "fund": r.get("Fund", "Unknown"),
                "gain_pct": float(r.get("Gain%", 0.0)),
                "gain_abs": float(r.get("Gain", 0.0)),
                "invested": float(r.get("Invested", 0.0))
            })
            
        for _, r in df_worst.iterrows():
            worst_funds.append({
                "fund": r.get("Fund", "Unknown"),
                "gain_pct": float(r.get("Gain%", 0.0)),
                "gain_abs": float(r.get("Gain", 0.0)),
                "invested": float(r.get("Invested", 0.0))
            })

    return {
        "status": "success",
        "monthly_flows": monthly_arr,
        "yearly_flows": yearly_arr,
        "capital_curve": final_curve,
        "best_funds": best_funds,
        "worst_funds": worst_funds
    }
