"""Consolidated ISR payload and health schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.faq import FAQRead
from app.schemas.page import PageContentRead
from app.schemas.photo import PhotoRead
from app.schemas.site import SiteProfileRead
from app.schemas.video import VideoRead


class BootstrapResponse(BaseModel):
    """Everything the Next.js build/ISR pass needs, in one round trip.

    ``generated_at`` and ``content_version`` let the frontend key its cache and
    detect staleness without diffing the whole payload. ``content_version`` is
    the most recent ``updated_at`` across all content tables.
    """

    generated_at: datetime
    content_version: datetime | None = None

    site: SiteProfileRead
    pages: dict[str, PageContentRead] = Field(
        default_factory=dict, description="Keyed by slug"
    )
    photos: list[PhotoRead] = Field(default_factory=list)
    photos_by_role: dict[str, list[PhotoRead]] = Field(default_factory=dict)
    videos: list[VideoRead] = Field(default_factory=list)
    faqs: list[FAQRead] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["up", "down"]
    db_latency_ms: float = Field(..., description="Round trip of the liveness query")
    environment: str
    checked_at: datetime
    detail: str | None = None
