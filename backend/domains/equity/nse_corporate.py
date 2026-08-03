"""
domains/equity/nse_corporate.py

NSE disclosure data: corporate actions, filings, and the results calendar.

NSE blocks `/api/quote-equity` by policy, which is what the existing `nse_client` was
built around. It does *not* block the disclosure endpoints - corporate actions,
announcements and the event calendar all return 200 from the same session that gets a
403 on quotes. That data is also the part NSE is authoritative for and Yahoo is not:

  * yfinance reports Indian **bonus issues as splits**, indistinguishably. All four of
    RELIANCE's yfinance "splits" are 1:1 bonuses; RIL has never split. The distinction
    matters for cost basis, because a bonus share carries zero cost.
  * yfinance's split *factors* are wrong for compound actions. BAJFINANCE's June 2025
    1:2 split plus 4:1 bonus is 10x in total; yfinance reports `Stock Splits = 2.0`
    while back-adjusting prices by the full 10x, so anything keyed off `.splits`
    under-adjusts by 5x while the chart still looks right.

One hard constraint: **NSE blocks datacenter IPs.** These endpoints work from a
residential connection and time out from a cloud host. Every call here therefore fails
soft - callers get an empty list, never an exception - so a cloud deployment degrades
to "no corporate actions" rather than to a broken analyzer.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import requests

from shared.services.cache import MARKET_CACHE

logger = logging.getLogger(__name__)

_BASE = "https://www.nseindia.com/api"
_RSS_BASE = "https://nsearchives.nseindia.com/content/RSS"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

#: Short by design. These calls happen on the janitor thread or behind a warm cache, so
#: a slow NSE must not become a slow request; failing fast and serving the cached copy
#: is strictly better than holding a threadpool slot.
_TIMEOUT = 12

#: Disclosures change on filing, not continuously. A day is the right granularity for
#: actions and the calendar; announcements move faster and are held for an hour.
_TTL_ACTIONS = 24 * 3600
_TTL_CALENDAR = 12 * 3600
_TTL_ANNOUNCEMENTS = 3600

#: Hard caps. An unfiltered announcements query for RELIANCE returns 3,326 records and
#: ~2.8 MB; nothing in the UI shows more than a handful, and the rest is pure cache
#: budget. Bound at the parse boundary rather than trusting the upstream to be small.
_MAX_ITEMS = 40


def _get_json(path: str, params: dict[str, str]) -> Any:
    """
    GET one NSE JSON endpoint. Returns None on any failure, never raises.

    No cookie bootstrap: the disclosure endpoints serve a plain UA + Referer, and
    hitting the homepage first is what tends to trip the WAF.
    """
    try:
        resp = requests.get(f"{_BASE}/{path}", params=params,
                            headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("[nse_corporate] %s -> HTTP %s", path, resp.status_code)
            return None
        return resp.json()
    except Exception as e:
        # Datacenter IPs time out here. That is expected, not exceptional.
        logger.warning("[nse_corporate] %s failed: %s", path, e)
        return None


def _parse_nse_date(raw: str | None) -> str | None:
    """NSE's several date spellings -> ISO, or None. Never raises on junk."""
    if not raw or raw in ("-", "NA"):
        return None
    text = str(raw).strip().split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%B-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ── corporate actions ────────────────────────────────────────────────────────

#: Ordered longest-first so "bonus issue" is tested before "bonus".
_ACTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("bonus", re.compile(r"\bbonus\b", re.I)),
    ("split", re.compile(r"\b(split|sub[- ]?division|face value)\b", re.I)),
    ("rights", re.compile(r"\brights\b", re.I)),
    ("buyback", re.compile(r"\bbuy[- ]?back\b", re.I)),
    ("demerger", re.compile(r"\b(demerger|scheme of arrangement)\b", re.I)),
    ("dividend", re.compile(r"\bdividend\b", re.I)),
]

#: "1:2" / "1 : 2". Ratio order differs between bonus and split in NSE's own wording,
#: so the raw text is always kept alongside the parse.
_RATIO_RE = re.compile(r"(\d+)\s*:\s*(\d+)")

#: NSE states most splits as a face-value change, not a ratio:
#: "Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share".
#: The multiplier is old FV / new FV. Without this the ratio parse finds nothing and
#: the action contributes 1.0 - which is exactly how a 10x compound action silently
#: becomes 5x. Handles "Rs"/"Re", optional "/-", and decimal face values.
_FACE_VALUE_RE = re.compile(
    r"from\s+rs?\.?\s*(\d+(?:\.\d+)?)\s*/?-?\s*(?:per\s+share\s*)?to\s+rs?e?\.?\s*(\d+(?:\.\d+)?)",
    re.I,
)


def _trim_num(text: str) -> str:
    """'2.00' -> '2', '0.50' -> '0.5', '10' -> '10'. Never mangles trailing zeros."""
    return f"{float(text):g}"


def classify_action(subject: str) -> str:
    """
    Bucket an NSE `subject` string into an action type.

    Dividend is tested last: "Bonus issue and dividend" is a bonus first, and mislabeling
    a bonus as a dividend is the error that corrupts cost basis.
    """
    text = subject or ""
    for kind, pattern in _ACTION_PATTERNS:
        if pattern.search(text):
            return kind
    return "other"


def _parse_action(row: dict) -> dict[str, Any]:
    subject = (row.get("subject") or "").strip()
    kind = classify_action(subject)
    ratio = None
    if kind == "split":
        # Face-value wording first: a split subject often contains no "a:b" at all.
        fv = _FACE_VALUE_RE.search(subject)
        if fv:
            ratio = f"{_trim_num(fv.group(1))}:{_trim_num(fv.group(2))}"
    if ratio is None and kind in ("bonus", "split", "rights"):
        m = _RATIO_RE.search(subject)
        if m:
            ratio = f"{m.group(1)}:{m.group(2)}"
    return {
        "symbol": (row.get("symbol") or "").strip().upper(),
        "type": kind,
        "subject": subject,
        "ratio": ratio,
        "ex_date": _parse_nse_date(row.get("exDate")),
        "record_date": _parse_nse_date(row.get("recDate")),
        "isin": (row.get("isin") or "").strip() or None,
        "face_value": row.get("faceVal"),
    }


def corporate_actions(symbol: str) -> list[dict[str, Any]]:
    """
    Dividends, bonuses, splits and buybacks for one symbol, newest ex-date first.

    Empty list when NSE is unreachable - which is the normal case from a cloud host.
    """
    sym = symbol.upper().strip()

    def _fetch() -> list[dict[str, Any]]:
        raw = _get_json("corporates-corporateActions",
                        {"index": "equities", "symbol": sym})
        if not isinstance(raw, list):
            return []
        items = [_parse_action(r) for r in raw[:_MAX_ITEMS] if isinstance(r, dict)]
        # Undated rows sort last rather than being dropped: an announced action with no
        # ex-date yet is still worth showing.
        return sorted(items, key=lambda a: a["ex_date"] or "", reverse=True)

    return MARKET_CACHE.get_or_compute(
        f"nse_actions_v1:{sym}", _fetch, _TTL_ACTIONS,
    )


# ── results calendar ─────────────────────────────────────────────────────────

def event_calendar(symbol: str) -> list[dict[str, Any]]:
    """Board meetings and results dates for one symbol, soonest first."""
    sym = symbol.upper().strip()

    def _fetch() -> list[dict[str, Any]]:
        raw = _get_json("event-calendar", {"index": "equities", "symbol": sym})
        if not isinstance(raw, list):
            return []
        out = []
        for r in raw[:_MAX_ITEMS]:
            if not isinstance(r, dict):
                continue
            out.append({
                "symbol": (r.get("symbol") or "").strip().upper(),
                "company": (r.get("company") or "").strip(),
                "purpose": (r.get("purpose") or "").strip(),
                "date": _parse_nse_date(r.get("date")),
                "details": (r.get("bm_desc") or "").strip() or None,
            })
        return sorted(out, key=lambda e: e["date"] or "", reverse=True)

    return MARKET_CACHE.get_or_compute(
        f"nse_calendar_v1:{sym}", _fetch, _TTL_CALENDAR,
    )


# ── announcements ────────────────────────────────────────────────────────────

def announcements(symbol: str, limit: int = 15) -> list[dict[str, Any]]:
    """
    Recent exchange filings for one symbol, newest first.

    Date-bounded by the `_MAX_ITEMS` slice rather than by query parameters, because the
    unfiltered response for a large cap is several megabytes.
    """
    sym = symbol.upper().strip()

    def _fetch() -> list[dict[str, Any]]:
        raw = _get_json("corporate-announcements",
                        {"index": "equities", "symbol": sym})
        if not isinstance(raw, list):
            return []
        out = []
        for r in raw[:_MAX_ITEMS]:
            if not isinstance(r, dict):
                continue
            out.append({
                "symbol": (r.get("symbol") or "").strip().upper(),
                "subject": (r.get("desc") or r.get("subject") or "").strip(),
                "detail": (r.get("attchmntText") or "").strip()[:400] or None,
                "broadcast_at": (r.get("an_dt") or r.get("sort_date") or "").strip() or None,
                "attachment": (r.get("attchmntFile") or "").strip() or None,
            })
        return out

    items = MARKET_CACHE.get_or_compute(
        f"nse_announce_v1:{sym}", _fetch, _TTL_ANNOUNCEMENTS,
    )
    return items[:limit]


# ── split/bonus reconciliation ───────────────────────────────────────────────

def adjustment_factor(actions: list[dict[str, Any]]) -> float:
    """
    Total share-count multiplier implied by NSE's own bonus and split records.

    Exists to check yfinance's `.splits`, which is wrong for compound actions:
    BAJFINANCE's June 2025 1:2 split (2x) and 4:1 bonus (5x) are 10x together, but
    yfinance reports 2.0 while back-adjusting prices by 10x.

    Ratio conventions differ by action, and NSE states both in the same `a:b` shape:
      * bonus "4:1"  = 4 new shares for every 1 held -> 5x
      * split "1:2"  = one share becomes two         -> 2x
    """
    factor = 1.0
    for a in actions:
        if not a.get("ratio"):
            continue
        try:
            # float, not int: face-value ratios can be fractional ("Re 0.5").
            left, right = (float(x) for x in a["ratio"].split(":"))
        except (ValueError, AttributeError):
            continue
        if right <= 0 or left <= 0:
            continue
        if a["type"] == "bonus":
            factor *= (left + right) / right
        elif a["type"] == "split":
            factor *= max(left, right) / min(left, right)
    return round(factor, 6)
