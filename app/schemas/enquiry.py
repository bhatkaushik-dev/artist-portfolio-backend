"""Lead capture schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import EnquiryStatus
from app.schemas.common import ORMModel


class EnquiryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = Field(None, max_length=32)
    subject: str | None = Field(None, max_length=240)
    message: str = Field(..., min_length=1, max_length=5000)
    source: str = Field("contact_page", max_length=64)


class EnquiryCreateResponse(BaseModel):
    """Returned only after the row is committed."""

    id: uuid.UUID
    status: Literal["persisted"] = "persisted"
    whatsapp_url: str = Field(..., description="wa.me deep link with pre-filled text")
    notification_queued: bool = Field(
        ..., description="False when SMTP is not configured; the row is saved regardless"
    )


class EnquiryRead(ORMModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    phone: str | None = None
    subject: str | None = None
    message: str
    source: str
    status: EnquiryStatus

    ip_address: str | None = None
    user_agent: str | None = None
    referer: str | None = None

    notified: bool
    notified_at: datetime | None = None
    admin_notes: str | None = None
    created_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def _stringify_inet(cls, value: object) -> str | None:
        # asyncpg decodes the INET column into an ipaddress object.
        return None if value is None else str(value)


class EnquiryListResponse(BaseModel):
    items: list[EnquiryRead]
    total: int
    limit: int
    offset: int


class EnquiryStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: EnquiryStatus
    admin_notes: str | None = None
