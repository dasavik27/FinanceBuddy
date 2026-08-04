"""
shared/users.py - resolve a credential to an account.

`users.id` is issued here and belongs to this application. A provider's idea of who
someone is lives in `identities` as an (issuer, subject) pair pointing at that id.

That indirection is the whole point. Switching identity provider, or adding a second
one, is an INSERT into `identities` - no table is re-keyed, and no user loses their
data. Storing the provider's subject directly as the owner column would make the
provider impossible to leave, which is the single most expensive kind of coupling to
undo later.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import Optional, Tuple

from shared import crypto, db, identity
from shared.identity import Caller

logger = logging.getLogger(__name__)


class NotAuthorizedError(Exception):
    """Raised when a valid IdP token belongs to an email that is not allowlisted."""

    def __init__(
        self,
        message: str = "not_authorized",
        access_request_status: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = "not_authorized"
        self.access_request_status = access_request_status or "none"


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


def _admin_emails() -> set:
    import os
    from dotenv import load_dotenv

    load_dotenv(override=True)
    admin_env = (os.getenv("FINANCEBUDDY_ADMIN_EMAILS") or os.getenv("ADMIN_EMAILS") or "").strip()
    return {e.strip().lower() for e in admin_env.split(",") if e.strip()}


def _open_provision() -> bool:
    """Test-only escape hatch so DB fixtures can create accounts without access_requests."""
    import os
    from dotenv import load_dotenv

    load_dotenv(override=True)
    return (os.getenv("FINANCEBUDDY_OPEN_PROVISION") or "").strip().lower() in (
        "1", "true", "yes",
    )


def _has_approved_access(conn, email: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM access_requests WHERE LOWER(email) = %s AND status = 'approved' LIMIT 1",
        (email.strip().lower(),),
    ).fetchone()
    return row is not None


def _has_pending_access(conn, email: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM access_requests WHERE LOWER(email) = %s AND status = 'pending' LIMIT 1",
        (email.strip().lower(),),
    ).fetchone()
    return row is not None


def _identity_email(conn, issuer: str, subject: str) -> Optional[str]:
    row = conn.execute(
        "SELECT email FROM identities WHERE issuer = %s AND subject = %s",
        (issuer, subject),
    ).fetchone()
    if row and row[0] and str(row[0]).strip():
        return str(row[0]).strip().lower()
    return None


def _email_from_supabase(subject: str) -> Optional[str]:
    """Resolve email from Supabase Auth when the access token omits the claim (common with Google)."""
    import json
    import os
    import urllib.error
    import urllib.request

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_role_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_SERVICE_KEY", "")
    ).strip()
    if not supabase_url or not service_role_key or not subject:
        return None

    try:
        req = urllib.request.Request(
            f"{supabase_url}/auth/v1/admin/users/{subject}",
            headers={
                "Authorization": f"Bearer {service_role_key}",
                "apikey": service_role_key,
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, dict):
            nested = data.get("user")
            if isinstance(nested, dict):
                email = (nested.get("email") or "").strip().lower()
            else:
                email = (data.get("email") or "").strip().lower()
        else:
            email = ""
        if email:
            logger.info("[AUTH] resolved email from Supabase admin for subject=%s", subject)
            return email
        logger.warning("[AUTH] Supabase admin user %s has no email in response", subject)
        return None
    except Exception as exc:
        logger.warning("[AUTH] Supabase admin user lookup failed for %s: %s", subject, exc)
        return None


def _resolve_email(
    conn,
    issuer: str,
    subject: str,
    email: Optional[str],
) -> Optional[str]:
    """Best email for allowlist checks: JWT claim, identities row, then Supabase admin."""
    if email and str(email).strip():
        return str(email).strip().lower()
    stored = _identity_email(conn, issuer, subject)
    if stored:
        return stored
    return _email_from_supabase(subject)


def lookup_access_request_status(conn, email: Optional[str]) -> Optional[str]:
    """Latest access_requests.status for this email, or None if no row."""
    if not email:
        return None
    row = conn.execute(
        """
        SELECT status FROM access_requests
        WHERE LOWER(email) = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (email.strip().lower(),),
    ).fetchone()
    return row[0] if row else None


def message_for_access_status(status: Optional[str]) -> str:
    """User-facing copy keyed off access_requests.status."""
    if status == "pending":
        return (
            "Request pending. Your access request is waiting for admin approval. "
            "You will get an invite once it is approved."
        )
    if status == "approved":
        return (
            "Password not set yet. Your access is approved. "
            "Open the invite email, create your password, then sign in here."
        )
    return (
        "Access required. You do not have access yet. "
        "Raise a request, or check status with the email you already submitted."
    )


def _provision_deny_reason(conn, email: Optional[str]) -> str:
    """Short reason for logs when first-time provisioning is denied."""
    if _open_provision():
        return "open_provision_enabled"  # should not deny
    if not email:
        return "no_email_on_token_or_supabase"
    email_lower = email.strip().lower()
    admins = _admin_emails()
    if not admins:
        admin_note = "FINANCEBUDDY_ADMIN_EMAILS_empty"
    elif email_lower in admins:
        return "is_admin_email"  # should not deny
    else:
        admin_note = "not_in_FINANCEBUDDY_ADMIN_EMAILS"
    req = lookup_access_request_status(conn, email_lower)
    if req == "approved":
        return "has_approved_access"  # should not deny
    if req == "pending":
        return "has_pending_access"  # should not deny
    if req:
        return f"access_request_status={req};{admin_note}"
    return f"no_access_request;{admin_note}"


def _may_provision(conn, email: Optional[str]) -> bool:
    """True when a brand-new identity is allowed to create an app account."""
    if _open_provision():
        return True
    if not email:
        return False
    email_lower = email.strip().lower()
    if email_lower in _admin_emails():
        return True
    # Approved → full access; pending request → create a pending account so they
    # see the wait screen after Google / email verification instead of "raise request".
    return _has_approved_access(conn, email_lower) or _has_pending_access(conn, email_lower)


def _initial_account_flags(conn, email: Optional[str]) -> tuple:
    """(status, role) for a newly provisioned account. Call only after _may_provision."""
    role = "user"
    status = "pending"
    if not email:
        return status, role
    email_lower = email.strip().lower()
    if email_lower in _admin_emails():
        return "active", "admin"
    if _has_approved_access(conn, email_lower):
        return "active", role
    if _has_pending_access(conn, email_lower):
        return "pending", role
    # Open-provision / legacy test path: create as pending until approved.
    return status, role


def _sync_account_flags(conn, user_id, email: Optional[str]) -> tuple:
    """
    Load status/role and promote accounts when access has been approved or the
    caller is an configured administrator.
    Returns (status, role).
    """
    row = conn.execute(
        "SELECT status, role FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    if not row:
        return "pending", "user"
    status, role = row[0], row[1]
    # Suspended is sticky until an admin explicitly reactivates (not implemented here).
    if status == "suspended" or not email:
        return status, role

    email_lower = email.strip().lower()
    new_status, new_role = status, role
    if email_lower in _admin_emails():
        new_status, new_role = "active", "admin"
    elif status == "pending" and _has_approved_access(conn, email_lower):
        new_status = "active"

    if new_status != status or new_role != role:
        conn.execute(
            "UPDATE users SET status = %s, role = %s WHERE id = %s",
            (new_status, new_role, user_id),
        )
        invalidate(str(user_id))
        return new_status, new_role
    return status, role


def activate_by_email(email: str) -> None:
    """Promote a pending account to active when an access request is approved."""
    email_lower = email.strip().lower()
    if not email_lower:
        return
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id FROM users u
            JOIN identities i ON i.user_id = u.id
            WHERE LOWER(i.email) = %s AND u.status = 'pending'
            """,
            (email_lower,),
        ).fetchall()
        for (user_id,) in rows:
            conn.execute(
                "UPDATE users SET status = 'active' WHERE id = %s", (user_id,)
            )
            invalidate(str(user_id))


def suspend_by_email(email: str) -> Optional[str]:
    """
    Set status=suspended for every account linked to this email.
    Returns the first user_id suspended, or None if none matched.
    """
    email_lower = (email or "").strip().lower()
    if not email_lower:
        return None
    suspended_id = None
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT u.id FROM users u
            JOIN identities i ON i.user_id = u.id
            WHERE LOWER(i.email) = %s
            """,
            (email_lower,),
        ).fetchall()
        for (user_id,) in rows:
            conn.execute(
                "UPDATE users SET status = 'suspended' WHERE id = %s", (user_id,)
            )
            invalidate(str(user_id))
            if suspended_id is None:
                suspended_id = str(user_id)
    return suspended_id


def list_accounts(limit: int = 100) -> list:
    """Admin roster: app users with primary email, status, and role."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.status, u.role, u.created_at, u.last_seen_at,
                   (
                     SELECT i.email FROM identities i
                     WHERE i.user_id = u.id AND i.email IS NOT NULL
                     ORDER BY i.created_at ASC
                     LIMIT 1
                   ) AS email
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "user_id": str(r[0]),
            "status": r[1],
            "role": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
            "last_seen_at": r[4].isoformat() if r[4] else None,
            "email": r[5],
        }
        for r in rows
    ]


def update_account(
    user_id: str,
    status: Optional[str] = None,
    role: Optional[str] = None,
) -> Optional[dict]:
    """Update account status and/or role. Returns updated row summary or None."""
    allowed_status = {"pending", "active", "suspended"}
    allowed_role = {"user", "admin"}
    if status is not None and status not in allowed_status:
        return None
    if role is not None and role not in allowed_role:
        return None
    if status is None and role is None:
        return None

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, status, role FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if not row:
            return None
        new_status = status if status is not None else row[1]
        new_role = role if role is not None else row[2]
        conn.execute(
            "UPDATE users SET status = %s, role = %s WHERE id = %s",
            (new_status, new_role, user_id),
        )
        email_row = conn.execute(
            """
            SELECT email FROM identities
            WHERE user_id = %s AND email IS NOT NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    invalidate(user_id)
    return {
        "user_id": str(user_id),
        "status": new_status,
        "role": new_role,
        "email": email_row[0] if email_row else None,
    }


def resolve(issuer: str, subject: str, email: Optional[str] = None,
            pan: Optional[str] = None,
            name: Optional[str] = None) -> Optional[Caller]:
    """
    The account for (issuer, subject), creating it on first sight only when the
    email is allowlisted (admin list or approved access request).

    Unapproved first-time sign-ins raise NotAuthorizedError so the middleware can
    return 403 without inserting a pending account.

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

            effective_email = _resolve_email(conn, issuer, subject, email)

            if row is None:
                if not _may_provision(conn, effective_email):
                    deny_reason = _provision_deny_reason(conn, effective_email)
                    req_status = lookup_access_request_status(conn, effective_email)
                    logger.warning(
                        "[AUTH] denied provisioning reason=%s issuer=%s subject=%s "
                        "email=%s access_request_status=%s admin_emails_configured=%s",
                        deny_reason, issuer, subject, effective_email or "<none>",
                        req_status or "none", bool(_admin_emails()),
                    )
                    raise NotAuthorizedError(
                        message_for_access_status(req_status),
                        access_request_status=req_status or "none",
                    )
                status, role = _initial_account_flags(conn, effective_email)
                provision_why = _provision_deny_reason(conn, effective_email)
                # _provision_deny_reason returns allow reasons too (is_admin_email, etc.)
                user_id = conn.execute(
                    "INSERT INTO users (status, role) VALUES (%s, %s) RETURNING id",
                    (status, role),
                ).fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO identities (issuer, subject, user_id, email)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (issuer, subject) DO NOTHING
                    """,
                    (issuer, subject, user_id, effective_email),
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
                logger.info(
                    "[AUTH] provisioned account why=%s email=%s user_id=%s status=%s role=%s",
                    provision_why, effective_email or "<none>", user_id, status, role,
                )
            else:
                user_id = row[0]
                conn.execute(
                    "UPDATE users SET last_seen_at = now() WHERE id = %s", (user_id,)
                )
                if email:
                    conn.execute(
                        """
                        UPDATE identities SET email = COALESCE(email, %s)
                        WHERE issuer = %s AND subject = %s
                        """,
                        (email, issuer, subject),
                    )
                elif effective_email:
                    conn.execute(
                        """
                        UPDATE identities SET email = COALESCE(email, %s)
                        WHERE issuer = %s AND subject = %s
                        """,
                        (effective_email, issuer, subject),
                    )

            status, role = _sync_account_flags(conn, user_id, effective_email)

            # PAN comes from the profile, not from the caller, so a request cannot
            # assert someone else's. The legacy path passes one in only because it
            # *is* the credential there, and it is written to the profile below.
            profile = conn.execute(
                "SELECT pan_encrypted FROM profiles WHERE user_id = %s", (user_id,)
            ).fetchone()
            # Bound to the user id, so a PAN ciphertext copied into another account's
            # profile row fails to decrypt rather than being served as theirs.
            stored_pan = _decrypt_pan(profile[0], user_id) if profile else None

            if pan and pan != stored_pan:
                conn.execute(
                    """
                    INSERT INTO profiles (user_id, pan_encrypted) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                        SET pan_encrypted = EXCLUDED.pan_encrypted, updated_at = now()
                    """,
                    (user_id, crypto.encrypt_text(pan, aad=str(user_id))),
                )
                stored_pan = pan

            if name and isinstance(name, str) and name.strip():
                clean_name = name.strip()
                conn.execute(
                    """
                    INSERT INTO profiles (user_id, display_name) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                        SET display_name = COALESCE(profiles.display_name, EXCLUDED.display_name),
                            updated_at = now()
                    """,
                    (user_id, clean_name),
                )

        caller = Caller(user_id=str(user_id), pan=stored_pan, status=status, role=role)
        _cache_put(key, caller)
        return caller
    except NotAuthorizedError:
        raise
    except Exception as e:
        # Fail closed. Returning None makes the request anonymous, which owns_record
        # denies against any owned row - never accidentally authorized.
        logger.error("[AUTH] could not resolve identity for issuer=%s: %s", issuer, e)
        return None


def _decrypt_pan(blob, user_id) -> Optional[str]:
    """
    Decrypt a stored PAN, degrading to None rather than failing the request.

    A PAN that will not decrypt costs the CAS-password autofill - the upload form
    asks for a password instead. That is a far better outcome than 500-ing every
    authenticated request, which is what raising here would do: this runs inside
    identity resolution, on the path of every single call.
    """
    if blob is None:
        return None
    try:
        return crypto.decrypt_text(blob, aad=str(user_id))
    except crypto.DecryptionFailed:
        logger.exception("[AUTH] cannot decrypt stored PAN for user %s", user_id)
        return None


def find_pan(user_id: str) -> Optional[str]:
    """The PAN on a user's profile, if they have set one."""
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT pan_encrypted FROM profiles WHERE user_id = %s", (user_id,)
            ).fetchone()
        return _decrypt_pan(row[0], user_id) if row else None
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
            INSERT INTO profiles (user_id, pan_encrypted) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE
                SET pan_encrypted = EXCLUDED.pan_encrypted, updated_at = now()
            """,
            (user_id, crypto.encrypt_text(pan, aad=str(user_id))),
        )
    # The cached Caller carries the old PAN, and it is read as the CAS password
    # default - a stale one silently fails every upload until the TTL expires.
    invalidate(user_id)
    return pan
