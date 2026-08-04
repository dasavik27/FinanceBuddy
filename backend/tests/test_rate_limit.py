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
