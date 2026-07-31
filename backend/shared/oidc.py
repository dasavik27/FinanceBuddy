"""
shared/oidc.py - verify an OpenID Connect ID token and reduce it to a Principal.

Provider independence
---------------------
This speaks OIDC, not a vendor. A provider is three pieces of configuration - a
JWKS URL, an expected issuer, an expected audience - so Supabase, Google, Auth0,
Cognito and Entra are the same code path with different environment variables. No
vendor SDK is imported, and nothing downstream learns which provider signed the
token: it sees a Principal.

`issuer` is carried into the Principal because it is half of the identity key.
`identities` is keyed on (issuer, subject), so subjects from two providers cannot
collide, and adding a provider later is an INSERT rather than a migration.

Cost per request
----------------
Signature verification is local: an asymmetric verify is tens of microseconds, and
the signing keys are fetched once and cached for their lifespan. Calling the
provider's userinfo endpoint per request instead would add a network round trip to
every authenticated call, which on a single-worker instance is the difference
between a fast API and a proxy for someone else's.

Security notes, each of which is a real attack if omitted
---------------------------------------------------------
- Algorithms are pinned. Accepting whatever the token's header asks for allows
  algorithm confusion: a token signed HS256 using the *public* RSA key as the HMAC
  secret verifies, and the public key is published in the JWKS.
- `aud` is required and checked. Without it, a token the same issuer minted for a
  different application is accepted here.
- `iss` is required and checked, so a token from an unrelated issuer whose key
  happens to be fetchable cannot be replayed.
- `exp` is required. PyJWT will not enforce an expiry claim that is absent unless
  told to.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

# Asymmetric only. Symmetric algorithms are excluded by construction rather than by
# configuration - see the algorithm-confusion note above.
DEFAULT_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384")

# Tolerance for clock skew between this host and the provider, in seconds.
DEFAULT_LEEWAY = 60


@dataclass(frozen=True)
class Principal:
    """Who the caller is, according to a verified token."""

    issuer: str
    subject: str
    email: Optional[str] = None

    @property
    def identity_key(self) -> tuple:
        """The (issuer, subject) pair that keys the `identities` table."""
        return (self.issuer, self.subject)


class AuthVerifier(Protocol):
    """Turns a bearer token into a Principal, or None if it is not valid."""

    def verify(self, token: str) -> Optional[Principal]:
        ...


class OidcJwtVerifier:
    """Verifies an ID token against a provider's published JWKS."""

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str,
        algorithms: Sequence[str] = DEFAULT_ALGORITHMS,
        leeway: int = DEFAULT_LEEWAY,
        jwk_client=None,
        cache_lifespan: int = 3600,
    ):
        if not jwks_url:
            raise ValueError("jwks_url is required")
        if not issuer:
            raise ValueError("issuer is required")
        if not audience:
            raise ValueError("audience is required")

        self.issuer = issuer
        self.audience = audience
        self.algorithms = list(algorithms)
        self.leeway = leeway
        # Injectable so tests can supply a locally-generated key without a network
        # round trip or a live provider.
        self._jwks = jwk_client or PyJWKClient(
            jwks_url, cache_keys=True, lifespan=cache_lifespan
        )

    def verify(self, token: str) -> Optional[Principal]:
        """
        The Principal for a valid token, or None.

        Returns None rather than raising for every rejection reason, so a caller
        cannot accidentally distinguish "expired" from "wrong signature" from
        "malformed" and turn that into an oracle. The reason is logged, not
        returned.
        """
        if not token:
            return None

        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
        except Exception as e:
            # Unknown kid, unreachable JWKS, malformed header.
            logger.warning("[AUTH] could not resolve signing key: %s", e)
            return None

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway,
                options={
                    "require": ["exp", "iss", "aud", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
        except jwt.PyJWTError as e:
            logger.info("[AUTH] token rejected: %s", type(e).__name__)
            return None

        subject = claims.get("sub")
        if not subject:
            return None

        return Principal(
            issuer=claims.get("iss", self.issuer),
            subject=str(subject),
            email=claims.get("email"),
        )


def from_env(env: Optional[dict] = None) -> Optional[OidcJwtVerifier]:
    """
    Build the verifier from configuration, or None when auth is not configured.

    Reads generic names first so the provider is a deployment detail. The
    SUPABASE_* fallbacks exist only so an existing .env keeps working; nothing in
    the code path below cares which provider answered.
    """
    import os

    env = env if env is not None else os.environ

    jwks_url = env.get("AUTH_JWKS_URL") or env.get("SUPABASE_JWKS_URL") or ""
    issuer = env.get("AUTH_ISSUER") or ""
    audience = env.get("AUTH_AUDIENCE") or ""

    # Supabase publishes its JWKS at <project>/auth/v1/.well-known/jwks.json, issues
    # tokens as <project>/auth/v1, and uses the audience "authenticated". Derived
    # rather than required so the common case needs one variable, not three.
    supabase_url = (env.get("SUPABASE_URL") or "").rstrip("/")
    if supabase_url:
        issuer = issuer or f"{supabase_url}/auth/v1"
        audience = audience or "authenticated"
        jwks_url = jwks_url or f"{supabase_url}/auth/v1/.well-known/jwks.json"

    if not (jwks_url and issuer and audience):
        logger.warning(
            "[AUTH] no identity provider configured "
            "(set AUTH_JWKS_URL, AUTH_ISSUER, AUTH_AUDIENCE)"
        )
        return None

    return OidcJwtVerifier(jwks_url=jwks_url, issuer=issuer, audience=audience)
