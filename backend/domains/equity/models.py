"""
domains/equity/models.py

EquityPortfolio — the in-memory analytics model for a user's stock holdings.

Mirrors the MF Portfolio class in domains/mutual_funds/models.py but is
purpose-built for direct equity:
  - Holdings are individual stocks, not fund units
  - P&L is unrealized (mark-to-market) and realized (tradebook)
  - Sector allocation uses the NSE sector map
  - Live prices come from yfinance (SYMBOL.NS suffix)
  - XIRR is computed from tradebook if available
"""

import logging
from typing import Any

import pandas as pd
import numpy as np

from domains.equity.sector_map import get_sector, get_all_sectors

logger = logging.getLogger(__name__)


def _to_ns_ticker(symbol: str) -> str:
    """Convert NSE symbol to Yahoo Finance ticker format."""
    s = symbol.upper().strip().replace("-EQ", "")
    if not s.endswith(".NS") and not s.endswith(".BO"):
        return s + ".NS"
    return s


class EquityPortfolio:
    """
    In-memory analytics model for a direct equity portfolio.

    df_holdings columns (standardized by parser/kite_client):
      symbol, isin, name, exchange, quantity, avg_price, ltp, current_value,
      invested, unrealized_pnl, pnl_pct, day_change, day_change_pct, broker

    df_trades columns (from tradebook, optional):
      date, symbol, type (BUY/SELL), quantity, price, amount
    """

    def __init__(
        self,
        df_holdings: pd.DataFrame,
        df_trades: pd.DataFrame | None = None,
        source: str = "csv",
        kite_access_token: str | None = None,
    ):
        self.df_holdings = df_holdings.copy() if not df_holdings.empty else pd.DataFrame()
        self.df_trades = df_trades.copy() if df_trades is not None and not df_trades.empty else pd.DataFrame()
        self.source = source
        self.kite_access_token = kite_access_token

        self._enrich_sectors()
        self._compute_totals()

    def _enrich_sectors(self) -> None:
        """Add sector and industry columns using the NSE sector map."""
        if self.df_holdings.empty:
            return
        sectors, industries = [], []
        for sym in self.df_holdings["symbol"]:
            sec, ind = get_sector(str(sym))
            sectors.append(sec)
            industries.append(ind)
        self.df_holdings["sector"] = sectors
        self.df_holdings["industry"] = industries

    def _compute_totals(self) -> None:
        if self.df_holdings.empty:
            self.total_value = 0.0
            self.total_invested = 0.0
            return
        self.total_value = float(self.df_holdings["current_value"].sum())
        self.total_invested = float(self.df_holdings["invested"].sum())

    def update_live_prices(self) -> None:
        """
        Fetch latest LTP from Yahoo Finance for all held stocks.
        Skips stocks where yfinance returns no data.
        """
        if self.df_holdings.empty:
            return
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("[equity] yfinance not installed — skipping live price update")
            return

        symbols = self.df_holdings["symbol"].tolist()
        tickers = [_to_ns_ticker(s) for s in symbols]
        sym_to_ticker = dict(zip(symbols, tickers))

        try:
            data = yf.download(
                tickers, period="2d", interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=True,
            )
        except Exception as e:
            logger.warning("[equity] yfinance download failed: %s", e)
            return

        for sym, ticker in sym_to_ticker.items():
            try:
                if len(tickers) == 1:
                    close_col = data.get("Close")
                else:
                    close_col = data.get((ticker, "Close")) or data.get(ticker, {}).get("Close")

                if close_col is None or close_col.dropna().empty:
                    continue
                price = float(close_col.dropna().iloc[-1])

                mask = self.df_holdings["symbol"] == sym
                self.df_holdings.loc[mask, "ltp"] = price
                qty = self.df_holdings.loc[mask, "quantity"].values[0]
                invested = self.df_holdings.loc[mask, "invested"].values[0]
                current_val = price * qty
                pnl = current_val - invested
                self.df_holdings.loc[mask, "current_value"] = round(current_val, 2)
                self.df_holdings.loc[mask, "unrealized_pnl"] = round(pnl, 2)
                self.df_holdings.loc[mask, "pnl_pct"] = round(pnl / invested * 100, 2) if invested else 0.0

            except Exception as e:
                logger.debug("[equity] price update skipped for %s: %s", sym, e)

        self._compute_totals()
        if self.total_value > 0:
            self.df_holdings["weight_pct"] = (
                self.df_holdings["current_value"] / self.total_value * 100
            ).round(2)

    def get_summary(self) -> dict[str, Any]:
        """High-level KPI metrics for the Overview tab."""
        if self.df_holdings.empty:
            return {}

        unrealized_pnl = self.total_value - self.total_invested
        pnl_pct = (unrealized_pnl / self.total_invested * 100) if self.total_invested > 0 else 0.0

        day_change = 0.0
        if "day_change" in self.df_holdings.columns:
            day_change = float(self.df_holdings["day_change"].fillna(0).sum())

        return {
            "total_value": round(self.total_value, 2),
            "total_invested": round(self.total_invested, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "day_change": round(day_change, 2),
            "num_stocks": len(self.df_holdings),
            "source": self.source,
            "has_trades": not self.df_trades.empty,
        }

    def get_holdings(self, sort_by: str = "current_value", ascending: bool = False) -> list[dict]:
        """Per-stock holdings table for the Holdings tab."""
        if self.df_holdings.empty:
            return []
        df = self.df_holdings.copy()
        if sort_by in df.columns:
            df = df.sort_values(sort_by, ascending=ascending)
        return df.fillna(0).to_dict(orient="records")

    def get_sector_allocation(self) -> dict[str, Any]:
        """Sector breakdown for the Sector Allocation tab."""
        if self.df_holdings.empty:
            return {"by_sector": [], "by_industry": []}

        df = self.df_holdings.copy()

        # By sector
        sector_grp = (
            df.groupby("sector")["current_value"]
            .sum()
            .reset_index()
            .rename(columns={"sector": "label", "current_value": "value"})
        )
        total = self.total_value or 1
        sector_grp["pct"] = (sector_grp["value"] / total * 100).round(2)
        sector_grp["value"] = sector_grp["value"].round(2)
        sector_grp = sector_grp.sort_values("pct", ascending=False)

        # By industry
        industry_grp = (
            df.groupby(["sector", "industry"])["current_value"]
            .sum()
            .reset_index()
            .rename(columns={"current_value": "value"})
        )
        industry_grp["pct"] = (industry_grp["value"] / total * 100).round(2)
        industry_grp["value"] = industry_grp["value"].round(2)
        industry_grp = industry_grp.sort_values("pct", ascending=False)

        return {
            "by_sector": sector_grp.to_dict(orient="records"),
            "by_industry": industry_grp.to_dict(orient="records"),
        }

    def get_pnl_analysis(self) -> dict[str, Any]:
        """P&L analysis and STCG/LTCG tax estimates."""
        if self.df_holdings.empty:
            return {}

        df = self.df_holdings.copy()
        unrealized = float(df["unrealized_pnl"].fillna(0).sum())
        gainers = df[df["unrealized_pnl"] > 0]
        losers = df[df["unrealized_pnl"] < 0]

        # Rough LTCG estimate: gains on stocks held > 1 year
        # Without a tradebook, we can only estimate from upload date
        # With tradebook, we compute exact holding periods
        stcg_estimate = 0.0
        ltcg_estimate = 0.0
        stcg_tax = 0.0
        ltcg_tax = 0.0

        if not self.df_trades.empty:
            stcg_estimate, ltcg_estimate = self._compute_capital_gains()
            stcg_tax = round(stcg_estimate * 0.20, 2)   # 20% STCG (Budget 2024)
            ltcg_tax = round(max(0, ltcg_estimate - 125000) * 0.125, 2)  # 12.5% LTCG above ₹1.25L

        return {
            "unrealized_pnl": round(unrealized, 2),
            "total_gainers": len(gainers),
            "total_losers": len(losers),
            "gainers_value": round(float(gainers["unrealized_pnl"].sum()), 2),
            "losers_value": round(float(losers["unrealized_pnl"].sum()), 2),
            "stcg_estimate": round(stcg_estimate, 2),
            "ltcg_estimate": round(ltcg_estimate, 2),
            "stcg_tax_estimate": stcg_tax,
            "ltcg_tax_estimate": ltcg_tax,
            "has_tradebook": not self.df_trades.empty,
            "top_gainers": gainers.nlargest(5, "unrealized_pnl")[["symbol", "unrealized_pnl", "pnl_pct"]].fillna(0).to_dict(orient="records"),
            "top_losers": losers.nsmallest(5, "unrealized_pnl")[["symbol", "unrealized_pnl", "pnl_pct"]].fillna(0).to_dict(orient="records"),
        }

    def _compute_capital_gains(self) -> tuple[float, float]:
        """
        Compute STCG and LTCG from the tradebook using FIFO lot matching.
        Returns (stcg, ltcg) in rupees.
        """
        if self.df_trades.empty:
            return 0.0, 0.0

        df = self.df_trades.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")

        stcg = 0.0
        ltcg = 0.0

        for sym, group in df.groupby("symbol"):
            buy_lots: list[tuple] = []  # (date, qty, price)
            for _, row in group.iterrows():
                tx_type = str(row.get("type", "")).upper()
                qty = float(row.get("quantity", 0) or 0)
                price = float(row.get("price", 0) or 0)
                tx_date = row["date"]

                if "BUY" in tx_type:
                    buy_lots.append((tx_date, qty, price))
                elif "SELL" in tx_type and buy_lots:
                    remaining_sell = qty
                    while remaining_sell > 0 and buy_lots:
                        buy_date, buy_qty, buy_price = buy_lots[0]
                        matched = min(remaining_sell, buy_qty)
                        gain = matched * (price - buy_price)
                        days_held = (tx_date - buy_date).days
                        if days_held > 365:
                            ltcg += gain
                        else:
                            stcg += gain
                        remaining_sell -= matched
                        if matched >= buy_qty:
                            buy_lots.pop(0)
                        else:
                            buy_lots[0] = (buy_date, buy_qty - matched, buy_price)

        return round(stcg, 2), round(ltcg, 2)

    def get_insights(self) -> dict[str, Any]:
        """Smart nudges: top movers, concentrated positions, tax-loss harvest opportunities."""
        if self.df_holdings.empty:
            return {}

        df = self.df_holdings.copy()
        total = self.total_value or 1

        top_gainers = df.nlargest(5, "pnl_pct")[["symbol", "pnl_pct", "unrealized_pnl"]].fillna(0).to_dict(orient="records")
        top_losers = df.nsmallest(5, "pnl_pct")[["symbol", "pnl_pct", "unrealized_pnl"]].fillna(0).to_dict(orient="records")

        # Concentration risk: positions > 10% of portfolio
        df["weight_pct"] = df["current_value"] / total * 100
        concentrated = df[df["weight_pct"] > 10][["symbol", "weight_pct", "sector"]].to_dict(orient="records")

        # Tax-loss harvest candidates: unrealized losses
        harvestable = df[df["unrealized_pnl"] < -5000][["symbol", "unrealized_pnl", "pnl_pct"]].nsmallest(5, "unrealized_pnl").to_dict(orient="records")

        return {
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "concentrated_positions": concentrated,
            "tax_loss_harvest": harvestable,
            "diversification_score": self._diversification_score(),
        }

    def _diversification_score(self) -> int:
        """
        Simple diversification score 0-100.
        Penalizes for: few stocks, few sectors, large single positions.
        """
        if self.df_holdings.empty:
            return 0
        n_stocks = len(self.df_holdings)
        n_sectors = self.df_holdings["sector"].nunique() if "sector" in self.df_holdings.columns else 1
        max_weight = float(self.df_holdings["current_value"].max() / (self.total_value or 1) * 100)

        score = 100
        if n_stocks < 5:
            score -= 30
        elif n_stocks < 10:
            score -= 15
        if n_sectors < 3:
            score -= 25
        elif n_sectors < 5:
            score -= 10
        if max_weight > 40:
            score -= 25
        elif max_weight > 25:
            score -= 10

        return max(0, min(100, score))
