"""
domains/equity/kite_client.py

Zerodha Kite Connect API integration.

OAuth 2.0 Flow:
  1. Generate login URL → user logs in on Zerodha
  2. Zerodha redirects back with `request_token`
  3. Exchange request_token for access_token (valid for 1 trading day)
  4. Use access_token for all subsequent API calls

Kite Developer App: https://developers.kite.trade
Free tier covers: holdings, positions, orders (no live tick-by-tick streaming)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class KiteClient:
    """
    Lightweight wrapper around kiteconnect.KiteConnect.

    Imported lazily inside methods so the module loads even if kiteconnect
    is not installed (keeps the app bootable without the package).
    """

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self._kite = None

    def _get_kite(self):
        if self._kite is None:
            try:
                from kiteconnect import KiteConnect
                self._kite = KiteConnect(api_key=self.api_key)
            except ImportError:
                raise RuntimeError(
                    "kiteconnect is not installed. Run: pip install kiteconnect"
                )
        return self._kite

    def get_login_url(self) -> str:
        """
        Return the Zerodha login URL to redirect the user to.
        After login, Zerodha redirects to the configured redirect_url
        with ?request_token=<token>&action=login&status=success
        """
        kite = self._get_kite()
        return kite.login_url()

    def exchange_token(self, request_token: str) -> dict[str, Any]:
        """
        Exchange the request_token (from Zerodha redirect) for an access_token.
        Returns a dict with access_token, public_token, user_id, etc.
        """
        kite = self._get_kite()
        try:
            session = kite.generate_session(request_token, api_secret=self.api_secret)
            kite.set_access_token(session["access_token"])
            return session
        except Exception as e:
            logger.error("[kite] token exchange failed: %s", e)
            raise ValueError(f"Zerodha authentication failed: {e}") from e

    def set_access_token(self, access_token: str) -> None:
        """Set a previously-obtained access token on this client."""
        kite = self._get_kite()
        kite.set_access_token(access_token)

    def fetch_holdings(self, access_token: str) -> list[dict]:
        """
        Fetch current equity holdings from Kite API.
        Returns list of dicts with: tradingsymbol, isin, quantity, average_price,
        last_price, pnl, day_change, day_change_percentage, t1_quantity, etc.
        """
        kite = self._get_kite()
        kite.set_access_token(access_token)
        try:
            holdings = kite.holdings()
            logger.info("[kite] fetched %d holdings", len(holdings))
            return holdings
        except Exception as e:
            logger.error("[kite] holdings fetch failed: %s", e)
            raise ValueError(f"Could not fetch holdings from Zerodha: {e}") from e

    def fetch_positions(self, access_token: str) -> dict[str, list]:
        """
        Fetch intraday and overnight positions.
        Returns {"net": [...], "day": [...]}
        """
        kite = self._get_kite()
        kite.set_access_token(access_token)
        try:
            return kite.positions()
        except Exception as e:
            logger.error("[kite] positions fetch failed: %s", e)
            raise ValueError(f"Could not fetch positions from Zerodha: {e}") from e

    def fetch_profile(self, access_token: str) -> dict:
        """Fetch user profile (name, email, user_id, broker)."""
        kite = self._get_kite()
        kite.set_access_token(access_token)
        try:
            return kite.profile()
        except Exception as e:
            logger.warning("[kite] profile fetch failed: %s", e)
            return {}


def holdings_to_dataframe(kite_holdings: list[dict]):
    """
    Convert Kite holdings API response to the normalized equity DataFrame
    that EquityPortfolio expects.
    """
    import pandas as pd

    if not kite_holdings:
        return pd.DataFrame()

    rows = []
    for h in kite_holdings:
        qty = float(h.get("quantity", 0) or 0) + float(h.get("t1_quantity", 0) or 0)
        if qty <= 0:
            continue
        rows.append({
            "symbol": str(h.get("tradingsymbol", "")).upper().strip(),
            "isin": h.get("isin", ""),
            "name": h.get("tradingsymbol", ""),
            "exchange": h.get("exchange", "NSE"),
            "quantity": qty,
            "avg_price": float(h.get("average_price", 0) or 0),
            "ltp": float(h.get("last_price", 0) or 0),
            "current_value": float(h.get("last_price", 0) or 0) * qty,
            "invested": float(h.get("average_price", 0) or 0) * qty,
            "unrealized_pnl": float(h.get("pnl", 0) or 0),
            "pnl_pct": 0.0,  # computed below
            "day_change": float(h.get("day_change", 0) or 0),
            "day_change_pct": float(h.get("day_change_percentage", 0) or 0),
            "broker": "zerodha_kite",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        invested = df["invested"].replace(0, float("nan"))
        df["pnl_pct"] = (df["unrealized_pnl"] / invested * 100).round(2)
    return df
