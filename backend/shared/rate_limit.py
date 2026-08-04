"""
Simple in-process sliding-window rate limiter.

One uvicorn worker means this is a shared cache for that process — good enough
to blunt public-endpoint abuse without Redis. Multi-worker deploys get a
per-worker budget; tighten via env if needed.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float):
        self.max_calls = max(1, int(max_calls))
        self.window = float(window_seconds)
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            cutoff = now - self.window
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_calls:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        """Test helper."""
        with self._lock:
            self._hits.clear()
