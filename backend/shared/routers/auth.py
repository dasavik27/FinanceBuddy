from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared import identity, users

import logging
logger = logging.getLogger(__name__)


router = APIRouter()


class ProfileRequest(BaseModel):
    pan: str


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

    Sign-in is by Google token; a PAN is not identity here, it is profile data the
    user supplies afterwards because the CAS PDF password default and AIS matching
    still want one.
    """
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    pan = users.set_pan(caller.user_id, req.pan)
    if not pan:
        raise HTTPException(status_code=400, detail="Invalid PAN format.")
    return {"status": "success", "pan": pan}


@router.post("/logout")
def logout_user():
    """
    Clears the caller's own resident tax sessions.

    Stored data is untouched - this only drops the in-memory cache, which is
    rehydrated from the database on next access.
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
