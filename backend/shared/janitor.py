"""
shared/janitor.py - the periodic background sweep, owned by no domain.

What this replaces
------------------
There was one garbage-collection thread, and it lived in
domains/mutual_funds/sessions.py. It started as an import side effect of that module:

    threading.Thread(target=_session_purge_worker, daemon=True).start()

and its body reached into two other domains:

    from domains.tax_expert.tax_sessions import purge_expired_from_disk
    from domains.equity.sessions import purge_expired as purge_equity


So the Mutual Funds domain was responsible for garbage-collecting Tax Expert and
Equity, and disabling or removing MF would have silently stopped GC for both - with no
error, just unbounded memory growth in domains that never mentioned MF.

The shape now
-------------
Domains register their own sweep at import:

    from shared import janitor
    janitor.register("mutual_funds.sessions", _purge_resident_sessions)

and the composition root (main.py's lifespan) starts the thread. Adding a domain means
editing that domain; nothing here and nothing in main.py needs to know about it. A
domain that is never imported never registers, which is correct - it has nothing
resident to sweep.

Each sweep runs inside its own try/except, so one domain raising cannot stop the
others from running. This mirrors the old behaviour, which wrapped each step
individually for the same reason.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Seconds between sweeps. 10 minutes, matching the interval the MF daemon used.
DEFAULT_INTERVAL_SECONDS = 600

_sweeps: List[Tuple[str, Callable[[], object]]] = []
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


def register(name: str, sweep: Callable[[], object]) -> None:
    """
    Register a callable to run on every sweep.

    `name` is used only for logging, and should identify the module so a failing sweep
    is attributable. Registering the same name twice replaces the first - modules can
    be re-imported under test without stacking duplicates.
    """
    with _lock:
        for i, (existing, _) in enumerate(_sweeps):
            if existing == name:
                _sweeps[i] = (name, sweep)
                return
        _sweeps.append((name, sweep))
    logger.debug("[JANITOR] registered sweep %s", name)


def registered() -> List[str]:
    """Names of the currently registered sweeps, for diagnostics and tests."""
    with _lock:
        return [name for name, _ in _sweeps]


def run_once() -> dict:
    """
    Run every registered sweep once. Never raises.

    Returns {name: result-or-None}, so a caller (a test, or a diagnostics endpoint)
    can see what ran and what each sweep reported.
    """
    with _lock:
        snapshot = list(_sweeps)

    results = {}
    for name, sweep in snapshot:
        try:
            results[name] = sweep()
        except Exception as e:
            # One domain's failure must not skip the rest.
            logger.error("[JANITOR] sweep %s failed: %s", name, e)
            results[name] = None
    return results


def _worker(interval: int) -> None:
    while True:
        # Sleep first: at startup every store is empty, so an immediate sweep is pure
        # cost on a cold box that is busy serving its first requests.
        time.sleep(interval)
        run_once()


def start(interval: int = DEFAULT_INTERVAL_SECONDS) -> bool:
    """
    Start the sweep thread. Idempotent - returns False if already running.

    Called from main.py's lifespan rather than at import, so that importing a domain
    module (in a test, a script, or a migration) does not spawn a background thread.
    """
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _thread = threading.Thread(
            target=_worker, args=(interval,), daemon=True, name="janitor",
        )
        _thread.start()
    logger.info(
        "[JANITOR] started, every %ds, sweeps: %s",
        interval, ", ".join(registered()) or "(none registered)",
    )
    return True
