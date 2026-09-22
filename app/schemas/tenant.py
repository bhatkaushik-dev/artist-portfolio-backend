"""Tenant management payloads. Only the super-admin ever sees these."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel, StrictModel

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"


class TenantCreate(StrictModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(
        None,
        pattern=SLUG_PATTERN,
        description="Defaults to a slugified name. Also the media path prefix.",
    )


class TenantUpdate(StrictModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None


class TenantRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    site_key: str
    is_active: bool
    created_at: datetime


class TenantCredentials(TenantRead):
    """Returned only on create and rotate — the admin key is never re-shown."""

    admin_key: str
