"""Google sign-in and the session tokens this API issues afterwards.

Two separate JWTs are involved, and keeping them straight matters:

* Google's **ID token** — signed by Google with RS256, proves who the person is.
  It is verified here against Google's published keys, so the admin panel is
  never trusted to vouch for an identity it claims to have checked.
* Our **access token** — signed by us with HS256, proves an already-verified
  person may act on a given tenant. Short-lived and refreshable.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

ALGORITHM = "HS256"

# Google rotates its signing keys; PyJWKClient caches them and refetches on a
# miss, so this is created once rather than per request.
_jwks_client: PyJWKClient | None = None


class AuthError(Exception):
    """Sign-in failed for a reason the caller is allowed to hear about."""


def _jwks() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """Return the verified claims of a Google ID token.

    Raises ``AuthError`` for anything that makes the token untrustworthy —
    wrong audience, wrong issuer, expired, bad signature, unverified email.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise AuthError("Google sign-in is not configured on this server")

    try:
        signing_key = _jwks().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            # Pinning the audience is what stops an ID token minted for some
            # other Google app from being replayed here.
            audience=settings.GOOGLE_CLIENT_ID,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("That sign-in attempt expired; please try again") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("That sign-in was issued for a different application") from exc
    except jwt.PyJWTError as exc:
        # TEMPORARY: pin down why this only fails in the deployed environment.
        logger.exception("Google ID token verification failed: %r", exc)
        raise AuthError("Could not verify that Google sign-in") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("That token was not issued by Google")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise AuthError("Google did not return an email address")
    # Without this check, a Google Workspace account could in principle present
    # an address it has not proven it owns.
    if not claims.get("email_verified"):
        raise AuthError("That Google account has no verified email address")

    claims["email"] = email
    return claims


# --- Our own access tokens --------------------------------------------------


def _secret() -> str:
    if not settings.JWT_SECRET:
        raise AuthError("Sign-in is not configured on this server")
    return settings.JWT_SECRET


def issue_access_token(
    *,
    user_id: uuid.UUID,
    email: str,
    is_super: bool,
    tenant_id: uuid.UUID | None,
    tenant_slug: str | None,
    session_started: dt.datetime | None = None,
) -> tuple[str, dt.datetime]:
    """Mint a short-lived token and return it with its expiry.

    ``session_started`` carries forward across refreshes so a session cannot be
    extended indefinitely one refresh at a time.
    """
    now = dt.datetime.now(tz=dt.UTC)
    started = session_started or now
    expires = min(
        now + dt.timedelta(minutes=settings.JWT_TTL_MINUTES),
        started + dt.timedelta(hours=settings.SESSION_MAX_HOURS),
    )

    payload = {
        "sub": str(user_id),
        "email": email,
        "sup": is_super,
        "tid": str(tenant_id) if tenant_id else None,
        "tsl": tenant_slug,
        "sst": int(started.timestamp()),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), expires


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your session has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid session token") from exc


def session_started_at(claims: dt.datetime | dict[str, Any]) -> dt.datetime | None:
    if isinstance(claims, dt.datetime):
        return claims
    started = claims.get("sst")
    return dt.datetime.fromtimestamp(started, tz=dt.UTC) if started else None
