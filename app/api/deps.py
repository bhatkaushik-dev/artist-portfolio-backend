"""Shared FastAPI dependencies."""

from __future__ import annotations

import ipaddress
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth as auth_core
from app.core.config import settings
from app.db.session import get_session
from app.models.tenant import Tenant

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Distinct scheme_names keep these as two separate entries in the OpenAPI
# schema; without them FastAPI names both after the class and the second
# silently overwrites the first, so /docs would prompt for the wrong header.
_site_key_header = APIKeyHeader(
    name="X-Site-Key",
    scheme_name="SiteKey",
    auto_error=False,
    description="Public per-tenant key identifying whose content to read",
)
_admin_key_header = APIKeyHeader(
    name="X-Admin-Key",
    scheme_name="AdminKey",
    auto_error=False,
    description="Per-tenant write secret, or the super-admin key on /tenants",
)
_tenant_slug_header = APIKeyHeader(
    name="X-Tenant-Slug",
    scheme_name="TenantSlug",
    auto_error=False,
    description="Target tenant, required only when writing with the super-admin key",
)
# Issued by POST /api/auth/google after a verified Google sign-in. This is what
# the admin panel uses; the API keys above remain for scripts and integrations.
_bearer = HTTPBearer(
    scheme_name="SessionToken",
    auto_error=False,
    description="Session token from /api/auth/google",
)

BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "X-Admin-Key"},
    )


async def _active_tenant_by(session: AsyncSession, column, value: str) -> Tenant | None:
    return await session.scalar(
        select(Tenant).where(column == value, Tenant.is_active.is_(True))
    )


def _bearer_claims(credentials: HTTPAuthorizationCredentials | None) -> dict | None:
    """Decode a session token if one was presented, else None."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return auth_core.decode_access_token(credentials.credentials)
    except auth_core.AuthError as exc:
        raise _unauthorized(str(exc)) from exc


async def _tenant_from_claims(
    session: AsyncSession, claims: dict, tenant_slug: str | None
) -> Tenant:
    """Resolve which artist a signed-in person is acting on.

    A super admin says so explicitly; anyone else is pinned to the tenant their
    token was issued for, so the slug header cannot move them.
    """
    if claims.get("sup"):
        if not tenant_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Acting as a super admin requires an X-Tenant-Slug header "
                    "naming the tenant to act on"
                ),
            )
        tenant = await _active_tenant_by(session, Tenant.slug, tenant_slug)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active tenant with slug {tenant_slug!r}",
            )
        return tenant

    tenant_id = claims.get("tid")
    if not tenant_id:
        raise _unauthorized("This account is not linked to an artist")

    tenant = await session.scalar(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active.is_(True))
    )
    if tenant is None:
        raise _unauthorized("That artist is no longer active")
    return tenant


async def resolve_tenant(
    session: SessionDep,
    site_key: Annotated[str | None, Depends(_site_key_header)] = None,
    credentials: BearerDep = None,
    tenant_slug: Annotated[str | None, Depends(_tenant_slug_header)] = None,
) -> Tenant:
    """Identify whose content a read is for.

    Two ways in. A public site sends its site key, which is not a secret — it
    ships in the frontend bundle — so it only selects a tenant. The admin panel
    sends a session token instead, which also says who the reader is.
    """
    claims = _bearer_claims(credentials)
    if claims is not None:
        return await _tenant_from_claims(session, claims, tenant_slug)

    if not site_key:
        raise _unauthorized("Missing X-Site-Key header")

    tenant = await _active_tenant_by(session, Tenant.site_key, site_key)
    if tenant is None:
        raise _unauthorized("Unknown or inactive site key")
    return tenant


async def require_tenant_admin(
    session: SessionDep,
    api_key: Annotated[str | None, Depends(_admin_key_header)] = None,
    tenant_slug: Annotated[str | None, Depends(_tenant_slug_header)] = None,
    credentials: BearerDep = None,
) -> Tenant:
    """Authenticate a write *and* resolve the tenant it applies to.

    A signed-in person presents a session token. Scripts and integrations
    present an API key instead: for an artist's own key the header does both
    jobs, so that key is structurally incapable of touching another tenant's
    rows — there is no separate tenant selector to disagree with it.

    The super-admin key is the one exception: it may name any tenant through
    ``X-Tenant-Slug``. That grants it nothing new, because
    ``POST /tenants/{id}/rotate-keys`` already lets it mint any artist's admin
    key on demand. It only removes the need to destroy the artist's working
    credential just to make one edit on their behalf.
    """
    claims = _bearer_claims(credentials)
    if claims is not None:
        return await _tenant_from_claims(session, claims, tenant_slug)

    if not api_key:
        raise _unauthorized("Missing credentials")

    if secrets.compare_digest(api_key, settings.SUPER_ADMIN_KEY):
        if not tenant_slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Writing with the super-admin key requires an X-Tenant-Slug "
                    "header naming the tenant to act on"
                ),
            )
        tenant = await _active_tenant_by(session, Tenant.slug, tenant_slug)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active tenant with slug {tenant_slug!r}",
            )
        return tenant

    tenant = await _active_tenant_by(session, Tenant.admin_key, api_key)
    if tenant is None:
        raise _unauthorized("Invalid or missing admin credentials")
    return tenant


async def require_super_admin(
    api_key: Annotated[str | None, Depends(_admin_key_header)] = None,
    credentials: BearerDep = None,
) -> None:
    """Gate tenant management behind a super admin — signed in, or the env key."""
    claims = _bearer_claims(credentials)
    if claims is not None:
        if not claims.get("sup"):
            raise _unauthorized("This account cannot manage artists")
        return

    if not api_key or not secrets.compare_digest(api_key, settings.SUPER_ADMIN_KEY):
        raise _unauthorized("Invalid or missing super-admin credentials")


TenantDep = Annotated[Tenant, Depends(resolve_tenant)]
TenantAdminDep = Annotated[Tenant, Depends(require_tenant_admin)]
SuperAdminDep = Depends(require_super_admin)


def client_ip(request: Request) -> str | None:
    """Best-effort originating IP, validated before it reaches an INET column.

    Behind a proxy (Render, Fly, Vercel, Cloudflare) ``request.client.host`` is
    the load balancer, so the left-most ``X-Forwarded-For`` entry is preferred.
    Headers are attacker-controlled, so anything unparseable is dropped rather
    than handed to Postgres.
    """
    candidates: list[str] = []

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidates.extend(part.strip() for part in forwarded.split(","))
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        candidates.append(real_ip.strip())
    if request.client:
        candidates.append(request.client.host)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None
