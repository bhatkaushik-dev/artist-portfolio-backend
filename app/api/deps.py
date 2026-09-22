"""Shared FastAPI dependencies."""

from __future__ import annotations

import ipaddress
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_admin_key_header = APIKeyHeader(
    name="X-Admin-Key",
    auto_error=False,
    description="Shared admin secret required for every write route",
)


async def require_admin(
    api_key: Annotated[str | None, Depends(_admin_key_header)],
) -> None:
    """Gate all mutating routes behind a shared secret.

    ``compare_digest`` keeps the check constant-time so the key cannot be
    recovered by timing the response.
    """
    if not api_key or not secrets.compare_digest(api_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin credentials",
            headers={"WWW-Authenticate": "X-Admin-Key"},
        )


AdminDep = Depends(require_admin)


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
