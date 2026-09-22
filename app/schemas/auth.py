"""Sign-in payloads."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import ORMModel, StrictModel


class GoogleSignIn(StrictModel):
    id_token: str = Field(..., description="The ID token from Google's OAuth response")


class SignedInUser(ORMModel):
    id: uuid.UUID
    email: EmailStr
    name: str | None = None
    picture_url: str | None = None
    is_super: bool
    tenant_id: uuid.UUID | None = None


class TenantSummary(BaseModel):
    """Just enough for the panel to render a header and scope its calls."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    site_key: str


class SessionToken(BaseModel):
    access_token: str
    expires_at: dt.datetime
    user: SignedInUser
    # Absent for a super admin, who is not bound to one artist.
    tenant: TenantSummary | None = None
