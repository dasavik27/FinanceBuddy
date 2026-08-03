"""
shared/services/market_hours.py

NSE session calendar.

Cache TTLs in this codebase were wall-clock only, so a 60s "live quote" entry was
re-fetched every minute at 03:00 on a Sunday for a price that had not moved since
Friday's close - and, conversely, nothing shortened during the session. This module is
the single place that answers "can this number still change?", so a TTL can be derived
from market state instead of from a constant.

Pure and offline: stdlib only, no network, no I/O. Every function here is called on the
request path, so none of them may block.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

#: Normal equity session. Pre-open (09:00-09:15) is deliberately excluded: it produces
#: indicative prices that are not last-traded prices.
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

#: NSE trading holidays. Weekends are computed, so only weekday closures are listed.
#:
#: This is a static table and it goes stale: NSE publishes the next year's list each
#: December. When it does, `is_trading_day` degrades to treating an unlisted holiday as
#: a trading day - which costs a few wasted upstream calls, never a wrong answer. That
#: is the safe direction, so a stale table is not an outage.
_HOLIDAYS: frozenset[date] = frozenset({
    # 2026
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 4),    # Holi
    date(2026, 3, 20),   # Id-ul-Fitr
    date(2026, 3, 26),   # Ram Navami
    date(2026, 3, 31),   # Mahavir Jayanti
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 5, 27),   # Bakri Id
    date(2026, 6, 26),   # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 9, 14),   # Ganesh Chaturthi
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 9),   # Diwali Laxmi Pujan
    date(2026, 11, 10),  # Diwali Balipratipada
    date(2026, 11, 24),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
})


def now_ist() -> datetime:
    """Current time in IST. The only clock read in this module."""
    return datetime.now(IST)


def is_trading_day(d: date) -> bool:
    """Whether `d` is a weekday the exchange is open on."""
    return d.weekday() < 5 and d not in _HOLIDAYS


def is_market_open(at: datetime | None = None) -> bool:
    """Whether the cash-equity session is live right now."""
    at = at or now_ist()
    if at.tzinfo is None:
        at = at.replace(tzinfo=IST)
    else:
        at = at.astimezone(IST)
    if not is_trading_day(at.date()):
        return False
    return SESSION_OPEN <= at.time() < SESSION_CLOSE


def next_open(at: datetime | None = None) -> datetime:
    """Start of the next session at or after `at`."""
    at = (at or now_ist()).astimezone(IST)
    candidate = at.replace(
        hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0,
    )
    if candidate <= at or not is_trading_day(candidate.date()):
        candidate += timedelta(days=1)
        candidate = candidate.replace(
            hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0,
        )
    # A long weekend plus Diwali is the worst realistic run; 10 bounds it without
    # risking an unbounded loop if the holiday table is ever malformed.
    for _ in range(10):
        if is_trading_day(candidate.date()):
            return candidate
        candidate += timedelta(days=1)
    return candidate


def seconds_until_open(at: datetime | None = None) -> int:
    """Seconds until the next session opens. 0 while the market is live."""
    at = (at or now_ist()).astimezone(IST)
    if is_market_open(at):
        return 0
    return max(0, int((next_open(at) - at).total_seconds()))


def quote_ttl(live_ttl: int = 60, max_closed_ttl: int = 6 * 3600) -> int:
    """
    How long a last-traded price stays valid.

    Live: `live_ttl`. Closed: until the next open, because the number provably cannot
    change before then - capped so a four-day weekend does not pin a price behind an
    entry nothing will ever invalidate, and so a stale holiday table cannot strand one
    for a week.
    """
    if is_market_open():
        return live_ttl
    return max(live_ttl, min(seconds_until_open(), max_closed_ttl))


def fundamentals_ttl(default: int = 6 * 3600) -> int:
    """
    How long fundamentals stay valid.

    Statements change four times a year on results day, so the binding constraint is
    not freshness but noticing a filing. Held longer outside market hours, when no
    company is reporting.
    """
    return default if is_market_open() else max(default, 12 * 3600)
