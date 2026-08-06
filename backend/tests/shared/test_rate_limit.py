"""Unit tests for the in-process sliding-window limiter."""

from shared.rate_limit import SlidingWindowLimiter


def test_allows_up_to_max_then_blocks():
    lim = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    assert lim.allow("a")
    assert lim.allow("a")
    assert lim.allow("a")
    assert not lim.allow("a")
    # Different key is independent.
    assert lim.allow("b")


def test_reset_clears_hits():
    lim = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    assert lim.allow("x")
    assert not lim.allow("x")
    lim.reset()
    assert lim.allow("x")


def test_rate_limiter_expires_old_hits():
    import time

    lim = SlidingWindowLimiter(max_calls=2, window_seconds=0.05)
    assert lim.allow("k") is True
    assert lim.allow("k") is True
    assert lim.allow("k") is False
    time.sleep(0.06)
    assert lim.allow("k") is True
