"""
core/models.py
Domain models for the Finance Buddy engine.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from domains.mutual_funds.finance import compute_xirr, compute_benchmark_xirr, compute_period_comparison, is_absolute_return
from shared.services.market_indices import fetch_benchmark_series
from shared.config import BENCHMARKS, PERIOD_MAP, get_standard_category, EXP_RATIO_BANDS, TAX_RATES

class Portfolio:
    def __init__(self, df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool = False):
        self.df_h = df_h
        self.df_t = df_t
        self.df_s = df_s
        self.is_partial = is_partial
        self.total_value = float(df_h["Market Value"].sum()) if not df_h.empty else 0.0
        self.total_invested = float(df_h["Invested"].sum()) if not df_h.empty else 0.0
        # V11-1 FIX: Freeze original CAS PDF NAV at construction time,
        # BEFORE any live update can overwrite the NAV column.
        if not df_h.empty and "NAV" in df_h.columns and "CAS NAV" not in df_h.columns:
            self.df_h["CAS NAV"] = df_h["NAV"].copy()

    def update_live_navs(self, refresh: bool = False):
        """Re-fetch live NAVs from AMFI and update all holdings in memory."""
        if self.df_h.empty:
            return
        from shared.services.market_data import fetch_live_navs_with_date
        live_map, date_map = fetch_live_navs_with_date(refresh=refresh)
            
        def update_row(row):
            isin = row.get("ISIN")
            units = float(row.get("Units", 0) or 0)
            invested = float(row.get("Invested", 0) or 0)
                
            if live_map and isin and isin in live_map:
                new_nav = float(live_map[isin])
                cas_nav = float(row.get("CAS NAV", 0))
                
                # Prevent Liquid/Debt funds from showing NAV regression
                cat = str(row.get("Category", "")).upper()
                if "LIQUID" in cat or "DEBT" in cat or "GILT" in cat:
                    if new_nav < cas_nav:
                        new_nav = cas_nav
                
                row["NAV"] = new_nav
                
                # V11-3 FIX: Always use the AMFI-provided date (the trading date).
                # Never fallback to datetime.now() which shows tomorrow's date.
                raw_date = date_map.get(isin, "")
                if raw_date:
                    try:
                        dt = pd.to_datetime(raw_date, format="%d-%b-%Y")
                        row["NAV Date"] = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass  # Keep existing NAV Date if AMFI date fails to parse
                    
                row["Market Value"] = round(units * new_nav, 2)
                row["Gain"] = round(row["Market Value"] - invested, 2)
                if invested > 0:
                    row["Gain%"] = round((row["Gain"] / invested) * 100, 2)
                    
            # ── Permanently Embed TER for Expense Drag Calculations ──
            if "TER" not in row or pd.isna(row.get("TER")):
                from shared.services.market_data import resolve_scheme_code_from_isin, fetch_fund_ter
                code = resolve_scheme_code_from_isin(isin) if isin else None
                ter = fetch_fund_ter(code, row.get("Plan", "Direct")) if code else None
                if ter is not None and ter > 0:
                    row["TER"] = round(ter, 2)
                else:
                    from shared.services.fallbacks.deterministic import DeterministicFallback
                    fb = DeterministicFallback().generate_fallbacks(
                        isin=isin or "", 
                        category=row.get("Category", ""), 
                        fund_name=row.get("Fund", ""), 
                        current_result={}
                    )
                    row["TER"] = fb.get("expense_ratio", 0.0)
                        
            return row

        self.df_h = self.df_h.apply(update_row, axis=1)
        if "Market Value" in self.df_h.columns:
            total_mv = float(self.df_h["Market Value"].sum())
            self.total_value = round(total_mv, 2)
            if total_mv > 0:
                self.df_h["Weight%"] = (self.df_h["Market Value"] / total_mv * 100).round(2)

    def get_summary(self, benchmark: str = "Nifty 500") -> Dict[str, Any]:
        """
        Generate high-level portfolio KPIs (XIRR, Alpha, Total Gain).
        
        Note on is_absolute:
        The backend calculates whether the entire portfolio's lifespan is under 1 year.
        If true, `is_absolute` is passed as True, allowing the frontend Overview tab
        to dynamically switch its primary Hero metric from 'Annualized XIRR' to 
        'Absolute Return', remaining fully compliant with institutional SEBI standards.
        """
        if self.df_h.empty: return {}
        
        ticker = BENCHMARKS.get(benchmark, benchmark)
        bench_data = fetch_benchmark_series(ticker, 9999)

        portfolio_xirr = compute_xirr(self.df_t, self.total_value)
        bench_xirr, _  = compute_benchmark_xirr(self.df_t, bench_data)
        is_abs = is_absolute_return(self.df_t)

        gain_pct = (self.total_value / self.total_invested - 1) * 100 if self.total_invested > 0 else 0

        total_expense = self.compute_expense_drag()

        nav_date = ""
        if "NAV Date" in self.df_h.columns and not self.df_h["NAV Date"].dropna().empty:
            nav_date = str(self.df_h["NAV Date"].dropna().max())
            try:
                # Convert YYYY-MM-DD to DD MMM YYYY for UI
                dt = pd.to_datetime(nav_date)
                nav_date = dt.strftime("%d %b, %Y")
            except:
                pass

        return {
            "total_value":     round(self.total_value, 2),
            "total_invested":  round(self.total_invested, 2),
            "total_gain":      round(self.total_value - self.total_invested, 2),
            "gain_pct":        round(gain_pct, 2),
            "portfolio_xirr":  round(portfolio_xirr, 2),
            "bench_xirr":      round(bench_xirr, 2),
            "alpha":           round(portfolio_xirr - bench_xirr, 2),
            "expense_drag":    round(total_expense, 2),
            "num_funds":       len(self.df_h),
            "is_absolute":     is_abs,
            "is_partial":      self.is_partial,
            "nav_date":        nav_date
        }

    def compute_expense_drag(self) -> float:
        """
        Annual rupee cost of holding the portfolio, from each fund's TER.

        Single source of truth: /insights previously carried a byte-identical copy of
        this loop AND called get_summary() (which runs it too), so the same figure was
        computed twice per request and could drift if only one copy were edited.
        """
        if self.df_h.empty:
            return 0.0

        total_expense = 0.0
        for _, row in self.df_h.iterrows():
            val = row.get("Market Value", 0)
            ter = row.get("TER", 0.0)

            if pd.isna(ter) or ter == 0:
                cat = row.get("Category", "Equity")
                lo, hi = EXP_RATIO_BANDS.get(cat, (0.50, 1.00))
                ter = lo if "direct" in str(row.get("Plan", "")).lower() else lo + 0.80

            total_expense += val * (ter / 100.0)

        return total_expense

    def get_allocation_data(self) -> Dict[str, Any]:
        if self.df_h.empty: return {}
        
        df = self.df_h.copy()
        df["BroadClass"] = df["Category"].apply(get_standard_category)
        
        broad_data = []
        classes = [
            ("Equity", "#6366F1"), 
            ("Debt", "#10B981"), 
            ("Hybrid", "#F59E0B"), 
            ("Global", "#8B5CF6"), 
            ("Other", "#94A3B8")
        ]
        for cls, color in classes:
            val = float(df[df["BroadClass"] == cls]["Market Value"].sum())
            broad_data.append({
                "label": cls, "value": round(val, 2), 
                "pct": round(val / self.total_value * 100, 1) if self.total_value > 0 else 0,
                "color": color
            })
        broad_data = sorted(broad_data, key=lambda x: x["pct"], reverse=True)

        # Cap breakdown
        df_c = df.copy()
        df_c["Cap Type"] = df_c["Cap Type"].replace("N/A", "Fixed Income / Other")
        cap_grp = df_c.groupby("Cap Type")["Market Value"].sum().reset_index()
        cap_grp["pct"] = (cap_grp["Market Value"] / self.total_value * 100).round(1) if self.total_value > 0 else 0
        cap_grp = cap_grp.sort_values(by="pct", ascending=False)
        cap_grp = cap_grp.rename(columns={"Cap Type": "label", "Market Value": "value"})

        return {
            "broad":       broad_data,
            "by_cap":      cap_grp.to_dict(orient="records"),
            "by_category": df.groupby("Category")["Market Value"].sum().reset_index().rename(
                columns={"Category": "label", "Market Value": "value"}
            ).to_dict(orient="records")
        }
