"""Unit tests for shared/services/refresh.py."""

from shared.services import refresh

def test_refresh_sweep_budget_exhausted(monkeypatch):
    from shared.services import refresh

    refresh.WARM._entries.clear()
    refresh.WARM.touch("AAA")
    refresh.WARM.touch("BBB")
    refresh.register(refresh.TIER_STATIC, lambda sym: None)
    monkeypatch.setattr(refresh, "MAX_PER_SWEEP", 1)
    done = refresh.sweep()
    assert sum(done.values()) <= 1

def test_refresh_sweep_inner_budget_break(monkeypatch):
    from shared.services import refresh

    refresh.WARM._entries.clear()
    refresh.WARM.touch("AAA")
    refresh.WARM.touch("BBB")
    refresh.register(refresh.TIER_STATIC, lambda sym: None)
    monkeypatch.setattr(refresh, "MAX_PER_SWEEP", 1)
    done = refresh.sweep()
    assert sum(done.values()) == 1

