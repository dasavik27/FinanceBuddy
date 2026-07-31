from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import sqlite3
import re
from shared import identity
from shared.identity import mask_pan
from shared.storage import DB_PATH
import logging
logger = logging.getLogger(__name__)


router = APIRouter()

class LoginRequest(BaseModel):
    pan: str

@router.post("/login")
def login_with_pan(req: LoginRequest):
    pan = req.pan.strip().upper()
    
    # Basic PAN validation (5 letters, 4 numbers, 1 letter)
    # Some users might have slightly different PANs, but this is standard.
    if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan):
        raise HTTPException(status_code=400, detail="Invalid PAN format. Must be 10 characters (e.g. ABCDE1234F).")
        
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT pan_id FROM users WHERE pan_id = ?", (pan,))
        user = cursor.fetchone()

        if not user:
            conn.execute("INSERT INTO users (pan_id) VALUES (?)", (pan,))
            conn.commit()
            # NOTE: there used to be a migration here that claimed every orphaned
            # session (pan_id IS NULL) for the first user created, so existing
            # uploads survived the introduction of PANs. It has been removed.
            #
            # On an ephemeral filesystem the `users` table resets on every restart,
            # so "the first user" recurred on each deploy - and the next person to
            # log in inherited a stranger's uploads and could read them through
            # /history. It was an upgrade shim for a database that no longer
            # survives restarts.
            logger.info(f"[AUTH] New user profile created for PAN: {mask_pan(pan)}")
        else:
            logger.info(f"[AUTH] Existing user logged in: {mask_pan(pan)}")

    return {"status": "success", "pan": pan}

@router.post("/logout")
def logout_user(req: Optional[LoginRequest] = None):
    """
    Clears the caller's own tax sessions.

    The PAN comes from the request-scoped identity, never from the body. Reading it
    from `req.pan` made this an unauthenticated destructive endpoint: anyone could
    POST {"pan": "<someone else's PAN>"} and wipe that user's tax sessions from
    memory and disk. `delete_tax_session` performs no ownership check of its own,
    so the request body was the only thing deciding whose data was destroyed.

    The body is still accepted and ignored so that a client sending the old shape
    does not get a 422 instead of a logout.
    """
    pan = identity.current_pan()
    if not pan:
        raise HTTPException(status_code=401, detail="Authentication required.")

    from domains.tax_expert.tax_sessions import get_sessions_by_pan, delete_tax_session
    # get_sessions_by_pan is already scoped to this PAN, so every id it returns is
    # one the caller owns.
    sessions = get_sessions_by_pan(pan)
    for s in sessions:
        delete_tax_session(s["session_id"])
    logger.info(
        f"[AUTH] Logged out {mask_pan(pan)} and cleared {len(sessions)} "
        "tax sessions from memory and disk."
    )
    return {"status": "success"}
