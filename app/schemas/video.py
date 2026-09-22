"""Video schemas (VideoObject JSON-LD source)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.common import OrderField, ORMModel

# YouTube video ids are always 11 chars from a fixed alphabet.
YOUTUBE_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"


class VideoRead(ORMModel):
    id: uuid.UUID
    youtube_id: str
    title: str
    description: str | None = None
    upload_date: datetime | None = None
    duration: str | None = Field(None, description="ISO-8601, e.g. PT12M31S")
    thumbnail_url: str | None = None
    order: int = OrderField()
    featured: bool
    is_active: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_id}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embed_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.youtube_id}"


class VideoCreate(BaseModel):
    """Only the YouTube id is required; the rest is synced or overridden."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    youtube_id: str = Field(..., pattern=YOUTUBE_ID_PATTERN)
    title: str | None = Field(None, max_length=300)
    description: str | None = None
    upload_date: datetime | None = None
    duration: str | None = Field(None, max_length=32)
    thumbnail_url: str | None = Field(None, max_length=512)
    order: int = Field(0, ge=0)
    featured: bool = False
    sync_metadata: bool = Field(
        True,
        description="Fetch title/description/uploadDate from the YouTube Data API "
        "when a key is configured. Explicit fields always win.",
    )


class VideoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(None, max_length=300)
    description: str | None = None
    upload_date: datetime | None = None
    duration: str | None = Field(None, max_length=32)
    thumbnail_url: str | None = Field(None, max_length=512)
    order: int | None = Field(None, ge=0)
    featured: bool | None = None
    is_active: bool | None = None
