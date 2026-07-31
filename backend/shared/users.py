"""
shared/users.py - resolve a credential to an account.

`users.id` is issued here and belongs to this application. A provider's idea of who
someone is lives in `identities` as an (issuer, subject) pair pointing at that id.

That indirection is the whole point. Switching identity provider, or adding a second
one, is an INSERT into `identities` - no table is re-keyed, and no user loses their
data. Storing the provider's subject directly as the owner column would make the
provider impossible to leave, which is the single most expensive kind of coupling to
undo later.

The legacy PAN header is modelled as just another issuer. It is not special-cased
anywhere below this module: a PAN-authenticated request produces the same Caller as
a token-authenticated one, so every downstream authorization check is identical and
removing PAN login later touches only this file and the middleware.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional, Tuple

from shared import db, identity
from shared.identity import Caller

logger = logging.getLogger(__name__)

# Issuer for the pre-OIDC PAN header. A URN rather than a bare word so it cannot
# collide with a real issuer, which is always an https URL.
LEGACY_PAN_ISSUER = "urn:financebuddy:legacy-pan"

# ── Resolution cache ──────────────────────────────────────────────────────────
#
# Identity resolution runs on *every* authenticated request. Against a local file
# that was free; against a pooled network database it is a round trip - ~90 ms to
# the nearest region - before the handler starts, on every call. That is the single
# most expensive thing this migration could accidentally introduce, so the mapping
# is cached in process.
#
# Safe to cache because (issuer, subject) -> user_id is immutable once written: a
# user_id is never reassigned, and rows are only ever added. The mutable part is the
# profile PAN, so set_pan() invalidates explicitly.
#
# Bounded, because an unbounded dict keyed on caller-supplied subjects is a memory
# exhaustion vector on a 512 MB box. TTL'd as well, so `last_seen_at` still advances
# for an active user and a deleted account stops resolving within the window.
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ENTRIES = 512
_cache: "OrderedDict[Tuple[str, str], Tuple[float, Caller]]" = OrderedDict()
_cache_lock = threading.RLock()


def _cache_get(key: Tuple[str, str]) -> Optional[Caller]:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        expires_at, caller = hit
        if expires_at < time.time():
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return caller


def _cache_put(key: Tuple[str, str], caller: Caller) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + _CACHE_TTL_SECONDS, caller)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def invalidate(user_id: Optional[str] = None) -> None:
    """Drop cached resolutions - for one user, or all of them."""
    with _cache_lock:
        if user_id is None:
            _cache.clear()
            return
        for key in [k for k, (_, c) in _cache.items() if c.user_id == str(user_id)]:
            _cache.pop(key, None)


def resolve(issuer: str, subject: str, email: Optional[str] = None,
            pan: Optional[str] = None) -> Optional[Caller]:
    """
    The account for (issuer, subject), creating it on first sight.

    Provisioning on first login rather than requiring a separate signup keeps the
    flow to one round trip and means a provider-side account that already exists
    does not need a second registration step here.

    Idempotent under concurrency: two simultaneous first requests for the same
    subject would both see no row, so the insert uses ON CONFLICT and re-reads the
    winner rather than raising a unique violation at whichever one lost.
    """
    if not issuer or not subject:
        return None

    key = (issuer, subject)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM identities WHERE issuer = %s AND subject = %s",
                (issuer, subject),
            ).fetchone()

            if row is None:
                user_id = conn.execute(
                    "INSERT INTO users DEFAULT VALUES RETURNING id"
                ).fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO identities (issuer, subject, user_id, email)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (issuer, subject) DO NOTHING
                    """,
                    (issuer, subject, user_id, email),
                )
                # If the insert conflicted, another request created the account
                # first; adopt theirs so both requests agree on one id. The users row
                # created above is left unreferenced and is harmless - it holds no
                # data and cascades away with nothing attached.
                winner = conn.execute(
                    "SELECT user_id FROM identities WHERE issuer = %s AND subject = %s",
                    (issuer, subject),
                ).fetchone()
                user_id = winner[0] if winner else user_id
                logger.info("[AUTH] provisioned account for issuer=%s", issuer)
            else:
                user_id = row[0]
                conn.execute(
                    "UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,)
                )

            # PAN comes from the profile, not from the caller, so a request cannot
            # assert someone else's. The legacy path passes one in only because it
            # *is* the credential there, and it is written to the profile below.
            profile = conn.execute(
                "SELECT pan FROM profiles WHERE user_id = %s", (user_id,)
            ).fetchone()
            stored_pan = profile[0] if profile else None

            if pan and pan != stored_pan:
                conn.execute(
                    """
                    INSERT INTO profiles (user_id, pan) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                        SET pan = EXCLUDED.pan, updated_at = now()
                    """,
                    (user_id, pan),
                )
                stored_pan = pan

        caller = Caller(user_id=str(user_id), pan=stored_pan)
        _cache_put(key, caller)
        return caller
    except Exception as e:
        # Fail closed. Returning None makes the request anonymous, which owns_record
        # denies against any owned row - never accidentally authorized.
        logger.error("[AUTH] could not resolve identity for issuer=%s: %s", issuer, e)
        return None


def resolve_legacy_pan(raw_pan: str) -> Optional[Caller]:
    """
    The account for a PAN presented via the X-User-PAN header.

    This is identification, not authentication - the header carries no proof of
    possession. It exists so the Postgres cutover and the switch to real sign-in are
    separate, independently reversible changes; delete this function and its
    middleware branch when the frontend sends tokens.
    """
    pan = identity.normalize_pan(raw_pan)
    if not pan:
        return None
    return resolve(LEGACY_PAN_ISSUER, pan, pan=pan)


def find_pan(user_id: str) -> Optional[str]:
    """The PAN on a user's profile, if they have set one."""
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT pan FROM profiles WHERE user_id = %s", (user_id,)
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error("[AUTH] profile lookup failed: %s", e)
        return None


def set_pan(user_id: str, raw_pan: str) -> Optional[str]:
    """Attach a PAN to an account. Returns the normalized value, or None if invalid."""
    pan = identity.normalize_pan(raw_pan)
    if not pan:
        return None
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO profiles (user_id, pan) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE
                SET pan = EXCLUDED.pan, updated_at = now()
            """,
            (user_id, pan),
        )
    # The cached Caller carries the old PAN, and it is read as the CAS password
    # default - a stale one silently fails every upload until the TTL expires.
    invalidate(user_id)
    return pan
