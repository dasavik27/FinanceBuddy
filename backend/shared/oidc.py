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
    name: Optional[str] = None

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
            alg = jwt.get_unverified_header(token).get("alg")
        except jwt.PyJWTError:
            alg = None
        if alg == "HS256":
            logger.warning(
                "[AUTH] received HS256 token but verifier is JWKS-only — "
                "set SUPABASE_JWT_SECRET on the backend (Supabase JWT Secret)"
            )
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
            logger.warning(
                "[AUTH] JWKS token rejected reason=%s expected_iss=%s expected_aud=%s",
                type(e).__name__, self.issuer, self.audience,
            )
            return None

        subject = claims.get("sub")
        if not subject:
            logger.warning("[AUTH] JWKS token missing sub claim")
            return None

        return _principal_from_claims(claims, self.issuer)


def _principal_from_claims(claims: dict, default_issuer: str) -> Optional[Principal]:
    subject = claims.get("sub")
    if not subject:
        return None

    raw_meta = claims.get("user_metadata")
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    extracted_name = (
        claims.get("name")
        or claims.get("full_name")
        or meta.get("full_name")
        or meta.get("name")
        or meta.get("user_name")
    )
    clean_name = extracted_name.strip() if isinstance(extracted_name, str) and extracted_name.strip() else None

    raw_email = claims.get("email")
    if not raw_email and isinstance(meta, dict):
        meta_email = meta.get("email")
        if isinstance(meta_email, str) and meta_email.strip():
            raw_email = meta_email.strip()
    if not raw_email:
        app_meta = claims.get("app_metadata")
        if isinstance(app_meta, dict):
            app_email = app_meta.get("email")
            if isinstance(app_email, str) and app_email.strip():
                raw_email = app_email.strip()
    if not raw_email and isinstance(claims.get("user_email"), str):
        raw_email = claims.get("user_email").strip()

    return Principal(
        issuer=claims.get("iss", default_issuer),
        subject=str(subject),
        email=raw_email if isinstance(raw_email, str) and raw_email.strip() else None,
        name=clean_name,
    )


class Hs256JwtVerifier:
    """Verify legacy Supabase tokens signed with the project JWT secret (HS256)."""

    def __init__(
        self,
        secret: str,
        issuer: str,
        audience: str,
        leeway: int = DEFAULT_LEEWAY,
    ):
        if not secret:
            raise ValueError("secret is required")
        if not issuer:
            raise ValueError("issuer is required")
        if not audience:
            raise ValueError("audience is required")
        self.issuer = issuer
        self.audience = audience
        self.leeway = leeway
        self._secret = secret

    def verify(self, token: str) -> Optional[Principal]:
        if not token:
            return None
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
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
            logger.warning(
                "[AUTH] HS256 token rejected reason=%s expected_iss=%s expected_aud=%s "
                "(check SUPABASE_JWT_SECRET matches Supabase JWT Secret)",
                type(e).__name__, self.issuer, self.audience,
            )
            return None
        return _principal_from_claims(claims, self.issuer)


class CompositeAuthVerifier:
    """Try JWKS (asymmetric) first, then legacy HS256 when configured."""

    def __init__(
        self,
        jwks: Optional[OidcJwtVerifier],
        hs256: Optional[Hs256JwtVerifier],
    ):
        if jwks is None and hs256 is None:
            raise ValueError("at least one verifier is required")
        self._jwks = jwks
        self._hs256 = hs256
        ref = jwks or hs256
        self.issuer = ref.issuer
        self.audience = ref.audience

    def verify(self, token: str) -> Optional[Principal]:
        if not token:
            return None
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            kid = header.get("kid")
        except jwt.PyJWTError as e:
            logger.warning("[AUTH] malformed JWT header: %s", type(e).__name__)
            return None

        if alg == "HS256":
            if self._hs256 is None:
                logger.warning(
                    "[AUTH] token alg=HS256 but SUPABASE_JWT_SECRET not set — "
                    "cannot verify legacy Supabase JWT; set secret or rotate to asymmetric keys"
                )
                return None
            principal = self._hs256.verify(token)
            if principal is None:
                logger.warning("[AUTH] HS256 verify failed alg=%s kid=%s", alg, kid)
            return principal

        if self._jwks is not None:
            principal = self._jwks.verify(token)
            if principal is None:
                logger.warning("[AUTH] JWKS verify failed alg=%s kid=%s", alg, kid)
            return principal

        logger.warning("[AUTH] no verifier for token alg=%s kid=%s", alg, kid)
        return None


def from_env(env: Optional[dict] = None) -> Optional[AuthVerifier]:
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

    jwt_secret = (
        env.get("SUPABASE_JWT_SECRET")
        or env.get("JWT_SECRET")
        or ""
    ).strip()

    jwks_verifier = OidcJwtVerifier(jwks_url=jwks_url, issuer=issuer, audience=audience)
    hs256_verifier = Hs256JwtVerifier(jwt_secret, issuer, audience) if jwt_secret else None

    if hs256_verifier is not None:
        logger.info(
            "[AUTH] JWT verification ready mode=jwks+hs256 issuer=%s audience=%s jwks=%s",
            issuer, audience, jwks_url,
        )
        return CompositeAuthVerifier(jwks_verifier, hs256_verifier)

    logger.info(
        "[AUTH] JWT verification ready mode=jwks-only issuer=%s audience=%s jwks=%s "
        "(set SUPABASE_JWT_SECRET if tokens are still HS256)",
        issuer, audience, jwks_url,
    )
    return jwks_verifier
