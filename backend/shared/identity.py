"""
shared/identity.py - caller identity for the current request.

Why a ContextVar instead of a FastAPI dependency on every route
---------------------------------------------------------------
Ownership has to be enforced at the *data access* boundary - get_session(),
get_tax_session(), get_history() - rather than on each of the ~26 route
signatures. A forgotten `Depends()` on a route added six months from now is a
silent authorization hole; a check inside get_session() cannot be forgotten,
because there is no other way to reach a portfolio.

This follows the pattern already established by RequestCacheMiddleware: pure ASGI
middleware sets a ContextVar, and anyio copies the context into the threadpool
worker that runs sync endpoints, so the value is visible to both `def` and
`async def` handlers.

What identifies a caller
------------------------
A `user_id` - a uuid this application issues and stores in `users.id`. Not a PAN.

PAN used to be all three of the login credential, the owner column on every table,
and the default CAS PDF password. It is a ten-character string printed on financial
documents, so "anyone who knows a PAN can read that user's data" was the actual
posture. It is now an attribute hanging off the account (`profiles.pan`), still
needed for AIS matching and as the CAS password default, but no longer deciding
who anyone is.

The user_id is resolved by the middleware from whatever credential arrived - a
verified OIDC token, or the legacy PAN header - via `identities`. Nothing below
this layer knows or cares which.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass
from contextvars import ContextVar
from typing import Iterator, Optional

# Standard Indian PAN: 5 letters, 4 digits, 1 letter.
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


@dataclass(frozen=True)
class Caller:
    """The authenticated caller. `pan` is profile data, never the identity."""

    user_id: str
    pan: Optional[str] = None
    status: str = "active"
    role: str = "user"


# Three states are distinguishable, and the distinction is load-bearing:
#
#   _UNSET  - not inside a request at all. Scripts, the GC daemon, the test suite.
#             These are trusted internal callers running in-process.
#   None    - inside a request that presented no usable credential. An anonymous
#             HTTP caller. Must NOT reach an owned record.
#   Caller  - inside a request authenticated as that user.
#
# Collapsing the first two would mean either locking internal callers out of their
# own data or letting an anonymous HTTP request read anybody's. IdentityMiddleware
# always enters identity_scope(), even with no credential, so an HTTP request can
# never observe _UNSET.
_UNSET = "\x00__no_request__"

_current_caller: ContextVar = ContextVar("current_caller", default=_UNSET)


def normalize_pan(raw: Optional[str]) -> Optional[str]:
    """Upper-case and validate a PAN. Returns None if absent or malformed."""
    if not raw:
        return None
    pan = raw.strip().upper()
    return pan if PAN_PATTERN.match(pan) else None


def mask_pan(raw: Optional[str]) -> str:
    """
    A PAN safe to write to a log, keeping only the last 4 characters.

    Render (and any hosted log aggregator) retains stdout, so an unmasked PAN in a
    log line is durable personal data sitting outside the retention the rest of the
    system honours. Enough of the tail is kept to correlate two lines about the same
    user during an incident.
    """
    if not raw:
        return "<none>"
    tail = raw.strip().upper()[-4:]
    return f"******{tail}"


@contextmanager
def identity_scope(caller: Optional[Caller]) -> Iterator[Optional[Caller]]:
    """Bind the caller for the duration of a request."""
    token = _current_caller.set(caller)
    try:
        yield caller
    finally:
        _current_caller.reset(token)


def current_caller() -> Optional[Caller]:
    """The authenticated caller, or None if anonymous / outside a request."""
    value = _current_caller.get()
    return None if value is _UNSET else value


def current_user_id() -> Optional[str]:
    """
    The user_id this request authenticated as, or None.

    Callers must treat None as "unauthenticated", never as "authorized for
    everything" - use owns_record() to make access decisions rather than comparing
    this yourself.
    """
    caller = current_caller()
    return caller.user_id if caller else None


def current_pan() -> Optional[str]:
    """
    The caller's PAN, where their profile has one.

    This is profile data. It is the CAS PDF password default and the AIS matching
    key; it is *not* an authorization input. Never compare it to decide access -
    that is what owns_record() is for.
    """
    caller = current_caller()
    return caller.pan if caller else None


def in_request() -> bool:
    """True when running inside a request scope (i.e. behind IdentityMiddleware)."""
    return _current_caller.get() is not _UNSET


def owns_record(owner_user_id: Optional[str]) -> bool:
    """
    May the current caller access a record owned by `owner_user_id`?

    The rules, in order:

    - not inside a request - allowed. An in-process caller (the GC daemon, a
      migration script, the test suite) is trusted; it did not arrive over HTTP.
    - `owner_user_id` falsy - the record is unowned. There is nobody to protect it
      from. Allowed.
    - owned, but the request authenticated as nobody - denied. An anonymous caller
      holding a session_id must not read a portfolio that belongs to someone.
    - otherwise - allowed only on an exact match.

    The first rule is safe specifically because IdentityMiddleware wraps every HTTP
    request in identity_scope(), so no request can reach it - see the note on _UNSET
    above. If that middleware is ever removed, every route silently becomes a trusted
    internal caller, so it is covered by a test.
    """
    if not in_request():
        return True
    if not owner_user_id:
        return True
    caller = current_user_id()
    if caller is None:
        return False
    return str(caller) == str(owner_user_id)
