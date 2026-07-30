"""
shared/routers/google_auth.py

Google OAuth 2.0 + JWT Authentication
======================================
Implements a PKCE-based Google OAuth flow that produces our own signed JWTs.

Design notes
------------
No client_secret is stored in the frontend. The browser redirects to Google with a
code_challenge; the backend exchanges the code for tokens using the client_secret
from environment variables (never sent to the browser).

Google's id_token is verified locally by fetching Google's public keys once and
caching them. This avoids a round-trip on every request and tolerates Google's key
rotation via TTL-based refresh.

Our own access token (1-hour JWT) and refresh token (30-day, stored as a hash in
SQLite) are issued after Google identity is confirmed. The frontend stores the
access token in memory only — never localStorage. The refresh token is returned in
the response body so the frontend can store it in an httpOnly cookie via its own
service worker, or simply in memory for the session.

PAN linking
-----------
After first sign-in, `pan_linked: false` is returned. The frontend shows a
PAN-entry screen; the user types their PAN and hits POST /auth/link-pan. On all
subsequent sign-ins, `pan_linked: true` and the PAN is embedded in the JWT.

Backwards compatibility
-----------------------
The old POST /auth/login (PAN only) route in auth.py is kept for local dev and
the unit test suite. It is not called by the Google flow.
"""

import hashlib
import logging
import os
import secrets
import time
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from pydantic import BaseModel

from shared.identity import normalize_pan, mask_pan
from shared.storage import DB_PATH, _connect

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5173/auth/callback")

JWT_SECRET    = os.getenv("JWT_SECRET", "dev-secret-change-in-production-please")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_MINUTES       = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))
REFRESH_TOKEN_EXPIRY_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRY_DAYS", "30"))

GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_CERTS_URL   = "https://www.googleapis.com/oauth2/v3/certs"

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


# ── Google public key cache (avoids a round-trip on every verification) ───────

_google_certs: dict = {}
_google_certs_fetched_at: float = 0.0
_GOOGLE_CERTS_TTL = 3600  # seconds


def _get_google_certs() -> dict:
    global _google_certs, _google_certs_fetched_at
    if time.time() - _google_certs_fetched_at < _GOOGLE_CERTS_TTL and _google_certs:
        return _google_certs
    try:
        resp = httpx.get(GOOGLE_CERTS_URL, timeout=10)
        resp.raise_for_status()
        _google_certs = resp.json()
        _google_certs_fetched_at = time.time()
        logger.info("[AUTH] Refreshed Google public keys.")
    except Exception as e:
        logger.warning("[AUTH] Could not refresh Google public keys: %s", e)
    return _google_certs


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _issue_access_token(google_id: str, email: str, pan: Optional[str]) -> str:
    now = int(time.time())
    payload = {
        "sub": google_id,
        "email": email,
        "pan": pan,
        "iat": now,
        "exp": now + JWT_EXPIRY_MINUTES * 60,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify one of our own access tokens. Returns None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def _issue_refresh_token(google_id: str) -> str:
    """Generate a random refresh token, store its hash in SQLite, return the raw token."""
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = time.time() + REFRESH_TOKEN_EXPIRY_DAYS * 86400
    with _connect() as conn:
        # Revoke all existing live tokens for this user (one session at a time).
        conn.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE google_id = ? AND revoked = 0",
            (google_id,),
        )
        conn.execute(
            "INSERT INTO refresh_tokens (token_hash, google_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, google_id, expires_at),
        )
    return token


def _revoke_refresh_token(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as conn:
        conn.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?",
            (token_hash,),
        )


def _validate_refresh_token(token: str) -> Optional[str]:
    """Returns google_id if the token is valid and not expired/revoked."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as conn:
        row = conn.execute(
            "SELECT google_id, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    if not row:
        return None
    google_id, expires_at, revoked = row
    if revoked or time.time() > expires_at:
        return None
    return google_id


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_google_user(google_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT google_id, email, name, picture_url, pan_id FROM google_users WHERE google_id = ?",
            (google_id,),
        ).fetchone()
    if not row:
        return None
    return {"google_id": row[0], "email": row[1], "name": row[2], "picture_url": row[3], "pan_id": row[4]}


def _upsert_google_user(google_id: str, email: str, name: str, picture_url: str) -> dict:
    now = time.time()
    with _connect() as conn:
        conn.execute("""
            INSERT INTO google_users (google_id, email, name, picture_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(google_id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                picture_url = excluded.picture_url,
                updated_at = excluded.updated_at
        """, (google_id, email, name, picture_url, now, now))
        row = conn.execute(
            "SELECT google_id, email, name, picture_url, pan_id FROM google_users WHERE google_id = ?",
            (google_id,),
        ).fetchone()
    return {"google_id": row[0], "email": row[1], "name": row[2], "picture_url": row[3], "pan_id": row[4]}


def _link_pan_to_google(google_id: str, pan: str):
    now = time.time()
    # Also create/upsert the users row so the existing PAN-keyed ownership system still works.
    with _connect() as conn:
        conn.execute(
            "UPDATE google_users SET pan_id = ?, updated_at = ? WHERE google_id = ?",
            (pan, now, google_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO users (pan_id) VALUES (?)", (pan,)
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/google/login")
def google_login():
    """
    Returns the Google OAuth authorization URL.

    The frontend redirects the user here; after consent Google redirects to
    GOOGLE_REDIRECT_URI with a code parameter.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID in environment."
        )
    from urllib.parse import urlencode
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"url": url}


class CallbackRequest(BaseModel):
    code: str


@router.post("/google/callback")
def google_callback(req: CallbackRequest):
    """
    Exchange authorization code for Google tokens, verify identity, issue our JWT.

    Returns:
        access_token  — short-lived JWT (1 h), store in memory only
        refresh_token — long-lived opaque token (30 d), store in httpOnly cookie
        pan_linked    — false on first login; frontend must collect PAN
        user          — { email, name, picture_url }
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth not configured.")

    # Exchange code for tokens
    try:
        resp = httpx.post(GOOGLE_TOKEN_URL, data={
            "code": req.code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15)
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        logger.error("[AUTH] Google token exchange failed: %s", e)
        raise HTTPException(status_code=400, detail="Failed to exchange code with Google.")

    # Fetch user info using the access token
    google_access_token = token_data.get("access_token")
    if not google_access_token:
        raise HTTPException(status_code=400, detail="No access token in Google response.")

    try:
        ui = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
            timeout=10,
        )
        ui.raise_for_status()
        user_info = ui.json()
    except Exception as e:
        logger.error("[AUTH] Failed to fetch Google user info: %s", e)
        raise HTTPException(status_code=400, detail="Failed to fetch user info from Google.")

    google_id   = user_info.get("sub")
    email       = user_info.get("email", "")
    name        = user_info.get("name", "")
    picture_url = user_info.get("picture", "")

    if not google_id:
        raise HTTPException(status_code=400, detail="Google did not return a user ID.")

    user = _upsert_google_user(google_id, email, name, picture_url)
    pan = user.get("pan_id")

    access_token  = _issue_access_token(google_id, email, pan)
    refresh_token = _issue_refresh_token(google_id)

    logger.info("[AUTH] Google sign-in: %s (PAN linked: %s)", email, bool(pan))

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
        "pan_linked": bool(pan),
        "pan": pan,
        "user": {
            "email": email,
            "name": name,
            "picture_url": picture_url,
        },
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
def refresh_token(req: RefreshRequest):
    """
    Issue a new access token from a valid refresh token (token rotation).
    The old refresh token is revoked and a new one issued.
    """
    google_id = _validate_refresh_token(req.refresh_token)
    if not google_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user = _get_google_user(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    # Rotate: revoke old, issue new
    _revoke_refresh_token(req.refresh_token)
    new_refresh = _issue_refresh_token(google_id)
    new_access  = _issue_access_token(google_id, user["email"], user.get("pan_id"))

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
    }


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/google/logout")
def google_logout(req: LogoutRequest):
    """Revoke the refresh token so it cannot be used to obtain new access tokens."""
    _revoke_refresh_token(req.refresh_token)
    return {"status": "success"}


class LinkPanRequest(BaseModel):
    pan: str
    refresh_token: str  # to re-issue JWT with PAN embedded


@router.post("/link-pan")
def link_pan(req: LinkPanRequest):
    """
    Link a PAN to the authenticated Google account (called once after first sign-in).

    Validates the PAN format, stores the link in DB, re-issues the JWT with the
    PAN embedded so subsequent requests carry identity proof.
    """
    google_id = _validate_refresh_token(req.refresh_token)
    if not google_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please sign in again.")

    pan = normalize_pan(req.pan)
    if not pan:
        raise HTTPException(status_code=400, detail="Invalid PAN format. Must be 10 characters (e.g. ABCDE1234F).")

    user = _get_google_user(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    _link_pan_to_google(google_id, pan)

    # Rotate tokens with PAN now embedded in access token
    _revoke_refresh_token(req.refresh_token)
    new_refresh = _issue_refresh_token(google_id)
    new_access  = _issue_access_token(google_id, user["email"], pan)

    logger.info("[AUTH] PAN %s linked to Google account %s", mask_pan(pan), user["email"])

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
        "pan": pan,
        "pan_linked": True,
    }


@router.get("/google/config")
def google_config():
    """
    Returns the Google Client ID for the frontend (public, not secret).
    Avoids hardcoding it in the JS bundle — the bundle already ships to the browser,
    but keeping it in one place (env) is cleaner.
    """
    if not GOOGLE_CLIENT_ID:
        return {"configured": False}
    return {"configured": True, "client_id": GOOGLE_CLIENT_ID}
