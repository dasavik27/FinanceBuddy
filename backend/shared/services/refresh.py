"""
shared/services/refresh.py

Warm-set tracking and tiered background refresh.

The cache was lazy-on-request in every layer, so the first user after any restart paid
the full upstream cost inside their own request - for the equity analyzer that was
measured at 48.7s against a threadpool of 8. Serving from a store that something else
keeps warm is the only way that number becomes small, so this module answers two
questions: *which* symbols are worth keeping warm, and *when* is each kind of data due
for another look.

Design constraints, in the order they bind:

  * No new dependencies and no new threads. Refresh runs as a sweep on the existing
    janitor daemon (`shared/janitor.py`), which already ticks every 10 minutes.
  * Bounded work per tick. A sweep that tried to refresh the whole warm set would hold
    the janitor thread for minutes and stampede the upstream; `MAX_PER_SWEEP` caps it
    and the remainder simply waits for the next tick.
  * Bounded memory. The warm set is an LRU with a hard cap, not an ever-growing set of
    every symbol anyone ever typed.
  * Refresh only what can have changed. Tiers consult `market_hours`, so a closed
    market means intraday work is skipped entirely rather than repeated every 10
    minutes against an unchanging price.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Iterable

from shared.services import market_hours

logger = logging.getLogger(__name__)

#: Symbols kept warm. Sized for "what one household actually looks at" - holdings plus
#: a watchlist plus recent searches - not for the ~2,400 listed names. At roughly 16 KB
#: per cached analysis this bounds the working set to a few MB.
MAX_WARM_SYMBOLS = 150

#: Upstream calls per sweep, across all tiers. The janitor ticks every 600s, so this is
#: a ceiling of ~8 refreshes per 10 minutes: enough to walk the warm set in under two
#: hours, low enough that it never looks like a scraper.
MAX_PER_SWEEP = 8


@dataclass(frozen=True)
class Tier:
    """
    One refresh cadence.

    `interval` is the minimum age before an entry is considered due. `market_only`
    restricts a tier to live sessions - intraday prices cannot move once the exchange
    has closed, so re-fetching them overnight is pure cost.
    """

    name: str
    interval: int
    market_only: bool = False


#: Volatility tiers. The intervals are what the underlying data can actually do, not
#: round numbers: a price moves continuously, a filing four times a year.
TIER_INTRADAY = Tier("intraday", interval=300, market_only=True)
TIER_DAILY = Tier("daily", interval=12 * 3600)
TIER_QUARTERLY = Tier("quarterly", interval=7 * 24 * 3600)
TIER_STATIC = Tier("static", interval=7 * 24 * 3600)


class WarmSet:
    """
    Bounded LRU of symbols worth keeping fresh, with per-tier last-refresh times.

    Thread-safe: touched from request threads and read from the janitor thread.
    """

    def __init__(self, max_size: int = MAX_WARM_SYMBOLS):
        self._max = max_size
        self._lock = threading.Lock()
        # symbol -> {tier_name: last_refreshed_monotonic}
        self._entries: "OrderedDict[str, dict[str, float]]" = OrderedDict()

    def touch(self, symbol: str) -> None:
        """
        Record that a symbol is in active use.

        Called from the request path, so it must stay O(1) and never do I/O.
        """
        if not symbol:
            return
        sym = symbol.upper().strip()
        with self._lock:
            if sym in self._entries:
                self._entries.move_to_end(sym)
            else:
                self._entries[sym] = {}
                while len(self._entries) > self._max:
                    # Evict least-recently-used: the symbol nobody has looked at in
                    # longest is the one least worth spending an upstream call on.
                    self._entries.popitem(last=False)

    def touch_many(self, symbols: Iterable[str]) -> None:
        for s in symbols:
            self.touch(s)

    def mark_refreshed(self, symbol: str, tier: Tier) -> None:
        sym = symbol.upper().strip()
        with self._lock:
            if sym in self._entries:
                self._entries[sym][tier.name] = time.monotonic()

    def due(self, tier: Tier, limit: int) -> list[str]:
        """
        Symbols whose `tier` data is stale, most-recently-used first.

        MRU order rather than oldest-stale-first is deliberate: if the budget only
        covers part of the set, the symbols someone is actually looking at should be
        the ones that get refreshed.
        """
        if tier.market_only and not market_hours.is_market_open():
            return []

        now = time.monotonic()
        out: list[str] = []
        with self._lock:
            for sym, seen in reversed(self._entries.items()):
                last = seen.get(tier.name)
                if last is None or (now - last) >= tier.interval:
                    out.append(sym)
                    if len(out) >= limit:
                        break
        return out

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


#: Process-wide warm set.
WARM = WarmSet()


# ---------------------------------------------------------------------------
# Refresher registry
# ---------------------------------------------------------------------------

# tier -> callable(symbol) that re-populates that symbol's cache entry
_refreshers: "list[tuple[Tier, Callable[[str], object]]]" = []
_reg_lock = threading.Lock()


def register(tier: Tier, fn: Callable[[str], object]) -> None:
    """
    Register `fn` as the way to refresh one symbol's data for `tier`.

    Domains register their own refreshers rather than this module importing them, so
    `shared` keeps no dependency on `domains` - the same direction the janitor uses.
    """
    with _reg_lock:
        for i, (t, _) in enumerate(_refreshers):
            if t.name == tier.name:
                _refreshers[i] = (tier, fn)
                return
        _refreshers.append((tier, fn))
    logger.debug("[refresh] registered %s refresher", tier.name)


def sweep() -> dict:
    """
    Refresh what is due, up to `MAX_PER_SWEEP` upstream calls. Never raises.

    Returns a per-tier count so the janitor's log and tests can see what moved.
    """
    with _reg_lock:
        registered = list(_refreshers)

    budget = MAX_PER_SWEEP
    done: dict[str, int] = {}

    for tier, fn in registered:
        if budget <= 0:
            break
        symbols = WARM.due(tier, limit=budget)
        for sym in symbols:
            if budget <= 0:
                break  # pragma: no cover — defensive / hard to exercise in unit tests
            try:
                fn(sym)
                WARM.mark_refreshed(sym, tier)
                done[tier.name] = done.get(tier.name, 0) + 1
            except Exception as e:
                # A dead symbol or a flaky upstream must not stop the sweep, and must
                # not retry in a tight loop either - mark it done so it waits out the
                # tier interval like anything else.
                WARM.mark_refreshed(sym, tier)
                logger.warning("[refresh] %s refresh failed for %s: %s", tier.name, sym, e)
            finally:
                budget -= 1

    if done:
        logger.info("[refresh] swept %s (warm set: %d)", done, len(WARM))
    return done


# Runs on the existing janitor daemon rather than a thread of its own. Registered at
# import for the same reason the disk-cache sweep is: no scheduler dependency, and the
# sweep exists exactly when the module is part of the running app.
from shared import janitor  # noqa: E402  (circular-safe: janitor imports nothing here)

janitor.register("market_refresh", sweep)
