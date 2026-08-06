"""Unit tests for shared/janitor.py."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from shared import config, janitor


def test_janitor_lifecycle_and_error_isolation(monkeypatch):
    # 1. Register & deduplicate
    sweep1 = MagicMock(return_value="ok1")
    sweep2 = MagicMock(return_value="ok2")
    sweep_fail = MagicMock(side_effect=RuntimeError("Sweep exploded"))

    janitor.register("test_sweep_1", sweep1)
    janitor.register("test_sweep_fail", sweep_fail)
    assert "test_sweep_1" in janitor.registered()
    assert "test_sweep_fail" in janitor.registered()

    # Re-register same name replaces existing
    janitor.register("test_sweep_1", sweep2)
    assert janitor.registered().count("test_sweep_1") == 1

    # 2. run_once isolation
    results = janitor.run_once()
    assert results["test_sweep_1"] == "ok2"
    assert results["test_sweep_fail"] is None  # Error caught safely

    # 3. _worker execution
    called = []
    def fake_sleep(sec):
        called.append(sec)
        if len(called) >= 1:
            raise KeyboardInterrupt("Stop worker loop")

    monkeypatch.setattr(time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        janitor._worker(5)

    # 4. start daemon thread (may already be running from app lifespan)
    import shared.janitor as _janitor_mod
    _janitor_mod._thread = None
    assert janitor.start(interval=600) is True
    # Second start is idempotent
    assert janitor.start(interval=600) is False


def test_janitor_worker_runs_once(monkeypatch):
    calls = {"n": 0}

    def fake_sleep(sec):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt("stop loop")

    monkeypatch.setattr(time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        janitor._worker(1)
    assert calls["n"] == 2
