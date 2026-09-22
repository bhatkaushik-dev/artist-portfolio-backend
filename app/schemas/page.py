"""Page content + SEO schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMModel


class PageSEO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=400)
    keywords: list[str] = Field(default_factory=list)
    canonical_path: str | None = Field(None, max_length=255)
    og_image_url: str | None = Field(None, max_length=512)
    noindex: bool = False


class PageContentRead(ORMModel):
    id: uuid.UUID
    slug: str
    title: str
    subtitle: str | None = None
    intro: str | None = None
    body: str | None = None

    # Schemaless by design — see PageContent.blocks.
    blocks: dict[str, Any] = Field(default_factory=dict)

    is_published: bool
    updated_at: datetime

    seo_title: str | None = None
    seo_description: str | None = None
    seo_keywords: list[str] = Field(default_factory=list)
    canonical_path: str | None = None
    og_image_url: str | None = None
    noindex: bool = False

    @property
    def seo(self) -> PageSEO:
        return PageSEO(
            title=self.seo_title,
            description=self.seo_description,
            keywords=self.seo_keywords,
            canonical_path=self.canonical_path,
            og_image_url=self.og_image_url,
            noindex=self.noindex,
        )


class PageContentUpdate(BaseModel):
    """Partial update; ``blocks`` is replaced wholesale when supplied."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(None, min_length=1, max_length=200)
    subtitle: str | None = Field(None, max_length=320)
    intro: str | None = None
    body: str | None = None
    blocks: dict[str, Any] | None = None
    is_published: bool | None = None

    seo_title: str | None = Field(None, max_length=200)
    seo_description: str | None = Field(None, max_length=400)
    seo_keywords: list[str] | None = None
    canonical_path: str | None = Field(None, max_length=255)
    og_image_url: str | None = Field(None, max_length=512)
    noindex: bool | None = None
