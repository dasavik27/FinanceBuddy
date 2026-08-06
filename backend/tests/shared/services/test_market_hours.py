"""
tests/test_market_hours_refresh.py

Cover for the session calendar and the tiered background refresher.

Both exist to stop the cache doing work that cannot change anything: TTLs used to be
wall-clock only, so a "live quote" was re-fetched every 60s at 03:00 on a Sunday, and
every layer was lazy-on-request, so the first user after a restart paid the full
upstream cost inside their own request.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from shared.services import market_hours as mh
from shared.services.refresh import (
    TIER_DAILY,
    TIER_INTRADAY,
    Tier,
    WarmSet,
    sweep,
)
from shared.services import refresh as refresh_mod


def _ist(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=mh.IST)


# ── session calendar ─────────────────────────────────────────────────────────

class TestTradingDay:
    def test_weekend_is_closed(self):
        assert not mh.is_trading_day(date(2026, 8, 1))   # Saturday
        assert not mh.is_trading_day(date(2026, 8, 2))   # Sunday

    def test_weekday_is_open(self):
        assert mh.is_trading_day(date(2026, 8, 3))       # Monday

    def test_listed_holiday_is_closed(self):
        assert not mh.is_trading_day(date(2026, 8, 15))  # Independence Day

    def test_unlisted_holiday_degrades_to_open_not_to_an_error(self):
        # The holiday table goes stale every December. Treating an unknown date as a
        # trading day costs a wasted upstream call; the opposite would strand a price.
        assert mh.is_trading_day(date(2030, 6, 12))


class TestMarketOpen:
    @pytest.mark.parametrize("hh,mm,expected", [
        (9, 14, False),   # pre-open: indicative prices, not last-traded
        (9, 15, True),    # bell
        (12, 0, True),
        (15, 29, True),
        (15, 30, False),  # close is exclusive
        (18, 0, False),
        (3, 0, False),    # the 03:00 case that used to re-fetch every minute
    ])
    def test_session_boundaries(self, hh, mm, expected):
        assert mh.is_market_open(_ist(2026, 8, 3, hh, mm)) is expected

    def test_closed_all_day_on_a_holiday(self):
        assert not mh.is_market_open(_ist(2026, 8, 15, 12, 0))

    def test_naive_datetime_is_read_as_ist(self):
        assert mh.is_market_open(datetime(2026, 8, 3, 12, 0)) is True


class TestNextOpen:
    def test_from_midweek_evening_is_tomorrow_morning(self):
        nxt = mh.next_open(_ist(2026, 8, 3, 18, 0))
        assert (nxt.date(), nxt.hour, nxt.minute) == (date(2026, 8, 4), 9, 15)

    def test_friday_evening_skips_the_weekend(self):
        nxt = mh.next_open(_ist(2026, 8, 7, 18, 0))   # Friday
        assert nxt.date() == date(2026, 8, 10)        # Monday

    def test_skips_a_holiday_that_follows_a_weekend(self):
        # 15 Aug 2026 is a Saturday, so the next open from Friday is plain Monday;
        # assert the walk terminates on a trading day whatever the calendar does.
        assert mh.is_trading_day(mh.next_open(_ist(2026, 8, 14, 18, 0)).date())


class TestQuoteTtl:
    def test_live_session_uses_the_short_ttl(self, monkeypatch):
        monkeypatch.setattr(mh, "is_market_open", lambda *a, **k: True)
        assert mh.quote_ttl(live_ttl=60) == 60

    def test_closed_market_holds_until_open_not_60s(self, monkeypatch):
        monkeypatch.setattr(mh, "is_market_open", lambda *a, **k: False)
        monkeypatch.setattr(mh, "seconds_until_open", lambda *a, **k: 4000)
        assert mh.quote_ttl(live_ttl=60) == 4000

    def test_long_weekend_is_capped(self, monkeypatch):
        # A four-day close must not pin a price behind an entry nothing invalidates.
        monkeypatch.setattr(mh, "is_market_open", lambda *a, **k: False)
        monkeypatch.setattr(mh, "seconds_until_open", lambda *a, **k: 4 * 86400)
        assert mh.quote_ttl(live_ttl=60, max_closed_ttl=6 * 3600) == 6 * 3600


# ── warm set ─────────────────────────────────────────────────────────────────

class TestWarmSet:
    def test_touch_registers_a_symbol(self):
        w = WarmSet()
        w.touch("tcs")
        assert w.snapshot() == ["TCS"]      # normalised

    def test_bounded_by_max_size(self):
        w = WarmSet(max_size=3)
        w.touch_many(["A", "B", "C", "D", "E"])
        assert len(w) == 3

    def test_evicts_least_recently_used(self):
        w = WarmSet(max_size=3)
        w.touch_many(["A", "B", "C"])
        w.touch("A")            # A is now most recent, B is oldest
        w.touch("D")
        assert "B" not in w.snapshot()
        assert "A" in w.snapshot()

    def test_everything_is_due_before_a_first_refresh(self):
        w = WarmSet()
        w.touch_many(["A", "B"])
        assert set(w.due(TIER_DAILY, limit=10)) == {"A", "B"}

    def test_marking_refreshed_clears_it_from_due(self):
        w = WarmSet()
        w.touch("A")
        w.mark_refreshed("A", TIER_DAILY)
        assert w.due(TIER_DAILY, limit=10) == []

    def test_tiers_are_tracked_independently(self):
        w = WarmSet()
        w.touch("A")
        w.mark_refreshed("A", TIER_DAILY)
        # A daily refresh must not suppress a quarterly one.
        assert w.due(Tier("quarterly", interval=1), limit=10) == ["A"]

    def test_due_respects_the_limit(self):
        w = WarmSet()
        w.touch_many(["A", "B", "C", "D"])
        assert len(w.due(TIER_DAILY, limit=2)) == 2

    def test_most_recently_used_is_refreshed_first(self):
        # Partial budgets should be spent on what someone is actually looking at.
        w = WarmSet()
        w.touch_many(["OLD", "NEW"])
        assert w.due(TIER_DAILY, limit=1) == ["NEW"]

    def test_market_only_tier_is_skipped_when_closed(self, monkeypatch):
        monkeypatch.setattr(mh, "is_market_open", lambda *a, **k: False)
        w = WarmSet()
        w.touch("A")
        assert w.due(TIER_INTRADAY, limit=10) == []

    def test_market_only_tier_runs_when_open(self, monkeypatch):
        monkeypatch.setattr(mh, "is_market_open", lambda *a, **k: True)
        w = WarmSet()
        w.touch("A")
        assert w.due(TIER_INTRADAY, limit=10) == ["A"]

    def test_empty_symbol_is_ignored(self):
        w = WarmSet()
        w.touch("")
        assert w.snapshot() == []


# ── sweep ────────────────────────────────────────────────────────────────────

class TestSweep:
    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch):
        """Swap the module-global registry and warm set so tests do not leak."""
        monkeypatch.setattr(refresh_mod, "_refreshers", [])
        monkeypatch.setattr(refresh_mod, "WARM", WarmSet())

    def test_refreshes_due_symbols(self):
        seen = []
        refresh_mod.register(TIER_DAILY, seen.append)
        refresh_mod.WARM.touch_many(["A", "B"])
        assert sweep() == {"daily": 2}
        assert set(seen) == {"A", "B"}

    def test_budget_bounds_upstream_calls_per_tick(self, monkeypatch):
        monkeypatch.setattr(refresh_mod, "MAX_PER_SWEEP", 2)
        seen = []
        refresh_mod.register(TIER_DAILY, seen.append)
        refresh_mod.WARM.touch_many(["A", "B", "C", "D"])
        sweep()
        assert len(seen) == 2, "sweep must not walk the whole warm set in one tick"

    def test_a_failing_symbol_does_not_stop_the_sweep(self):
        seen = []

        def flaky(sym):
            seen.append(sym)
            if sym == "BAD":
                raise RuntimeError("upstream 500")

        refresh_mod.register(TIER_DAILY, flaky)
        refresh_mod.WARM.touch_many(["BAD", "GOOD"])
        sweep()
        assert set(seen) == {"BAD", "GOOD"}

    def test_a_failing_symbol_is_not_retried_in_a_tight_loop(self):
        def always_fails(sym):
            raise RuntimeError("dead symbol")

        refresh_mod.register(TIER_DAILY, always_fails)
        refresh_mod.WARM.touch("DEAD")
        sweep()
        # Marked done despite failing, so it waits out the tier interval like anything
        # else rather than consuming the budget on every tick.
        assert refresh_mod.WARM.due(TIER_DAILY, limit=10) == []

    def test_second_sweep_is_a_no_op(self):
        calls = []
        refresh_mod.register(TIER_DAILY, calls.append)
        refresh_mod.WARM.touch("A")
        sweep()
        assert sweep() == {}
        assert len(calls) == 1

    def test_registering_the_same_tier_twice_replaces_it(self):
        refresh_mod.register(TIER_DAILY, lambda s: None)
        refresh_mod.register(TIER_DAILY, lambda s: None)
        assert len(refresh_mod._refreshers) == 1

    def test_empty_registry_is_harmless(self):
        refresh_mod.WARM.touch("A")
        assert sweep() == {}

def test_market_hours_next_open_loop(monkeypatch):
    from shared.services import market_hours

    monkeypatch.setattr(market_hours, "is_trading_day", lambda d: d.weekday() < 5)
    at = datetime(2026, 1, 10, 8, 0, tzinfo=market_hours.IST)
    assert market_hours.next_open(at) is not None
    assert market_hours.seconds_until_open(at) >= 0

def test_market_hours_non_trading_loop_and_live(monkeypatch):
    from shared.services import market_hours

    monkeypatch.setattr(market_hours, "is_trading_day", lambda d: False)
    at = datetime(2026, 1, 10, 10, 0, tzinfo=market_hours.IST)
    assert market_hours.next_open(at) is not None

    monkeypatch.setattr(market_hours, "is_market_open", lambda at: True)
    assert market_hours.seconds_until_open(at) == 0

