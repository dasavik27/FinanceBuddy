"""
domains/equity/sessions.py

In-memory session store for equity portfolios.
Mirrors the MF sessions pattern: encrypt/compress payload to Postgres
and keep a bounded LRU in-process cache for hot reads.
"""

import logging
import threading
from collections import OrderedDict
from typing import Any

import pandas as pd

from domains.equity.models import EquityPortfolio
from shared import identity, storage

logger = logging.getLogger(__name__)

# Bounded LRU cache — same reasoning as MF sessions
_CACHE_SIZE = 20
_cache: OrderedDict[str, EquityPortfolio] = OrderedDict()
_lock = threading.Lock()


def _put(session_id: str, portfolio: EquityPortfolio) -> None:
    with _lock:
        _cache[session_id] = portfolio
        _cache.move_to_end(session_id)
        if len(_cache) > _CACHE_SIZE:
            evicted = next(iter(_cache))
            _cache.pop(evicted)
            logger.debug("[equity/sessions] evicted %s from LRU", evicted)


def _get(session_id: str) -> EquityPortfolio | None:
    with _lock:
        if session_id in _cache:
            _cache.move_to_end(session_id)
            return _cache[session_id]
    return None


def forget(session_id: str) -> None:
    """Evict a session from memory (called on delete)."""
    with _lock:
        _cache.pop(session_id, None)


def create_session(
    df_holdings: pd.DataFrame,
    df_trades: pd.DataFrame,
    source: str = "csv",
    kite_access_token: str | None = None,
    upload_type: str = "equity",
) -> str:
    """
    Persist an equity portfolio to Postgres and cache it in-process.
    Returns the session_id.
    """
    import uuid
    from shared import crypto

    portfolio = EquityPortfolio(
        df_holdings, df_trades, source=source, kite_access_token=kite_access_token
    )
    # Update prices right after creation
    portfolio.update_live_prices()

    # Adapt equity holdings columns to the storage layer's expected schema.
    # The storage layer uses "Market Value" and "Invested" for metrics extraction;
    # we rename our columns for persistence only, keeping portfolio.df_holdings untouched.
    df_h_store = portfolio.df_holdings.copy()
    if "current_value" in df_h_store.columns:
        df_h_store["Market Value"] = df_h_store["current_value"]
    if "invested" in df_h_store.columns:
        df_h_store["Invested"] = df_h_store["invested"]

    session_id = str(uuid.uuid4())
    user_id = identity.current_user_id()

    storage.save_session(
        session_id=session_id,
        df_h=df_h_store,
        df_t=df_trades if df_trades is not None else pd.DataFrame(),
        df_s=pd.DataFrame(),
        is_partial=False,
        statement_period=f"equity:{source}",
        user_id=user_id,
        upload_type=upload_type,
    )
    _put(session_id, portfolio)
    return session_id


def get_session(session_id: str) -> EquityPortfolio:
    """
    Return the EquityPortfolio for the given session.
    Falls back to Postgres if not in the in-process cache.
    Raises 404-style ValueError if not found or not owned by current user.
    """
    cached = _get(session_id)
    if cached is not None:
        return cached

    # Rehydrate from Postgres
    data = storage.load_session(session_id)
    if not data:
        raise ValueError(f"Equity session {session_id!r} not found.")

    df_h, df_t, _df_s, meta = data
    source = meta.get("source", "csv") if isinstance(meta, dict) else "csv"
    portfolio = EquityPortfolio(df_h, df_t, source=source)
    portfolio.update_live_prices()
    _put(session_id, portfolio)
    return portfolio
