"""Photo schemas. Dimensions are read-only: the pipeline owns them."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.enums import PhotoRole
from app.schemas.common import OrderField, ORMModel


class PhotoRead(ORMModel):
    id: uuid.UUID
    src: str = Field(..., description="WebP display asset (public URL)")
    download_url: str = Field(..., description="High-resolution JPEG (public URL)")
    # Declared after src: the fallback validator reads it from info.data.
    thumb_url: str = Field(
        None,  # type: ignore[assignment]
        validate_default=True,
        description="≤640px WebP for grids and pickers; falls back to src if absent",
    )
    width: int
    height: int
    alt: str
    caption: str | None = None
    credit: str | None = None
    order: int = OrderField()
    role: PhotoRole
    is_active: bool = True
    created_at: datetime

    @field_validator("thumb_url", mode="before")
    @classmethod
    def _thumb_fallback(cls, value: str | None, info: ValidationInfo) -> str | None:
        # Always hand clients a usable thumbnail, so none needs its own fallback.
        return value or info.data.get("src")


class PhotoUploadMeta(BaseModel):
    """Multipart form fields accompanying the file.

    Note the absence of width/height — they are derived from the bytes.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    alt: str = Field(..., min_length=1, max_length=320)
    caption: str | None = Field(None, max_length=500)
    credit: str | None = Field(None, max_length=160)
    role: PhotoRole = PhotoRole.GALLERY
    order: int | None = Field(None, ge=0)


class PhotoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    alt: str | None = Field(None, min_length=1, max_length=320)
    caption: str | None = Field(None, max_length=500)
    credit: str | None = Field(None, max_length=160)
    role: PhotoRole | None = None
    is_active: bool | None = None


class PhotoOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(..., ge=0)
