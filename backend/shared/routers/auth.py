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


class AccessStatusPayload(BaseModel):
    email: str


@router.post("/access-status")
def check_access_status(req: AccessStatusPayload):
    """
    Public lookup: does this email have an access_requests row, and what status?
    Used on failed email/Google sign-in to show pending vs raise-request messaging.
    """
    email = req.email.strip().lower()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    with db.connect() as conn:
        status = users.lookup_access_request_status(conn, email)

    access_status = status or "none"
    return {
        "email": email,
        "access_request_status": access_status,
        "message": users.message_for_access_status(status),
    }


@router.get("/me")
def whoami():
    """The current account. The frontend uses this to decide if a session is live."""
    caller = identity.current_caller()
    if caller is None:
        logger.warning(
            "[AUTH] GET /auth/me → 401 Not signed in "
            "(no caller — check JWT verify logs, or identity resolve / schema migration errors above)"
        )
        raise HTTPException(status_code=401, detail="Not signed in.")
    logger.info(
        "[AUTH] GET /auth/me → 200 user_id=%s status=%s role=%s pan_set=%s",
        caller.user_id, caller.status, caller.role, bool(caller.pan),
    )
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


def _assert_admin(caller) -> None:
    """Require role=admin or an email on FINANCEBUDDY_ADMIN_EMAILS. Deny by default."""
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    if getattr(caller, "role", None) == "admin":
        return

    import os
    from dotenv import load_dotenv
    load_dotenv(override=True)

    admin_env = (os.getenv("FINANCEBUDDY_ADMIN_EMAILS") or os.getenv("ADMIN_EMAILS") or "").strip()
    admin_emails = {e.strip().lower() for e in admin_env.split(",") if e.strip()}
    if not admin_emails:
        raise HTTPException(
            status_code=403,
            detail="Forbidden. Configure FINANCEBUDDY_ADMIN_EMAILS or sign in with an admin account.",
        )

    with db.connect() as conn:
        row = conn.execute(
            "SELECT email FROM identities WHERE user_id = %s",
            (caller.user_id,),
        ).fetchone()
        user_email = (row[0] or "").strip().lower() if row else ""
        if user_email not in admin_emails:
            raise HTTPException(
                status_code=403,
                detail="Forbidden. Only authorized administrators can access this console.",
            )


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
    Approve an access request and send a Supabase invite email.
    The user sets their own password after opening the invite link.
    """
    caller = identity.current_caller()
    _assert_admin(caller)

    if (req.method or "invite").strip().lower() == "create":
        raise HTTPException(
            status_code=400,
            detail="Admin password provisioning is disabled. Use invite email; the user sets their own password.",
        )

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, email, name FROM access_requests WHERE id = %s",
            (request_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Access request not found.")

        req_id, email, name = row

        # Invite-only: Supabase emails a link; user creates their password in-app.
        provisioned, prov_msg = _provision_in_supabase(
            email=email,
            name=name,
            method="invite",
            password=None,
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


class InviteUserPayload(BaseModel):
    email: str
    name: str
    method: str = "invite"  # "invite" or "create"
    password: Optional[str] = None
    investor_type: Optional[str] = "individual"
    notes: Optional[str] = ""


@router.post("/invites")
def invite_user(req: InviteUserPayload):
    """
    Admin-direct invite: allowlist the email, mark/create an approved access_requests
    row, and provision the Supabase Auth user without a prior public request.
    """
    caller = identity.current_caller()
    _assert_admin(caller)

    email = req.email.strip().lower()
    name = req.name.strip()
    if not email or "@" not in email or "." not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if (req.method or "invite").strip().lower() == "create":
        raise HTTPException(
            status_code=400,
            detail="Admin password provisioning is disabled. Use invite email; the user sets their own password.",
        )

    investor_type = (req.investor_type or "individual").strip()
    notes = (req.notes or "Admin invite").strip()

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, status FROM access_requests WHERE LOWER(email) = %s ORDER BY created_at DESC LIMIT 1",
            (email,),
        ).fetchone()
        if row:
            request_id = row[0]
            conn.execute(
                """
                UPDATE access_requests
                SET status = 'approved', name = %s, investor_type = %s, notes = %s, reviewed_at = now()
                WHERE id = %s
                """,
                (name, investor_type, notes, request_id),
            )
        else:
            request_id = conn.execute(
                """
                INSERT INTO access_requests (email, name, investor_type, notes, status, reviewed_at)
                VALUES (%s, %s, %s, %s, 'approved', now())
                RETURNING id
                """,
                (email, name, investor_type, notes),
            ).fetchone()[0]

    provisioned, prov_msg = _provision_in_supabase(
        email=email,
        name=name,
        method="invite",
        password=None,
    )
    users.activate_by_email(email)

    logger.info(
        "[AUTH] invite for %s by admin %s (request_id=%s provisioned=%s)",
        email, caller.user_id, request_id, provisioned,
    )
    return {
        "status": "success" if provisioned else "warning",
        "message": prov_msg,
        "supabase_provisioned": provisioned,
        "request_id": str(request_id),
        "email": email,
    }


class SuspendUserPayload(BaseModel):
    email: str


def _ban_in_supabase(email: str) -> tuple:
    """Best-effort ban of the Supabase Auth user. Returns (ok, message)."""
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
        return False, "Supabase service role not configured; app account suspended only."

    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    try:
        # Admin list has no reliable email filter across versions; page and match client-side.
        list_url = f"{supabase_url}/auth/v1/admin/users?page=1&per_page=200"
        req = urllib.request.Request(list_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        users_list = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(users_list, list):
            users_list = []
        match = next(
            (u for u in users_list if (u.get("email") or "").strip().lower() == email),
            None,
        )
        if not match:
            return False, "No Supabase Auth user found for that email; app account suspended."
        user_id = match.get("id")
        ban_url = f"{supabase_url}/auth/v1/admin/users/{user_id}"
        ban_body = json.dumps({"ban_duration": "876000h"}).encode("utf-8")
        ban_req = urllib.request.Request(ban_url, data=ban_body, headers=headers, method="PUT")
        with urllib.request.urlopen(ban_req, timeout=10) as resp:
            resp.read()
        return True, f"Suspended app account and banned Supabase user {email}."
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        logger.error("[AUTH] Supabase ban HTTP %d: %s", e.code, err_msg)
        return False, f"App account suspended; Supabase ban failed ({e.code})."
    except Exception as e:
        logger.exception("[AUTH] Supabase ban exception: %s", e)
        return False, f"App account suspended; Supabase ban failed: {e}"


@router.post("/users/suspend")
def suspend_user(req: SuspendUserPayload):
    """Admin: revoke app access for an email (status=suspended) and ban in Supabase if possible."""
    caller = identity.current_caller()
    _assert_admin(caller)

    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    user_id = users.suspend_by_email(email)
    if not user_id:
        raise HTTPException(status_code=404, detail="No app account found for that email.")

    banned, ban_msg = _ban_in_supabase(email)
    logger.info(
        "[AUTH] suspended %s (user_id=%s) by admin %s (supabase_banned=%s)",
        email, user_id, caller.user_id, banned,
    )
    return {
        "status": "success",
        "message": ban_msg,
        "user_id": user_id,
        "email": email,
        "supabase_banned": banned,
    }


class UpdateUserPayload(BaseModel):
    status: Optional[str] = None  # pending | active | suspended
    role: Optional[str] = None    # user | admin


@router.get("/users")
def list_app_users():
    """Admin: list provisioned app accounts with status and role."""
    caller = identity.current_caller()
    _assert_admin(caller)
    return {"users": users.list_accounts()}


@router.patch("/users/{user_id}")
def update_app_user(user_id: str, req: UpdateUserPayload):
    """Admin: activate, suspend, or change role for an app account."""
    caller = identity.current_caller()
    _assert_admin(caller)

    if req.status is None and req.role is None:
        raise HTTPException(status_code=400, detail="Provide status and/or role to update.")

    if str(caller.user_id) == user_id:
        if req.role == "user" or req.status == "suspended":
            raise HTTPException(
                status_code=400,
                detail="You cannot remove your own admin role or suspend your own account.",
            )

    updated = users.update_account(user_id, status=req.status, role=req.role)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found or invalid status/role.")

    logger.info(
        "[AUTH] user %s updated by admin %s (status=%s role=%s)",
        user_id, caller.user_id, updated["status"], updated["role"],
    )
    return {"status": "success", "user": updated}


def _delete_in_supabase(email: str) -> tuple:
    """Best-effort hard-delete of the Supabase Auth user. Returns (ok, message)."""
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
        return False, "Supabase service role not configured; app data deleted only."

    headers = {
        "Authorization": f"Bearer {service_role_key}",
        "apikey": service_role_key,
        "Content-Type": "application/json",
    }
    try:
        list_url = f"{supabase_url}/auth/v1/admin/users?page=1&per_page=200"
        req = urllib.request.Request(list_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        users_list = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(users_list, list):
            users_list = []
        match = next(
            (u for u in users_list if (u.get("email") or "").strip().lower() == email),
            None,
        )
        if not match:
            return False, "No Supabase Auth user found for that email; app data deleted."
        auth_user_id = match.get("id")
        del_url = f"{supabase_url}/auth/v1/admin/users/{auth_user_id}"
        del_req = urllib.request.Request(del_url, headers=headers, method="DELETE")
        with urllib.request.urlopen(del_req, timeout=10) as resp:
            resp.read()
        return True, f"Deleted Supabase Auth user {email}."
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        logger.error("[AUTH] Supabase delete HTTP %d: %s", e.code, err_msg)
        return False, f"App data deleted; Supabase delete failed ({e.code})."
    except Exception as e:
        logger.exception("[AUTH] Supabase delete exception: %s", e)
        return False, f"App data deleted; Supabase delete failed: {e}"


@router.delete("/users/{user_id}")
def delete_app_user(user_id: str):
    """
    Admin: permanently delete an app account and all cascaded data.

    Same purge model as DELETE /accounts/me: evict resident sessions, delete the
    users row (cascades identities/profiles/sessions/payloads/budget prefs), remove
    access_requests for the email, and best-effort delete the Supabase Auth user.
    """
    from shared import storage

    caller = identity.current_caller()
    _assert_admin(caller)

    if str(caller.user_id) == str(user_id):
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account from the Admin Console.",
        )

    account = users.get_account(user_id)
    if not account:
        raise HTTPException(status_code=404, detail="User not found.")

    email = (account.get("email") or "").strip().lower() or None

    # Memory first — same ordering as self-service purge.
    session_stores.evict_user(user_id)
    deleted_sessions = storage.delete_all_for_user(user_id)
    users.invalidate(user_id)
    removed_requests = users.delete_access_requests_for_email(email) if email else 0

    supabase_deleted = False
    supabase_msg = "No email on account; skipped Supabase Auth delete."
    if email:
        supabase_deleted, supabase_msg = _delete_in_supabase(email)

    logger.info(
        "[AUTH] deleted user %s email=%s by admin %s sessions=%s access_requests=%s supabase=%s",
        user_id, email, caller.user_id, deleted_sessions, removed_requests, supabase_deleted,
    )
    return {
        "status": "success",
        "message": (
            f"Permanently deleted account"
            f"{f' for {email}' if email else ''} "
            f"({deleted_sessions} session(s), {removed_requests} access request(s)). "
            f"{supabase_msg}"
        ),
        "user_id": user_id,
        "email": email,
        "deleted_sessions": deleted_sessions,
        "deleted_access_requests": removed_requests,
        "supabase_deleted": supabase_deleted,
    }


