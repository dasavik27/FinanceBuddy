import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import main
from shared.oidc import OidcJwtVerifier
from shared import users

ISSUER = "https://example-test-issuer.invalid/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-exp"


@pytest.fixture(scope="module")
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


class _StubJwks:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": self._public_key})()


def _mint_jwt(private_key, *, sub="user-123", email="user@example.test", exp_offset=3600):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": sub,
        "email": email,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def _find_identity_middleware(app):
    curr = app.middleware_stack
    while curr is not None:
        if isinstance(curr, main.IdentityMiddleware):
            return curr
        curr = getattr(curr, "app", None)
    return None


@pytest.fixture
def client_with_verifier(rsa_keypair):
    private_key, public_key = rsa_keypair
    verifier = OidcJwtVerifier(
        jwks_url="https://example.invalid/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        jwk_client=_StubJwks(public_key),
    )
    client = TestClient(main.app)
    # Trigger middleware stack initialization
    client.get("/health")
    mw = _find_identity_middleware(main.app)
    if mw is not None:
        old_verifier = mw._verifier
        mw._verifier = verifier
        yield client, private_key, verifier, mw
        mw._verifier = old_verifier
    else:
        yield client, private_key, verifier, None


def test_missing_token_returns_401(client_with_verifier):
    client, _, _, _ = client_with_verifier
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not signed in."}


def test_expired_token_returns_401_without_access_request_banner(client_with_verifier):
    """
    Expired JWT: Verifier returns None -> IdentityMiddleware treats request as anonymous.
    Route returns 401 Unauthorized. It does NOT return 403 or "not_authorized" access message.
    """
    client, private_key, _, _ = client_with_verifier
    
    # Token expired 10 minutes ago
    expired_token = _mint_jwt(private_key, exp_offset=-600)
    
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not signed in."}
    
    # Assert that 401 response contains NO access request fields
    assert "not_authorized" not in str(resp.json())
    assert "access_request_status" not in resp.json()


def test_invalid_malformed_token_returns_401(client_with_verifier):
    client, _, _, _ = client_with_verifier
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not signed in."}


def test_unapproved_user_raises_not_authorized_403(client_with_verifier, monkeypatch):
    """
    When token is valid but the account is not allowlisted/approved,
    users.resolve raises NotAuthorizedError, and IdentityMiddleware returns 403 Forbidden
    with detail='not_authorized' and access_request_status.
    """
    client, private_key, _, _ = client_with_verifier
    
    def _deny_resolve(issuer, subject, email=None, name=None):
        raise users.NotAuthorizedError(
            "Access required. You do not have access yet. Raise a request, or check status with the email you already submitted.",
            access_request_status="none",
        )
    
    monkeypatch.setattr(users, "resolve", _deny_resolve)
    
    valid_token = _mint_jwt(private_key, sub="unapproved-user", email="stranger@example.test", exp_offset=3600)
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
    
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"] == "not_authorized"
    assert data["access_request_status"] == "none"
    assert "raise a request" in data["message"].lower() or "access required" in data["message"].lower()
