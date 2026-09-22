"""FAQ schemas (FAQPage JSON-LD source)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OrderField, ORMModel


class FAQRead(ORMModel):
    id: uuid.UUID
    question: str
    answer: str
    page_slug: str | None = None
    order: int = OrderField()
    is_active: bool


class FAQCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=320)
    answer: str = Field(..., min_length=1)
    page_slug: str | None = Field(None, max_length=80)
    order: int = Field(0, ge=0)
    is_active: bool = True


class FAQUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str | None = Field(None, min_length=1, max_length=320)
    answer: str | None = Field(None, min_length=1)
    page_slug: str | None = Field(None, max_length=80)
    order: int | None = Field(None, ge=0)
    is_active: bool | None = None
