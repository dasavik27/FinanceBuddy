from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared import db, identity, session_stores, users

import logging
logger = logging.getLogger(__name__)


router = APIRouter()


class ProfileRequest(BaseModel):
    pan: str


class AccessRequestPayload(BaseModel):
    name: str
    email: str
    investor_type: Optional[str] = "individual"
    notes: Optional[str] = ""


@router.get("/me")
def whoami():
    """The current account. The frontend uses this to decide if a session is live."""
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return {
        "user_id": caller.user_id,
        "pan": caller.pan,
        "status": caller.status,
        "role": caller.role,
    }


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
    Clears the caller's own resident sessions across every domain.

    Stored data is untouched - this only drops the in-memory cache, which is
    rehydrated from the database on next access. All three domains are named because
    signing out and leaving a portfolio resident defeats the point of signing out on a
    shared machine; this used to evict tax sessions only.
    """
    caller = identity.current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    # Every domain holding resident state, without naming any of them: they register
    # themselves at import. See shared/session_stores.py.
    evicted = session_stores.evict_user(caller.user_id)
    logger.info(
        "[AUTH] signed out %s; evicted %d resident session(s)",
        caller.user_id, evicted,
    )
    return {"status": "success"}


@router.post("/request-access")
def submit_access_request(req: AccessRequestPayload):
    """
    Public endpoint for prospective users to request early access / invitation.
    Stores the request in access_requests table for admin provisioning.
    """
    email = req.email.strip().lower()
    name = req.name.strip()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")

    investor_type = (req.investor_type or "individual").strip()
    notes = (req.notes or "").strip()

    try:
        with db.connect() as conn:
            # Check if there is already an existing pending or approved request
            row = conn.execute(
                "SELECT id, status FROM access_requests WHERE LOWER(email) = %s ORDER BY created_at DESC LIMIT 1",
                (email,),
            ).fetchone()
            if row:
                existing_status = row[1]
                return {
                    "status": "already_submitted",
                    "message": f"Your request is already on file (status: {existing_status}). We will notify you once approved.",
                    "request_id": str(row[0]),
                }

            request_id = conn.execute(
                """
                INSERT INTO access_requests (email, name, investor_type, notes, status)
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING id
                """,
                (email, name, investor_type, notes),
            ).fetchone()[0]

            logger.info("[AUTH] access request submitted: %s (%s)", email, name)
            return {
                "status": "success",
                "message": "Thank you! Your access request has been submitted. Our team will review and send an invitation email.",
                "request_id": str(request_id),
            }
    except Exception as e:
        logger.exception("[AUTH] failed to store access request: %s", e)
        raise HTTPException(status_code=500, detail="Unable to submit access request at this time. Please try again later.")


class ApproveAccessRequestPayload(BaseModel):
    method: str = "invite"  # "invite" or "create"
    password: Optional[str] = None


def _provision_in_supabase(email: str, name: str, method: str = "invite", password: Optional[str] = None):
    import json
    import os
    import urllib.error
    import urllib.request
    from dotenv import load_dotenv

    load_dotenv(override=True)

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_role_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_SERVICE_KEY", "")
    ).strip()

    if not supabase_url or not service_role_key:
        return False, "SUPABASE_SERVICE_ROLE_KEY is missing in backend/.env. User was not created in Supabase."

    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }

    try:
        if method == "create" and password:
            endpoint = f"{supabase_url}/auth/v1/admin/users"
            payload = {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"name": name},
            }
        else:
            endpoint = f"{supabase_url}/auth/v1/invite"
            payload = {
                "email": email,
                "data": {"name": name},
            }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            logger.info("[AUTH] Supabase provision successful for %s: %s", email, resp_body[:100])
            return True, f"User {email} successfully provisioned in Supabase!"
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_msg)
            err_msg = parsed.get("msg") or parsed.get("message") or parsed.get("error_description") or err_msg
        except Exception:
            pass
        logger.error("[AUTH] Supabase provision HTTP %d: %s", e.code, err_msg)
        hint = " Tip: Use 'Set Password' to provision without relying on email SMTP." if method == "invite" else ""
        return False, f"Supabase Error ({e.code}): {err_msg}.{hint}"
    except Exception as e:
        logger.exception("[AUTH] Supabase provision exception: %s", e)
        return False, f"Failed to connect to Supabase: {str(e)}"


@router.get("/provisioning-status")
def get_provisioning_status():
    """
    Check if the server has the necessary credentials configured to provision Supabase users.
    """
    import os
    from dotenv import load_dotenv

    load_dotenv(override=True)
    has_url = bool(os.getenv("SUPABASE_URL", "").strip())
    has_service_key = bool(
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    )
    return {
        "supabase_url_configured": has_url,
        "service_role_key_configured": has_service_key,
        "can_auto_provision": has_url and has_service_key,
    }


def _assert_admin(caller) -> None:
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if getattr(caller, "role", None) == "admin":
        return

    import os
    from dotenv import load_dotenv
    load_dotenv(override=True)

    admin_env = (os.getenv("FINANCEBUDDY_ADMIN_EMAILS") or os.getenv("ADMIN_EMAILS") or "").strip()
    if not admin_env:
        return  # Default open to all authenticated users if whitelist not configured

    admin_emails = {e.strip().lower() for e in admin_env.split(",") if e.strip()}
    with db.connect() as conn:
        row = conn.execute(
            "SELECT email FROM identities WHERE user_id = %s",
            (caller.user_id,),
        ).fetchone()
        user_email = (row[0] or "").strip().lower() if row else ""
        if user_email not in admin_emails:
            raise HTTPException(status_code=403, detail="Forbidden. Only authorized administrators can access this console.")


@router.get("/access-requests")
def list_access_requests():
    """
    Administrative overview of submitted access requests.
    Requires signed-in caller with admin access.
    """
    caller = identity.current_caller()
    _assert_admin(caller)

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, email, name, investor_type, notes, status, created_at, reviewed_at
            FROM access_requests
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()

    return {
        "requests": [
            {
                "id": str(r[0]),
                "email": r[1],
                "name": r[2],
                "investor_type": r[3],
                "notes": r[4],
                "status": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "reviewed_at": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
    }


@router.post("/access-requests/{request_id}/approve")
def approve_access_request(request_id: str, req: ApproveAccessRequestPayload):
    """
    Approve an access request and provision the account in Supabase.
    """
    caller = identity.current_caller()
    _assert_admin(caller)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM access_requests WHERE id = %s",
            (request_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Access request not found.")

        req_id, email, name = row

        # Provision in Supabase if configured
        provisioned, prov_msg = _provision_in_supabase(
            email=email,
            name=name,
            method=req.method,
            password=req.password,
        )

        conn.execute(
            "UPDATE access_requests SET status = 'approved', reviewed_at = now() WHERE id = %s",
            (req_id,),
        )

    users.activate_by_email(email)

    logger.info("[AUTH] access request %s (%s) approved by admin %s (provisioned=%s)", req_id, email, caller.user_id, provisioned)
    return {
        "status": "success" if provisioned else "warning",
        "message": prov_msg,
        "supabase_provisioned": provisioned,
    }


@router.post("/access-requests/{request_id}/reject")
@router.delete("/access-requests/{request_id}")
def reject_access_request(request_id: str):
    """
    Reject and permanently remove an access request from the database.
    """
    caller = identity.current_caller()
    _assert_admin(caller)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, email FROM access_requests WHERE id = %s",
            (request_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Access request not found.")

        req_id, email = row

        conn.execute(
            "DELETE FROM access_requests WHERE id = %s",
            (req_id,),
        )

    logger.info("[AUTH] access request %s (%s) rejected and deleted by admin %s", req_id, email, caller.user_id)
    return {"status": "success", "message": f"Access request for {email} rejected and removed from database."}



