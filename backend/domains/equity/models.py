"""
domains/equity/models.py

EquityPortfolio — the in-memory analytics model for a user's stock holdings.

Mirrors the MF Portfolio class in domains/mutual_funds/models.py but is
purpose-built for direct equity:
  - Holdings are individual stocks, not fund units
  - P&L is unrealized (mark-to-market) and realized (tradebook)
  - Sector allocation uses the NSE sector map
  - Live prices come from domains/equity/quotes (cached, batched)

Not implemented, despite an earlier version of this docstring claiming it: XIRR. The
tradebook has the dated cashflows to compute one, and the mutual-fund side already has
the solver (domains/mutual_funds/finance.py), but nothing here calls it - so the only
return figure this module produces is absolute, which for a position built up over
several years is not the investor's return. Wiring it up is tracked separately rather
than asserted here.
"""

import logging
from collections import deque
from typing import Any

import pandas as pd
import numpy as np

from domains.equity import derived
from domains.equity.sector_map import (
    DEFAULT_INDUSTRY,
    DEFAULT_SECTOR,
    SECTOR_MAP,
    get_all_sectors,
    get_sector,
)
from domains.equity.quotes import fetch_quotes, to_yahoo_ticker

logger = logging.getLogger(__name__)

# Long-term capital gains on listed equity begin after 12 months of holding.
_LTCG_HOLDING_DAYS = 365

# Post-Budget-2024 rates for listed equity with STT paid.
_STCG_RATE = 0.20
_LTCG_RATE = 0.125

# Section 112A exemption, applied per financial year and to LTCG only.
_LTCG_ANNUAL_EXEMPTION = 125_000.0


def _to_ns_ticker(symbol: str) -> str:
    """Convert NSE symbol to Yahoo Finance ticker format."""
    return to_yahoo_ticker(symbol)


def _stcg_tax(stcg: float) -> float:
    """
    Tax on short-term capital gains for one financial year.

    Floored at zero. This used to be a bare `stcg * 0.20`, so a net short-term *loss*
    of Rs 50,000 rendered a tax estimate of -10,000 - a negative liability presented as
    if the government owed the user money. A realised loss carries forward against
    future gains; it is not a refund, and modelling set-off is out of scope for an
    estimate, so the floor is the honest answer.
    """
    return round(max(0.0, stcg) * _STCG_RATE, 2)


def _ltcg_tax(ltcg: float) -> float:
    """Tax on long-term capital gains for one financial year, after the annual 112A
    exemption. The exemption applies per year, which is why gains are bucketed."""
    return round(max(0.0, ltcg - _LTCG_ANNUAL_EXEMPTION) * _LTCG_RATE, 2)


def _financial_year(ts: pd.Timestamp) -> str:
    """
    Indian financial year label for a date: 1 April to 31 March.

    Capital gains are assessed per financial year, so gains realised in different
    years must never be summed into one figure - see _compute_capital_gains.
    """
    year = ts.year
    if ts.month < 4:
        return f"{year - 1}-{str(year)[2:]}"
    return f"{year}-{str(year + 1)[2:]}"


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

        # Brokers report "day change" per share. Until update_live_prices() rescales it
        # by quantity, the column is not additive across positions, and get_summary()
        # must not sum it.
        self._day_change_is_positional = False

        self._enrich_sectors()
        # Not just totals: this also guarantees pnl_pct and weight_pct exist before any
        # tab reads them. get_insights() used to recompute weight_pct itself because it
        # could not rely on the column being there.
        self._recompute_valuation()

    def _enrich_sectors(self) -> None:
        """
        Add sector and industry columns using the NSE sector map.

        Vectorized via `map` rather than a Python loop appending to two lists. The map
        is keyed on the same normalisation get_sector() applies, so lookups agree.
        """
        if self.df_holdings.empty:
            return

        # Same normalisation as get_sector(): upper, strip, drop "-EQ", drop spaces.
        keys = (
            self.df_holdings["symbol"].astype(str)
            .str.upper().str.strip()
            .str.replace("-EQ", "", regex=False)
            .str.replace(" ", "", regex=False)
        )
        pairs = keys.map(SECTOR_MAP)
        self.df_holdings["sector"] = [
            p[0] if isinstance(p, tuple) else DEFAULT_SECTOR for p in pairs
        ]
        self.df_holdings["industry"] = [
            p[1] if isinstance(p, tuple) else DEFAULT_INDUSTRY for p in pairs
        ]

    def _compute_totals(self) -> None:
        """Portfolio totals. Tolerates a missing or non-numeric column rather than
        raising from inside a rehydration path."""
        if self.df_holdings.empty:
            self.total_value = 0.0
            self.total_invested = 0.0
            return

        def _sum(col: str) -> float:
            if col not in self.df_holdings.columns:
                return 0.0
            return float(pd.to_numeric(self.df_holdings[col], errors="coerce").sum())

        self.total_value = _sum("current_value")
        self.total_invested = _sum("invested")

    def update_live_prices(self) -> None:
        """
        Refresh LTP and the derived value columns from the quotes service.

        Vectorized. The previous implementation looped over symbols and, per symbol,
        built a boolean mask and performed six full-column `.loc` assignments - roughly
        6N passes over the frame for N holdings, so 300 full-column scans for 50 rows.
        It also read `quantity` and `invested` with `.values[0]`, which takes the
        *first* matching row and then writes that one row's value to every match: a
        stock held on both NSE and BSE, or listed twice by a broker export, silently
        got the wrong current value on every duplicate row.

        Symbols the provider does not return keep their existing price rather than
        being zeroed - an unknown price is missing data, not a value of nothing.
        """
        if self.df_holdings.empty:
            return

        df = self.df_holdings
        symbols = df["symbol"].astype(str)

        quotes = fetch_quotes(symbols.unique().tolist())
        if not quotes:
            logger.info("[equity] no live quotes resolved; keeping stored prices")
            self._recompute_valuation()
            return

        price_map = {sym: q.ltp for sym, q in quotes.items()}
        change_map = {sym: q.day_change_per_share for sym, q in quotes.items()}

        # One aligned Series per column, so every row is updated on its own quantity.
        new_ltp = symbols.map(price_map)
        matched = new_ltp.notna()
        if matched.any():
            df.loc[matched, "ltp"] = new_ltp[matched].astype(float)

        # Day change is a *per-share* move. Both the Zerodha CSV column and the Kite
        # API field are per share, and this used to be summed straight across
        # positions, producing a rupee figure that was not the portfolio's day change
        # or anything else. Scaled by quantity here so the sum in get_summary() is the
        # actual change in portfolio value.
        per_share = symbols.map(change_map)
        if per_share.notna().any():
            scaled = per_share.astype(float) * pd.to_numeric(df["quantity"], errors="coerce")
            df.loc[per_share.notna(), "day_change"] = scaled[per_share.notna()].round(2)
            # Rows we could not price keep a per-share figure, so the column is only
            # additive once every row has been converted.
            self._day_change_is_positional = bool(per_share.notna().all())

        self._recompute_valuation()
        logger.info(
            "[equity] priced %d/%d holding(s) from live quotes",
            int(matched.sum()), len(df),
        )

    def _recompute_valuation(self) -> None:
        """
        Rebuild current_value, unrealized_pnl, pnl_pct, weight_pct and the totals from
        ltp and quantity. Pure column arithmetic - no per-row work.
        """
        df = self.df_holdings
        if df.empty:
            self._compute_totals()
            return

        def _num(col: str) -> pd.Series:
            """
            Column as a numeric Series, or zeros when absent.

            `pd.to_numeric(df.get(col))` looks equivalent and is not: DataFrame.get
            returns None for a missing column, and to_numeric(None) yields a scalar
            numpy float, so the next `.notna()` raises AttributeError. Reachable when
            rehydrating a stored payload written before a column existed.
            """
            if col not in df.columns:
                return pd.Series(0.0, index=df.index, dtype="float64")
            return pd.to_numeric(df[col], errors="coerce")

        qty = _num("quantity").fillna(0.0)
        ltp = _num("ltp")
        invested = _num("invested").fillna(0.0)

        # Only revalue rows that have a price; the rest keep whatever the broker gave.
        priced = ltp.notna() & (ltp > 0)
        if priced.any():
            df.loc[priced, "current_value"] = (ltp[priced] * qty[priced]).round(2)
            df.loc[priced, "unrealized_pnl"] = (
                df.loc[priced, "current_value"] - invested[priced]
            ).round(2)

        # Guard the divisor rather than testing truthiness of a possibly-NaN scalar:
        # `if invested` was True for NaN, which propagated NaN into pnl_pct.
        safe_invested = invested.where(invested > 0)
        df["pnl_pct"] = (
            _num("unrealized_pnl") / safe_invested * 100
        ).round(2).fillna(0.0)

        self._compute_totals()
        if self.total_value > 0:
            df["weight_pct"] = (
                _num("current_value") / self.total_value * 100
            ).round(2).fillna(0.0)
        else:
            df["weight_pct"] = 0.0

    def get_summary(self) -> dict[str, Any]:
        """High-level KPI metrics for the Overview tab."""
        if self.df_holdings.empty:
            return {}

        unrealized_pnl = self.total_value - self.total_invested
        pnl_pct = (unrealized_pnl / self.total_invested * 100) if self.total_invested > 0 else 0.0

        # day_change is stored per position (per-share move x quantity) by
        # update_live_prices, so this sum is the portfolio's rupee move. When prices
        # could not be refreshed the column still holds the broker's per-share figure,
        # which is not summable - so fall back to reporting nothing rather than a
        # number that looks like rupees and is not.
        day_change = 0.0
        if self._day_change_is_positional and "day_change" in self.df_holdings.columns:
            day_change = float(
                pd.to_numeric(self.df_holdings["day_change"], errors="coerce").fillna(0).sum()
            )

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

    # Columns a client may sort the holdings table by. An unrecognised value used to be
    # silently ignored, which returned rows in arbitrary order while the UI showed a
    # sorted header - so the caller now learns it asked for something that does not
    # exist.
    SORTABLE_COLUMNS = (
        "symbol", "name", "sector", "industry", "quantity", "avg_price", "ltp",
        "current_value", "invested", "unrealized_pnl", "pnl_pct", "day_change",
        "day_change_pct", "weight_pct",
    )

    def get_holdings(self, sort_by: str = "current_value", ascending: bool = False) -> list[dict]:
        """
        Per-stock holdings table for the Holdings tab.

        `sort_values` copies, so there is no separate `.copy()` here - the previous
        version held the original, a sorted copy and a fillna copy simultaneously, three
        full-size representations for one response.
        """
        if self.df_holdings.empty:
            return []
        if sort_by not in self.df_holdings.columns:
            sort_by = "current_value"
        df = self.df_holdings.sort_values(sort_by, ascending=ascending)
        return df.fillna(0).to_dict(orient="records")

    def get_sector_allocation(self) -> dict[str, Any]:
        """
        Sector breakdown for the Sector Allocation tab.

        Memoized: the Overview tab and the Sector tab both call this from the same
        inputs on a single dashboard load, so the second groupby pair was pure waste.
        """
        if self.df_holdings.empty:
            return {"by_sector": [], "by_industry": []}
        return derived.sector_allocation(
            self.df_holdings, self.total_value, self._sector_allocation_uncached
        )

    def _sector_allocation_uncached(self) -> dict[str, Any]:
        df = self.df_holdings

        # By sector. observed=True is explicit because sector/industry are stored as
        # `category` after dtype compaction, and an unobserved-category groupby would
        # emit a zero row for every sector in the map the user does not hold.
        sector_grp = (
            df.groupby("sector", observed=True)["current_value"]
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
            df.groupby(["sector", "industry"], observed=True)["current_value"]
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

        df = self.df_holdings
        unrealized = float(pd.to_numeric(df["unrealized_pnl"], errors="coerce").fillna(0).sum())
        gainers = df[df["unrealized_pnl"] > 0]
        losers = df[df["unrealized_pnl"] < 0]

        gains = self._compute_capital_gains()
        current_fy = gains["current_financial_year"]
        this_year = gains["by_financial_year"].get(current_fy, {"stcg": 0.0, "ltcg": 0.0})

        return {
            "unrealized_pnl": round(unrealized, 2),
            "total_gainers": len(gainers),
            "total_losers": len(losers),
            "gainers_value": round(float(gainers["unrealized_pnl"].sum()), 2),
            "losers_value": round(float(losers["unrealized_pnl"].sum()), 2),
            # Headline figures are the *current* financial year, because that is the
            # liability the user can still act on. These used to be the sum of every
            # year in the tradebook, with one year's exemption applied to the lot - so
            # a five-year tradebook reported five years of gains as this year's tax.
            "financial_year": current_fy,
            "stcg_estimate": round(this_year["stcg"], 2),
            "ltcg_estimate": round(this_year["ltcg"], 2),
            "stcg_tax_estimate": _stcg_tax(this_year["stcg"]),
            "ltcg_tax_estimate": _ltcg_tax(this_year["ltcg"]),
            "realised_by_year": gains["by_financial_year"],
            "lifetime_stcg": round(gains["lifetime_stcg"], 2),
            "lifetime_ltcg": round(gains["lifetime_ltcg"], 2),
            "unmatched_sell_qty": round(gains["unmatched_sell_qty"], 3),
            "has_tradebook": not self.df_trades.empty,
            "top_gainers": gainers.nlargest(5, "unrealized_pnl")[["symbol", "unrealized_pnl", "pnl_pct"]].fillna(0).to_dict(orient="records"),
            "top_losers": losers.nsmallest(5, "unrealized_pnl")[["symbol", "unrealized_pnl", "pnl_pct"]].fillna(0).to_dict(orient="records"),
        }

    def _compute_capital_gains(self) -> dict[str, Any]:
        """
        Realised capital gains, memoized on the tradebook's content hash.

        See domains/equity/derived.py for why the key excludes the holdings frame: gains
        are a function of executed trades, so a live-price refresh must not discard them.
        """
        return derived.capital_gains(self.df_trades, self._compute_capital_gains_uncached)

    def _compute_capital_gains_uncached(self) -> dict[str, Any]:
        """
        Realised capital gains from the tradebook, FIFO-matched and bucketed by the
        financial year of the *sale*.

        Bucketing is the point. Capital gains are assessed per financial year and the
        section 112A exemption is an annual allowance, so summing a multi-year
        tradebook into one STCG and one LTCG figure - which is what this used to do -
        both overstates the current year's liability and gives away the exemption once
        instead of once per year.

        `unmatched_sell_qty` reports quantity sold with no buy lot to match against.
        That happens legitimately when the tradebook does not reach back far enough to
        include the original purchase; previously such sells were silently skipped, so
        the gains were understated with no indication that anything was missing.
        """
        empty = {
            "by_financial_year": {},
            "lifetime_stcg": 0.0,
            "lifetime_ltcg": 0.0,
            "unmatched_sell_qty": 0.0,
            "current_financial_year": _financial_year(pd.Timestamp.now()),
        }
        if self.df_trades.empty:
            return empty

        df = self.df_trades.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        if df.empty:
            return empty

        # Sort once, globally, then group. A stable sort inside groupby preserves this
        # ordering per symbol, so FIFO sees trades chronologically.
        df = df.sort_values("date", kind="stable")

        by_year: dict[str, dict[str, float]] = {}
        unmatched_qty = 0.0

        for _sym, group in df.groupby("symbol", sort=False):
            # deque, not list: FIFO consumption used list.pop(0), which is O(n) per
            # pop and made a long tradebook quadratic in accumulated lots.
            buy_lots: deque[tuple[pd.Timestamp, float, float]] = deque()

            # itertuples, not iterrows: iterrows boxes every row into a new Series.
            for row in group.itertuples(index=False):
                tx_type = str(getattr(row, "type", "") or "").upper()
                qty = float(getattr(row, "quantity", 0) or 0)
                price = float(getattr(row, "price", 0) or 0)
                tx_date = row.date

                if qty <= 0:
                    continue

                if "BUY" in tx_type:
                    buy_lots.append((tx_date, qty, price))
                    continue
                if "SELL" not in tx_type:
                    continue

                fy = _financial_year(tx_date)
                bucket = by_year.setdefault(fy, {"stcg": 0.0, "ltcg": 0.0})

                remaining = qty
                while remaining > 0 and buy_lots:
                    buy_date, buy_qty, buy_price = buy_lots[0]
                    matched = min(remaining, buy_qty)
                    gain = matched * (price - buy_price)
                    if (tx_date - buy_date).days > _LTCG_HOLDING_DAYS:
                        bucket["ltcg"] += gain
                    else:
                        bucket["stcg"] += gain
                    remaining -= matched
                    if matched >= buy_qty:
                        buy_lots.popleft()
                    else:
                        buy_lots[0] = (buy_date, buy_qty - matched, buy_price)

                # Sold more than the tradebook accounts for. Surfaced, not swallowed.
                if remaining > 0:
                    unmatched_qty += remaining

        for bucket in by_year.values():
            bucket["stcg"] = round(bucket["stcg"], 2)
            bucket["ltcg"] = round(bucket["ltcg"], 2)

        if unmatched_qty > 0:
            logger.info(
                "[equity] %.3f units sold with no matching buy lot; the tradebook "
                "likely predates those purchases", unmatched_qty,
            )

        return {
            "by_financial_year": by_year,
            "lifetime_stcg": round(sum(b["stcg"] for b in by_year.values()), 2),
            "lifetime_ltcg": round(sum(b["ltcg"] for b in by_year.values()), 2),
            "unmatched_sell_qty": unmatched_qty,
            "current_financial_year": _financial_year(pd.Timestamp.now()),
        }

    def get_insights(self) -> dict[str, Any]:
        """Smart nudges: top movers, concentrated positions, tax-loss harvest opportunities."""
        if self.df_holdings.empty:
            return {}
        return derived.insights(
            self.df_holdings, self.total_value, self._insights_uncached
        )

    def _insights_uncached(self) -> dict[str, Any]:

        # No .copy(): every access below is a read or a projection, and copying the
        # whole frame per request was pure overhead.
        df = self.df_holdings

        top_gainers = df.nlargest(5, "pnl_pct")[["symbol", "pnl_pct", "unrealized_pnl"]].fillna(0).to_dict(orient="records")
        top_losers = df.nsmallest(5, "pnl_pct")[["symbol", "pnl_pct", "unrealized_pnl"]].fillna(0).to_dict(orient="records")

        # Concentration risk: positions > 10% of portfolio. weight_pct is maintained by
        # _recompute_valuation, so it no longer has to be derived (and written back to
        # a copy) here.
        concentrated = (
            df[df["weight_pct"] > 10][["symbol", "weight_pct", "sector"]]
            .sort_values("weight_pct", ascending=False)
            .to_dict(orient="records")
        )

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
