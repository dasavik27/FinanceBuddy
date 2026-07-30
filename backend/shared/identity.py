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

What this is and is not
-----------------------
This is *identification*, not authentication. `X-User-PAN` is asserted by the
client and carries no proof of possession, so anyone who knows a PAN can present
it. What this layer buys:

  - one user can no longer read another's session by holding a session_id
  - /accounts/summary no longer enumerates every PAN on the deployment
  - a purge request cannot target someone else's PAN

What it does not buy: resistance to a caller who simply sends a PAN that is not
theirs. PAN is a 10-character identifier printed on documents, not a secret.
Closing that gap needs a real credential (a signed token from an authenticated
login), which is a product decision rather than a bug fix - recorded in
SECURITY.md so it is not mistaken for done.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

# Standard Indian PAN: 5 letters, 4 digits, 1 letter.
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

# Three states are distinguishable, and the distinction is load-bearing:
#
#   _UNSET  - not inside a request at all. Scripts, the GC daemon, the test suite.
#             These are trusted internal callers running in-process.
#   None    - inside a request that presented no usable PAN. An anonymous HTTP
#             caller. Must NOT reach an owned record.
#   "ABC..." - inside a request asserting that PAN.
#
# Collapsing the first two would mean either locking internal callers out of their
# own data or letting an anonymous HTTP request read anybody's. IdentityMiddleware
# always enters identity_scope(), even when the header is missing, so an HTTP request
# can never observe _UNSET.
_UNSET = "\x00__no_request__"

_current_pan: ContextVar[str] = ContextVar("current_pan", default=_UNSET)


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
    log line is durable personal data sitting outside the 24h retention the rest of
    the system honours. Enough of the tail is kept to correlate two lines about the
    same user during an incident.
    """
    if not raw:
        return "<none>"
    tail = raw.strip().upper()[-4:]
    return f"******{tail}"


@contextmanager
def identity_scope(pan: Optional[str]) -> Iterator[Optional[str]]:
    """Bind the caller's PAN for the duration of a request."""
    token = _current_pan.set(pan)
    try:
        yield pan
    finally:
        _current_pan.reset(token)


def current_pan() -> Optional[str]:
    """
    The PAN this request asserted, or None if it asserted none / there is no request.

    Callers must treat None as "unauthenticated", never as "authorized for
    everything" - use owns_record() to make access decisions rather than comparing
    this yourself.
    """
    value = _current_pan.get()
    return None if value is _UNSET else value


def in_request() -> bool:
    """True when running inside a request scope (i.e. behind IdentityMiddleware)."""
    return _current_pan.get() is not _UNSET


def owns_record(owner_pan: Optional[str]) -> bool:
    """
    May the current caller access a record owned by `owner_pan`?

    The rules, in order:

    - not inside a request - allowed. An in-process caller (the GC daemon, a
      migration script, the test suite) is trusted; it did not arrive over HTTP.
    - `owner_pan` falsy - the record is unowned, e.g. uploaded before any PAN was
      associated with it. There is nobody to protect it from. Allowed.
    - owned, but the request asserted no PAN - denied. An anonymous caller holding
      a session_id must not be able to read a portfolio that belongs to someone.
    - otherwise - allowed only on an exact match.

    The first rule is safe specifically because IdentityMiddleware wraps every HTTP
    request in identity_scope(), so no request can reach it - see the note on
    _UNSET above. If that middleware is ever removed, every route silently becomes
    a trusted internal caller, so it is covered by a test.
    """
    if not in_request():
        return True
    if not owner_pan:
        return True
    caller = current_pan()
    if caller is None:
        return False
    return caller == owner_pan
