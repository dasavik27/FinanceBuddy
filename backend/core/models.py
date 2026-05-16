"""
core/models.py
Domain models for the PortfolioIQ engine.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from core.finance import compute_xirr, compute_benchmark_xirr, compute_period_comparison
from services.market_indices import fetch_benchmark_series
from core.config import BENCHMARKS, PERIOD_MAP, get_standard_category, EXP_RATIO_BANDS, TAX_RATES

class Portfolio:
    def __init__(self, df_h: pd.DataFrame, df_t: pd.DataFrame, df_s: pd.DataFrame, is_partial: bool = False):
        self.df_h = df_h
        self.df_t = df_t
        self.df_s = df_s
        self.is_partial = is_partial
        self.total_value = float(df_h["Market Value"].sum()) if not df_h.empty else 0.0
        self.total_invested = float(df_h["Invested"].sum()) if not df_h.empty else 0.0

    def update_live_navs(self):
        """Re-fetch live NAVs from AMFI and update all holdings in memory."""
        if self.df_h.empty:
            return
        from services.market_data import fetch_live_navs
        live_map = fetch_live_navs(refresh=True)
        if not live_map:
            return
            
        def update_row(row):
            isin = row.get("ISIN")
            units = float(row.get("Units", 0) or 0)
            invested = float(row.get("Invested", 0) or 0)
            if isin and isin in live_map:
                new_nav = float(live_map[isin])
                row["NAV"] = new_nav
                row["Market Value"] = round(units * new_nav, 2)
                row["Gain"] = round(row["Market Value"] - invested, 2)
                if invested > 0:
                    row["Gain%"] = round((row["Gain"] / invested) * 100, 2)
            return row

        self.df_h = self.df_h.apply(update_row, axis=1)
        if "Market Value" in self.df_h.columns:
            total_mv = float(self.df_h["Market Value"].sum())
            self.total_value = round(total_mv, 2)
            if total_mv > 0:
                self.df_h["Weight%"] = (self.df_h["Market Value"] / total_mv * 100).round(2)

    def get_summary(self, benchmark: str = "Nifty 50") -> Dict[str, Any]:
        if self.df_h.empty: return {}
        
        ticker = BENCHMARKS.get(benchmark, benchmark)
        bench_data = fetch_benchmark_series(ticker, 9999)

        portfolio_xirr = compute_xirr(self.df_t, self.total_value)
        bench_xirr, _  = compute_benchmark_xirr(self.df_t, bench_data)

        gain_pct = (self.total_value / self.total_invested - 1) * 100 if self.total_invested > 0 else 0
        
        # Expense drag estimation
        total_expense = 0.0
        for _, row in self.df_h.iterrows():
            cat = row["Category"]
            val = row["Market Value"]
            lo, hi = EXP_RATIO_BANDS.get(cat, (0.50, 1.00))
            # Use midpoint for Regular (more accurate than using 'hi' ceiling)
            est_er = lo if "direct" in str(row["Plan"]).lower() else (lo + hi) / 2
            total_expense += val * (est_er / 100.0)

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
            "is_partial":      self.is_partial
        }

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

        return {
            "broad":       broad_data,
            "by_cap":      cap_grp.to_dict(orient="records"),
            "by_category": df.groupby("Category")["Market Value"].sum().reset_index().to_dict(orient="records")
        }

    def get_tax_profile(self) -> Dict[str, Any]:
        """Aggregate FIFO-based tax estimates across all holdings."""
        from core.finance import compute_fifo_tax
        from datetime import datetime

        total_stcg = 0.0
        total_ltcg = 0.0
        total_stcg_tax = 0.0
        total_ltcg_tax = 0.0

        for _, row in self.df_h.iterrows():
            fund = row.get("Fund", "")
            units = float(row.get("Units", 0) or 0)
            nav = float(row.get("NAV", 0) or 0)
            category = row.get("Category", "Equity")

            if units <= 0 or nav <= 0:
                continue

            # Filter transactions for this fund
            fund_txs = self.df_t[self.df_t["Fund"] == fund] if "Fund" in self.df_t.columns else pd.DataFrame()

            result = compute_fifo_tax(fund_txs, units, nav, category)
            total_stcg += result.get("stcg_gain", 0)
            total_ltcg += result.get("ltcg_gain", 0)
            total_stcg_tax += result.get("stcg_tax", 0)
            total_ltcg_tax += result.get("ltcg_tax", 0)

        return {
            "stcg_gain": round(total_stcg, 2),
            "ltcg_gain": round(total_ltcg, 2),
            "stcg_tax": round(total_stcg_tax, 2),
            "ltcg_tax": round(total_ltcg_tax, 2),
            "total_tax": round(total_stcg_tax + total_ltcg_tax, 2),
        }
