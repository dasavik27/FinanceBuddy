"""
Minervini Trend Template + VCP detection (MarketSmith-free).

Logic ported from akdas79/vcp-scanner scripts/marketsmith_india_vcp.py —
composite scoring uses RS percentile / trend / VCP quality instead of MS ratings.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from domains.equity.research_engine.pivots import argrelextrema

TT = {
    "ma200_slope_window": 20,
    "pct_above_52w_low": 30,
    "pct_below_52w_high": 25,
}

VCP = {
    "min_contractions": 2,
    "max_contractions": 4,
    "max_contraction_depth": 0.50,
    "min_contraction_depth": 0.05,
    "tightest_contraction": 0.12,
    "min_weeks": 3,
    "argrelextrema_order": 8,
    "vol_check_short_days": 5,
    "vol_check_long_days": 30,
}

STRATEGY_ID = "minervini_vcp"
STRATEGY_META = {
    "id": STRATEGY_ID,
    "name": "Minervini Trend Template + VCP",
    "description": (
        "Stage-2 Trend Template (8-point) plus Volatility Contraction Pattern "
        "detection with pivot and volume dry-up. No MarketSmith dependency."
    ),
}


def _s(val: Any) -> float:
    if hasattr(val, "item"):
        return float(val.item())
    return float(val)


def compute_mas(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MA50"] = out["Close"].rolling(50).mean()
    out["MA150"] = out["Close"].rolling(150).mean()
    out["MA200"] = out["Close"].rolling(200).mean()
    return out


def trend_template(df: pd.DataFrame) -> dict[str, Any]:
    """Minervini Stage-2 checklist. passes_template when >= 8 of 9 criteria hold."""
    df = compute_mas(df)
    latest = df.iloc[-1]

    close = _s(latest["Close"])
    ma50 = _s(latest["MA50"]) if not pd.isna(latest["MA50"]) else float("nan")
    ma150 = _s(latest["MA150"]) if not pd.isna(latest["MA150"]) else float("nan")
    ma200 = _s(latest["MA200"]) if not pd.isna(latest["MA200"]) else float("nan")

    high_52w = float(df["High"].tail(252).max())
    low_52w = float(df["Low"].tail(252).min())

    slope_window = TT["ma200_slope_window"]
    if len(df) >= 200 + slope_window:
        ma200_sloping = bool(df["MA200"].iloc[-1] > df["MA200"].iloc[-1 - slope_window])
    else:
        ma200_sloping = False

    criteria: dict[str, Any] = {
        "C1_price_above_ma200": bool(close > ma200) if not np.isnan(ma200) else False,
        "C2_price_above_ma150": bool(close > ma150) if not np.isnan(ma150) else False,
        "C3_ma150_above_ma200": bool(ma150 > ma200) if not (np.isnan(ma150) or np.isnan(ma200)) else False,
        "C4_ma200_sloping_up": ma200_sloping,
        "C5_ma50_above_ma150": bool(ma50 > ma150) if not (np.isnan(ma50) or np.isnan(ma150)) else False,
        "C6_ma50_above_ma200": bool(ma50 > ma200) if not (np.isnan(ma50) or np.isnan(ma200)) else False,
        "C7_price_above_ma50": bool(close > ma50) if not np.isnan(ma50) else False,
        "C8_above_52w_low_30pct": bool(close >= low_52w * (1 + TT["pct_above_52w_low"] / 100)),
        "C9_within_52w_high_25pct": bool(close >= high_52w * (1 - TT["pct_below_52w_high"] / 100)),
    }
    passed = sum(1 for k, v in criteria.items() if k.startswith("C") and v)
    criteria["passed_count"] = passed
    criteria["passes_template"] = passed >= 8
    criteria["trend_score"] = passed / 9.0
    criteria["close"] = round(close, 2)
    criteria["high_52w"] = round(high_52w, 2)
    criteria["low_52w"] = round(low_52w, 2)
    return criteria


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    prev = df["Close"].shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def measure_contractions(df: pd.DataFrame) -> dict[str, Any]:
    """VCP contraction measurement (Close pivots, H/L depth)."""
    close = df["Close"].values
    highs_arr = df["High"].values
    lows_arr = df["Low"].values
    n_bars = len(close)
    order = VCP["argrelextrema_order"]
    half = order // 2

    highs_idx = argrelextrema(close, np.greater_equal, order=order)
    lows_idx = argrelextrema(close, np.less_equal, order=order)

    if len(highs_idx) < 2 or len(lows_idx) < 1:
        return {"valid": False, "reason": "insufficient pivots"}

    all_pivots = (
        [(int(i), "H", float(close[i])) for i in highs_idx]
        + [(int(i), "L", float(close[i])) for i in lows_idx]
    )
    all_pivots.sort(key=lambda x: x[0])

    alternating: list = []
    for pivot in all_pivots:
        if alternating and alternating[-1][1] == pivot[1]:
            prev = alternating[-1]
            if pivot[1] == "H" and pivot[2] > prev[2]:
                alternating[-1] = pivot
            elif pivot[1] == "L" and pivot[2] < prev[2]:
                alternating[-1] = pivot
        else:
            alternating.append(pivot)

    contractions: list = []
    for i in range(len(alternating) - 1):
        curr, nxt = alternating[i], alternating[i + 1]
        if curr[1] != "H" or nxt[1] != "L":
            continue
        hi_idx, lo_idx = curr[0], nxt[0]
        h_start, h_end = max(0, hi_idx - half), min(n_bars - 1, hi_idx + half)
        l_start, l_end = max(0, lo_idx - half), min(n_bars - 1, lo_idx + half)
        pv_h = float(highs_arr[h_start : h_end + 1].max())
        pv_l = float(lows_arr[l_start : l_end + 1].min())
        if pv_h <= 0:
            continue
        depth = (pv_h - pv_l) / pv_h
        contractions.append({
            "high_idx": hi_idx,
            "low_idx": lo_idx,
            "high_price": round(pv_h, 2),
            "low_price": round(pv_l, 2),
            "depth": round(depth, 4),
        })

    if not contractions:
        return {"valid": False, "reason": "no high-to-low contractions found"}

    depths = [c["depth"] for c in contractions]
    is_progressive = all(depths[j] < depths[j - 1] for j in range(1, len(depths)))
    n = len(contractions)
    max_depth = max(depths)
    min_depth = min(depths)
    last_depth = depths[-1]
    weeks_in_base = (contractions[-1]["low_idx"] - contractions[0]["high_idx"]) / 5.0

    vol = df["Volume"].values
    short_days = VCP["vol_check_short_days"]
    long_days = VCP["vol_check_long_days"]
    vol_contracting = (
        float(vol[-short_days:].mean()) < float(vol[-long_days:].mean())
        if len(vol) >= long_days else False
    )
    vol_50_avg = float(vol[-50:].mean()) if len(vol) >= 50 else float(vol.mean())
    pullback_vol_thin = (
        float(vol[-short_days:].mean()) < vol_50_avg * 0.60
        if len(vol) >= short_days else False
    )

    most_recent_high = contractions[-1]["high_price"]
    still_in_base = float(close[-1]) < most_recent_high

    atr_series = compute_atr(df)
    current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else float("nan")
    avg_atr = float(atr_series.dropna().mean()) if atr_series.dropna().shape[0] else float("nan")
    atr_ratio = (current_atr / avg_atr) if (avg_atr and not np.isnan(avg_atr) and avg_atr > 0) else 1.0
    atr_compressed = atr_ratio < 0.80

    depth_ratios = [depths[i] / depths[i - 1] for i in range(1, len(depths)) if depths[i - 1] > 0]
    depth_ratio_ok = all(0.20 <= r <= 0.65 for r in depth_ratios) if depth_ratios else True

    base_high = max(c["high_price"] for c in contractions)
    base_low = min(c["low_price"] for c in contractions)
    base_range = base_high - base_low
    pivot_relative = (most_recent_high - base_low) / base_range if base_range > 0 else 0.5
    in_upper_third = pivot_relative >= 0.67

    passes_count = VCP["min_contractions"] <= n <= VCP["max_contractions"]
    passes_max_depth = max_depth < VCP["max_contraction_depth"]
    passes_min_depth = min_depth >= VCP["min_contraction_depth"]
    passes_tightest = last_depth <= VCP["tightest_contraction"]
    passes_duration = weeks_in_base >= VCP["min_weeks"]

    is_valid_vcp = (
        passes_count and passes_max_depth and passes_min_depth
        and passes_tightest and passes_duration and vol_contracting and still_in_base
    )

    quality_factors = [
        passes_count, passes_max_depth, passes_tightest, passes_duration,
        is_progressive, vol_contracting, pullback_vol_thin, atr_compressed,
        depth_ratio_ok, in_upper_third, still_in_base,
    ]
    vcp_quality = sum(quality_factors) / len(quality_factors)

    return {
        "valid": bool(is_valid_vcp),
        "contractions": contractions,
        "n_contractions": n,
        "max_depth": round(max_depth, 4),
        "min_depth": round(min_depth, 4),
        "last_depth": round(last_depth, 4),
        "weeks_in_base": round(weeks_in_base, 1),
        "is_progressive": bool(is_progressive),
        "vol_contracting": bool(vol_contracting),
        "still_in_base": bool(still_in_base),
        "pivot_high_price": round(most_recent_high, 2),
        "vcp_quality": round(vcp_quality, 3),
        "passes_count": bool(passes_count),
        "passes_max_depth": bool(passes_max_depth),
        "passes_tightest": bool(passes_tightest),
        "passes_duration": bool(passes_duration),
        "pullback_vol_thin": bool(pullback_vol_thin),
        "atr_compressed": bool(atr_compressed),
        "atr_ratio": round(float(atr_ratio), 3),
        "depth_ratio_ok": bool(depth_ratio_ok),
        "in_upper_third": bool(in_upper_third),
    }


def ret_52w(df: pd.DataFrame) -> float | None:
    if len(df) < 20:
        return None
    window = df["Close"].tail(252)
    if len(window) < 20 or float(window.iloc[0]) <= 0:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def composite_score(tt: dict[str, Any], vcp: dict[str, Any], rs_percentile: float | None) -> float:
    """0-100 research score without MarketSmith fields."""
    trend = float(tt.get("trend_score") or 0.0)
    vq = float(vcp.get("vcp_quality") or 0.0)
    if not vcp.get("valid"):
        vq *= 0.55
    rs = 0.0 if rs_percentile is None else max(0.0, min(1.0, rs_percentile / 100.0))
    score = 100.0 * (0.40 * trend + 0.40 * vq + 0.20 * rs)
    if tt.get("passes_template") and vcp.get("valid"):
        score = min(100.0, score + 5.0)
    return round(score, 1)


def evaluate(df: pd.DataFrame, *, rs_percentile: float | None = None) -> dict[str, Any]:
    """Evaluate one OHLCV frame; returns research payload."""
    if df is None or len(df) < 200:
        return {
            "strategy": STRATEGY_ID,
            "ok": False,
            "reason": "insufficient history (need ~200 trading days)",
        }

    tt = trend_template(df)
    vcp_window = df.tail(126) if len(df) > 126 else df
    vcp = measure_contractions(vcp_window)
    score = composite_score(tt, vcp, rs_percentile)
    r52 = ret_52w(df)

    return {
        "strategy": STRATEGY_ID,
        "ok": True,
        "score": score,
        "stage2": bool(tt.get("passes_template")),
        "vcp_valid": bool(vcp.get("valid")),
        "pivot": vcp.get("pivot_high_price"),
        "last_depth": vcp.get("last_depth"),
        "n_contractions": vcp.get("n_contractions"),
        "rs_percentile": None if rs_percentile is None else round(rs_percentile, 1),
        "close": tt.get("close"),
        "trend": tt,
        "vcp": vcp,
        "ret_52w": None if r52 is None else round(r52 * 100.0, 2),
    }
