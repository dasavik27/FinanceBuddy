"""
shared/session_stores.py - the registry of domains that hold resident session state.

What this replaces
------------------
Three shared routers each hardcoded the list of domains:

    shared/routers/auth.py:59      logout      -> evict_for_user on MF, equity, tax
    shared/routers/accounts.py:186 purge       -> evict_for_user on MF, equity, tax
    shared/routers/accounts.py:218 clear_caches-> clear_all      on MF, equity, tax
    shared/routers/history.py:42   delete      -> forget         on MF, equity, tax

Every one of them carried a comment saying "every domain with a resident store has to
be named here", which is the tell: the requirement was known, and enforcing it was left
to whoever remembered. It was already not enforced - the Budget domain appears in none
of those lists, and the comment in accounts.py records that Equity was missing once
before and a purge left stock portfolios readable after the rows were deleted.

Domains now register themselves at import and the routers iterate the registry, so
adding a domain means editing that domain and nothing else.

Failure policy - deliberately different from shared/janitor.py
--------------------------------------------------------------
The janitor swallows a failing sweep, because a missed GC pass is a memory cost and
the other domains should still run. These operations are the opposite: they are the
memory half of a delete, and the routers run them *before* dropping rows precisely so
that a failure aborts the request with the data still intact and still owned.

If eviction failed silently here, purge_account would go on to delete the registry
rows and leave a resident copy with no row left to name its owner - readable by anyone
holding the session id. That is the exact bug the accounts.py comment describes.

So these functions do not catch. A raising store propagates, the router 500s, and
nothing is deleted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionStore:
    """
    One domain's resident-state hooks. Every hook is optional.

    A domain with no in-memory store (Budget, today) simply does not register - there
    is nothing to evict, and an empty registry entry would only be noise.
    """

    name: str
    #: Drop everything belonging to a user. Returns a count. Used by logout and purge.
    evict_user: Optional[Callable[[str], Any]] = None
    #: Drop one session id if this store holds it; a no-op otherwise, because a session
    #: id is not tagged by domain at the shared layer.
    forget_session: Optional[Callable[[str], Any]] = None
    #: Drop the entire store. Used by the cache-clear diagnostic endpoint.
    clear_all: Optional[Callable[[], Any]] = None


_stores: List[SessionStore] = []


def register(store: SessionStore) -> None:
    """Register a domain's store. Re-registering the same name replaces it."""
    for i, existing in enumerate(_stores):
        if existing.name == store.name:
            _stores[i] = store
            return
    _stores.append(store)
    logger.debug("[SESSION STORES] registered %s", store.name)


def registered() -> List[str]:
    """Names of the registered stores, for diagnostics and tests."""
    return [s.name for s in _stores]


def evict_user(user_id: str) -> int:
    """
    Drop every resident session belonging to `user_id`, across all domains.

    Returns the total evicted. Raises if any store raises - see the module docstring.
    """
    total = 0
    for store in _stores:
        if store.evict_user is None:
            continue
        result = store.evict_user(user_id)
        if isinstance(result, int):
            total += result
    return total


def forget_session(session_id: str) -> None:
    """
    Ask every store to drop `session_id`.

    Deliberately asks all of them rather than working out which domain owns the id:
    the shared `sessions` table discriminates by `upload_type`, but this layer is
    handed a bare id. forget() on an absent id is a no-op in every store.
    """
    for store in _stores:
        if store.forget_session is not None:
            store.forget_session(session_id)


def clear_all() -> Dict[str, Any]:
    """Empty every registered store. Returns {name: result} for the response body."""
    out: Dict[str, Any] = {}
    for store in _stores:
        if store.clear_all is not None:
            out[store.name] = store.clear_all()
    return out
