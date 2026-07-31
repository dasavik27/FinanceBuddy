from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from shared import identity, users

import logging
logger = logging.getLogger(__name__)


router = APIRouter()


class LoginRequest(BaseModel):
    pan: str


class ProfileRequest(BaseModel):
    pan: str


@router.post("/login")
def login_with_pan(req: LoginRequest):
    """
    Legacy PAN sign-in.

    This is identification, not authentication: a PAN is printed on documents and
    the request carries no proof of possession. It survives the Postgres cutover
    only so that changing the database and changing how people sign in remain two
    separately reversible steps. Once the frontend sends OIDC tokens, delete this
    route along with users.resolve_legacy_pan and the middleware's PAN branch.

    It no longer writes the `users` table directly. Resolution goes through the same
    path a token takes, so a PAN login and a Google login produce the same account
    shape and the same owner id.
    """
    pan = identity.normalize_pan(req.pan)
    if not pan:
        raise HTTPException(
            status_code=400,
            detail="Invalid PAN format. Must be 10 characters (e.g. ABCDE1234F).",
        )

    caller = users.resolve_legacy_pan(pan)
    if caller is None:
        # resolve() fails closed, so this is a database problem rather than a
        # credential one - 503 so the client retries instead of re-prompting.
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable.")

    logger.info("[AUTH] signed in %s", identity.mask_pan(pan))
    return {"status": "success", "pan": pan, "user_id": caller.user_id}


@router.get("/me")
def whoami():
    """The current account. The frontend uses this to decide if a session is live."""
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return {"user_id": caller.user_id, "pan": caller.pan}


@router.put("/profile/pan")
def set_profile_pan(req: ProfileRequest):
    """
    Attach a PAN to the signed-in account.

    Needed once sign-in is by token rather than by PAN: the CAS password default and
    AIS matching still want one, but it is now profile data the user supplies after
    signing in, not the thing that identifies them.
    """
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    pan = users.set_pan(caller.user_id, req.pan)
    if not pan:
        raise HTTPException(status_code=400, detail="Invalid PAN format.")
    return {"status": "success", "pan": pan}


@router.post("/logout")
def logout_user(req: Optional[LoginRequest] = None):
    """
    Clears the caller's own resident tax sessions.

    The account is taken from the request identity, never from the body. Reading it
    from `req.pan` made this an unauthenticated destructive endpoint: anyone could
    POST someone else's PAN and wipe their tax sessions from memory and disk.

    The body is still accepted and ignored so a client sending the old shape does not
    get a 422 instead of a logout.
    """
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    from domains.tax_expert.tax_sessions import evict_for_user

    evicted = evict_for_user(caller.user_id)
    logger.info(
        "[AUTH] signed out %s; evicted %d resident tax session(s)",
        caller.user_id, evicted,
    )
    return {"status": "success"}
