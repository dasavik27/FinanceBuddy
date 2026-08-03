"""
OIDC token verification.

These mint real tokens with a locally-generated RSA key and verify them through the
real code path - no mocking of jwt.decode - so the assertions are about actual
cryptographic verification rather than about a stub agreeing with itself.

Every rejection case here is a live attack if the check is missing. They are written
to fail loudly, because a verifier that accepts too much fails open.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from shared.oidc import OidcJwtVerifier, Principal, from_env, Hs256JwtVerifier, CompositeAuthVerifier

ISSUER = "https://example-project.supabase.co/auth/v1"
AUDIENCE = "authenticated"
KID = "test-key-1"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


class _StubJwks:
    """Stands in for PyJWKClient, returning a fixed local key."""

    def __init__(self, public_key, kid=KID):
        self._public_key = public_key
        self._kid = kid

    def get_signing_key_from_jwt(self, token):
        header = jwt.get_unverified_header(token)
        if header.get("kid") != self._kid:
            raise jwt.PyJWKClientError(f"unknown kid {header.get('kid')!r}")
        return type("Key", (), {"key": self._public_key})()


@pytest.fixture
def verifier(keypair):
    _, public_key = keypair
    return OidcJwtVerifier(
        jwks_url="https://example.invalid/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        jwk_client=_StubJwks(public_key),
    )


def _token(private_key, *, alg="RS256", kid=KID, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-abc-123",
        "email": "someone@example.com",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    for key in [k for k, v in claims.items() if v is None]:
        del claims[key]
    return jwt.encode(claims, private_key, algorithm=alg, headers={"kid": kid})


# ── the happy path ────────────────────────────────────────────────────────────

def test_valid_token_yields_a_principal(verifier, keypair):
    private_key, _ = keypair
    principal = verifier.verify(_token(private_key))

    assert principal == Principal(
        issuer=ISSUER, subject="user-abc-123", email="someone@example.com"
    )
    # (issuer, subject) is what keys the identities table.
    assert principal.identity_key == (ISSUER, "user-abc-123")


def test_email_is_optional(verifier, keypair):
    private_key, _ = keypair
    principal = verifier.verify(_token(private_key, email=None))
    assert principal is not None
    assert principal.email is None


def test_name_claim_extracted_from_google_or_metadata(verifier, keypair):
    private_key, _ = keypair
    # Standard Google OIDC token claim
    principal = verifier.verify(_token(private_key, name="Avik Das"))
    assert principal is not None
    assert principal.name == "Avik Das"

    # Supabase user_metadata claim
    principal_meta = verifier.verify(_token(private_key, user_metadata={"full_name": "Sarah Connor"}))
    assert principal_meta is not None
    assert principal_meta.name == "Sarah Connor"


# ── rejections, each of which is an attack ────────────────────────────────────

def test_rejects_a_token_signed_by_someone_else(verifier):
    """The whole point: an attacker-minted token must not verify."""
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert verifier.verify(_token(attacker_key)) is None


def test_rejects_algorithm_confusion_via_hs256(verifier, keypair):
    """
    An RSA public key is published in the JWKS, so anyone can read it. If the
    verifier honoured the token's own `alg`, an attacker could sign HS256 using that
    public key as the HMAC secret and it would verify against the same bytes.
    Pinning to asymmetric algorithms is what prevents it.

    The token is assembled by hand rather than with jwt.encode, which refuses to use
    a PEM key as an HMAC secret. That refusal protects a careless *signer*; it does
    nothing for us, because the attacker is not using our library. Building the
    token manually is what the real attack looks like.
    """
    import base64
    import hashlib
    import hmac
    import json

    from cryptography.hazmat.primitives import serialization

    public_pem = keypair[1].public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = b64(json.dumps({
        "iss": ISSUER, "aud": AUDIENCE, "sub": "attacker",
        "exp": int(time.time()) + 3600,
    }).encode())
    signing_input = header + b"." + payload
    signature = b64(hmac.new(public_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + signature).decode()

    assert jwt.get_unverified_header(forged)["alg"] == "HS256"
    assert verifier.verify(forged) is None

    # Worth recording what actually rejects this, because it is not only our pin:
    # PyJWT refuses a PEM key as an HMAC secret on *decode* as well as encode, so a
    # verifier that wrongly allowed HS256 would still fail here. The allow-list is
    # defence in depth against that behaviour changing, and is what rejects the
    # `alg: none` case below - which nothing else stops.
    permissive = OidcJwtVerifier(
        jwks_url="https://example.invalid/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["HS256"],
        jwk_client=_StubJwks(public_pem),
    )
    assert permissive.verify(forged) is None


def test_rejects_an_unsigned_token(verifier, keypair):
    """
    `alg: none` with an empty signature is the oldest JWT attack there is. Nothing
    but the algorithm allow-list rejects it - the claims are perfectly well-formed.
    """
    import base64
    import json

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode())
    payload = b64(json.dumps({
        "iss": ISSUER, "aud": AUDIENCE, "sub": "attacker",
        "exp": int(time.time()) + 3600,
    }).encode())
    unsigned = (header + b"." + payload + b".").decode()

    assert jwt.get_unverified_header(unsigned)["alg"] == "none"
    assert verifier.verify(unsigned) is None


def test_rejects_an_expired_token(verifier, keypair):
    private_key, _ = keypair
    past = int(time.time()) - 7200
    assert verifier.verify(_token(private_key, iat=past, exp=past + 60)) is None


def test_rejects_a_token_with_no_expiry(verifier, keypair):
    """PyJWT does not enforce an absent claim unless it is in `require`."""
    private_key, _ = keypair
    assert verifier.verify(_token(private_key, exp=None)) is None


def test_rejects_another_applications_audience(verifier, keypair):
    """A token the same issuer minted for a different app is not ours."""
    private_key, _ = keypair
    assert verifier.verify(_token(private_key, aud="some-other-app")) is None


def test_rejects_a_foreign_issuer(verifier, keypair):
    private_key, _ = keypair
    assert verifier.verify(_token(private_key, iss="https://evil.example/auth")) is None


def test_rejects_an_unknown_signing_key(verifier, keypair):
    private_key, _ = keypair
    assert verifier.verify(_token(private_key, kid="some-other-kid")) is None


def test_rejects_a_token_with_no_subject(verifier, keypair):
    private_key, _ = keypair
    assert verifier.verify(_token(private_key, sub=None)) is None


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c", "..", None])
def test_rejects_malformed_input(verifier, garbage):
    assert verifier.verify(garbage) is None


def test_clock_skew_is_tolerated(verifier, keypair):
    """A token that expired two seconds ago is a clock difference, not an attack."""
    private_key, _ = keypair
    now = int(time.time())
    assert verifier.verify(_token(private_key, iat=now - 60, exp=now - 2)) is not None


# ── configuration ─────────────────────────────────────────────────────────────

def test_config_requires_all_three_parameters():
    for kwargs in (
        {"jwks_url": "", "issuer": ISSUER, "audience": AUDIENCE},
        {"jwks_url": "https://x/jwks", "issuer": "", "audience": AUDIENCE},
        {"jwks_url": "https://x/jwks", "issuer": ISSUER, "audience": ""},
    ):
        with pytest.raises(ValueError):
            OidcJwtVerifier(**kwargs)


def test_from_env_derives_supabase_defaults_from_one_variable():
    built = from_env({"SUPABASE_URL": "https://abcxyz.supabase.co"})
    assert built is not None
    assert built.issuer == "https://abcxyz.supabase.co/auth/v1"
    assert built.audience == "authenticated"


def test_from_env_prefers_generic_names_over_provider_ones():
    """The provider must be swappable without touching code."""
    built = from_env({
        "SUPABASE_URL": "https://abcxyz.supabase.co",
        "AUTH_ISSUER": "https://accounts.google.com",
        "AUTH_AUDIENCE": "my-google-client-id.apps.googleusercontent.com",
        "AUTH_JWKS_URL": "https://www.googleapis.com/oauth2/v3/certs",
    })
    assert built is not None
    assert built.issuer == "https://accounts.google.com"
    assert built.audience == "my-google-client-id.apps.googleusercontent.com"


def test_from_env_returns_none_when_unconfigured():
    assert from_env({}) is None


def test_hs256_legacy_supabase_token(verifier, keypair):
    secret = "super-secret-test-jwt-key"
    hs256 = Hs256JwtVerifier(secret, ISSUER, AUDIENCE)
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "legacy-admin-1",
            "email": "admin@example.com",
            "iat": now,
            "exp": now + 3600,
        },
        secret,
        algorithm="HS256",
    )
    principal = hs256.verify(token)
    assert principal == Principal(
        issuer=ISSUER, subject="legacy-admin-1", email="admin@example.com"
    )


def test_composite_prefers_hs256_for_legacy_tokens(keypair):
    secret = "super-secret-test-jwt-key"
    _, public_key = keypair
    jwks = OidcJwtVerifier(
        jwks_url="https://example.invalid/jwks.json",
        issuer=ISSUER,
        audience=AUDIENCE,
        jwk_client=_StubJwks(public_key),
    )
    hs256 = Hs256JwtVerifier(secret, ISSUER, AUDIENCE)
    composite = CompositeAuthVerifier(jwks, hs256)
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "legacy-admin-2",
            "email": "admin@example.com",
            "iat": now,
            "exp": now + 3600,
        },
        secret,
        algorithm="HS256",
    )
    principal = composite.verify(token)
    assert principal is not None
    assert principal.subject == "legacy-admin-2"


def test_from_env_builds_composite_when_jwt_secret_set():
    built = from_env({
        "SUPABASE_URL": "https://abcxyz.supabase.co",
        "SUPABASE_JWT_SECRET": "legacy-secret",
    })
    assert isinstance(built, CompositeAuthVerifier)
    assert built.issuer == "https://abcxyz.supabase.co/auth/v1"
