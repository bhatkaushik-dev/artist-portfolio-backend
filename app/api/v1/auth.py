"""``/api/auth`` — turning a Google identity into a session token.

The admin panel never tells this API who someone is; it forwards the ID token
Google gave it and this module verifies that signature itself. An allowlist in
the ``users`` table then decides whether that verified person may sign in.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import BearerDep, SessionDep
from app.core import auth as auth_core
from app.core.config import settings
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import GoogleSignIn, SessionToken

router = APIRouter(prefix="/auth", tags=["auth"])


def _rejected(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _build_session(
    session: SessionDep, user: User, started: dt.datetime | None
) -> SessionToken:
    tenant: Tenant | None = None
    if user.tenant_id:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.id == user.tenant_id, Tenant.is_active.is_(True))
        )
        if tenant is None:
            raise _rejected(
                "The artist linked to this account is no longer active. "
                "Ask your administrator to re-enable it."
            )

    token, expires = auth_core.issue_access_token(
        user_id=user.id,
        email=user.email,
        is_super=user.is_super,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug if tenant else None,
        session_started=started,
    )
    return SessionToken(
        access_token=token,
        expires_at=expires,
        user=user,
        tenant=tenant,
    )


@router.post(
    "/google",
    response_model=SessionToken,
    summary="Exchange a verified Google identity for a session token",
)
async def sign_in_with_google(
    payload: GoogleSignIn, session: SessionDep
) -> SessionToken:
    if not settings.google_signin_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this server",
        )

    try:
        claims = auth_core.verify_google_id_token(payload.id_token)
    except auth_core.AuthError as exc:
        raise _rejected(str(exc)) from exc

    email = claims["email"]
    user = await session.scalar(select(User).where(User.email == email))

    # Same message whether the address is unknown or disabled: a sign-in page
    # should not report which addresses have accounts.
    if user is None or not user.is_active:
        raise _rejected(
            f"{email} is not allowed to sign in. Ask your administrator for access."
        )

    # Keep the profile fresh; these are only ever used for display.
    user.name = claims.get("name") or user.name
    user.picture_url = claims.get("picture") or user.picture_url
    user.last_login_at = dt.datetime.now(tz=dt.UTC)

    result = await _build_session(session, user, started=None)
    await session.commit()
    return result


@router.post(
    "/refresh",
    response_model=SessionToken,
    summary="Extend a session that has not yet expired",
)
async def refresh(session: SessionDep, credentials: BearerDep = None) -> SessionToken:
    """Issue a fresh token from a still-valid one.

    An expired token is not accepted — that would make this an unlimited
    re-issuance oracle. ``SESSION_MAX_HOURS`` additionally caps how long a
    session can be extended for, however often it is refreshed.
    """
    if credentials is None or not credentials.credentials:
        raise _rejected("No session token supplied")

    try:
        claims = auth_core.decode_access_token(credentials.credentials)
    except auth_core.AuthError as exc:
        raise _rejected(str(exc)) from exc

    user = await session.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise _rejected("This account can no longer sign in")

    started = auth_core.session_started_at(claims)
    if started and started + dt.timedelta(hours=settings.SESSION_MAX_HOURS) <= dt.datetime.now(
        tz=dt.UTC
    ):
        raise _rejected("Your session has reached its maximum length; please sign in again")

    result = await _build_session(session, user, started=started)
    await session.commit()
    return result
