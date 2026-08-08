"""Strategy registry and universe scan runner."""

from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

from domains.equity.research_engine import ohlc as ohlc_mod
from domains.equity.research_engine import vcp as vcp_mod
from domains.equity.research_engine.universe import resolve_universe

logger = logging.getLogger(__name__)

# Sync scan hard cap — free-tier worker cannot pull hundreds of Yahoo series inline.
_DEFAULT_SCAN_LIMIT = 50
_HARD_SCAN_LIMIT = 80

StrategyFn = Callable[[pd.DataFrame], dict[str, Any]]

_STRATEGIES: dict[str, dict[str, Any]] = {
    vcp_mod.STRATEGY_ID: {
        **vcp_mod.STRATEGY_META,
        "evaluate": vcp_mod.evaluate,
    },
}


def list_strategies() -> list[dict[str, str]]:
    return [
        {"id": meta["id"], "name": meta["name"], "description": meta["description"]}
        for meta in _STRATEGIES.values()
    ]


def _rs_percentiles(frames: dict[str, pd.DataFrame]) -> dict[str, float]:
    rets: dict[str, float] = {}
    for sym, df in frames.items():
        r = vcp_mod.ret_52w(df)
        if r is not None:
            rets[sym] = r
    if not rets:
        return {}
    ordered = sorted(rets.items(), key=lambda kv: kv[1])
    n = len(ordered)
    out: dict[str, float] = {}
    for i, (sym, _) in enumerate(ordered):
        out[sym] = round(100.0 * i / max(n - 1, 1), 1)
    return out


def evaluate_symbol(symbol: str, strategy_id: str = vcp_mod.STRATEGY_ID) -> dict[str, Any]:
    meta = _STRATEGIES.get(strategy_id)
    if meta is None:
        return {"ok": False, "reason": f"unknown strategy: {strategy_id}", "symbol": symbol}

    df = ohlc_mod.fetch_ohlcv(symbol)
    if df is None:
        return {
            "ok": False,
            "reason": "no OHLCV data",
            "symbol": str(symbol).upper().strip(),
            "strategy": strategy_id,
        }

    result = meta["evaluate"](df, rs_percentile=None)
    result["symbol"] = str(symbol).upper().strip().replace("-EQ", "")
    return result


def run_scan(
    *,
    strategy_id: str = vcp_mod.STRATEGY_ID,
    universe: str = "nifty50",
    symbols: list[str] | None = None,
    limit: int = _DEFAULT_SCAN_LIMIT,
    only_setups: bool = False,
) -> dict[str, Any]:
    meta = _STRATEGIES.get(strategy_id)
    if meta is None:
        return {"ok": False, "reason": f"unknown strategy: {strategy_id}", "results": []}

    limit = max(1, min(int(limit or _DEFAULT_SCAN_LIMIT), _HARD_SCAN_LIMIT))
    univ = resolve_universe(universe, symbols)[:limit]

    frames: dict[str, pd.DataFrame] = {}
    skipped: list[dict[str, str]] = []
    for sym in univ:
        df = ohlc_mod.fetch_ohlcv(sym)
        if df is None or len(df) < 200:
            skipped.append({"symbol": sym, "reason": "insufficient OHLCV"})
            continue
        frames[sym] = df

    rs_map = _rs_percentiles(frames)
    results: list[dict[str, Any]] = []
    for sym, df in frames.items():
        row = meta["evaluate"](df, rs_percentile=rs_map.get(sym))
        row["symbol"] = sym
        if only_setups and not (row.get("stage2") and row.get("vcp_valid")):
            continue
        # Compact row for table; keep detail nested
        results.append(row)

    results.sort(key=lambda r: float(r.get("score") or 0), reverse=True)

    return {
        "ok": True,
        "strategy": strategy_id,
        "universe": universe if not symbols else "custom",
        "requested": len(univ),
        "evaluated": len(frames),
        "skipped": skipped,
        "results": results,
        "setups": sum(1 for r in results if r.get("stage2") and r.get("vcp_valid")),
    }
