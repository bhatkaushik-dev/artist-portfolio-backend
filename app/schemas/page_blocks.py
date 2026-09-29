"""Shapes of ``PageContent.blocks`` for the routes the portfolio renders.

Blocks stay JSONB so a page can grow a section without a migration, but the
keys the frontend reads are checked on write — a typo in the admin's JSON tab
should be a 422 here, not a blank section after the next ISR pass.

Validation only: the route stores the payload exactly as sent, so keys this
module does not know about survive untouched.

Rich text inside ``body``/``paragraphs``/``note`` fields uses two inline marks
and nothing else: ``**bold**`` and ``[label](/path)``.

Photos are referenced by ``photo_id`` (any key named ``photo_id`` or ending in
``_photo_id``) and must belong to the same tenant — see ``referenced_photo_ids``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

KEBAB = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class _Block(BaseModel):
    # Unknown keys are tolerated (and preserved by the route), not rejected.
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class Link(_Block):
    label: str = Field(..., min_length=1, max_length=80)
    href: str = Field(..., min_length=1, max_length=512)


class SectionHeading(_Block):
    """Eyebrow over a heading whose trailing words are set in gold."""

    eyebrow: str | None = Field(None, max_length=120)
    heading: str = Field(..., min_length=1, max_length=200)
    highlight: str | None = Field(None, max_length=200)


# --- home -------------------------------------------------------------------


class HomeHero(_Block):
    tagline: str | None = Field(
        None, max_length=120, description="Line under the name, e.g. 'Tabla Artist | Percussionist'"
    )


class HomeAboutBand(SectionHeading):
    """The biography band under the hero. ``heading`` may contain line breaks."""

    body: str | None = None
    link: Link | None = None
    photo_id: uuid.UUID | None = None


class HomeBlocks(_Block):
    hero: HomeHero | None = None
    about_band: HomeAboutBand | None = None


# --- about ------------------------------------------------------------------


class Chapter(_Block):
    """One passage of the biography; with a photo it becomes a two-column row."""

    id: str = Field(..., pattern=KEBAB, max_length=80, description="Anchor id")
    title: str | None = Field(None, max_length=120, description="Omit for a closing passage")
    photo_id: uuid.UUID | None = None
    caption: str | None = Field(None, max_length=200, description="Defaults to the photo's")
    paragraphs: list[str] = Field(..., min_length=1)


class AboutBlocks(_Block):
    chapters: list[Chapter] = Field(default_factory=list)
    # The screen photos are decorative, so the printed bio carries its own.
    print_photo_id: uuid.UUID | None = None

    @field_validator("chapters")
    @classmethod
    def _unique_ids(cls, chapters: list[Chapter]) -> list[Chapter]:
        seen: set[str] = set()
        for chapter in chapters:
            if chapter.id in seen:
                raise ValueError(f"chapter id {chapter.id!r} is used twice")
            seen.add(chapter.id)
        return chapters


# --- classes ----------------------------------------------------------------


class ClassFormat(_Block):
    icon: str | None = Field(
        None, pattern=KEBAB, max_length=40, description="lucide icon name, e.g. 'map-pin'"
    )
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=400)


class CallToAction(SectionHeading):
    body: str = Field(..., min_length=1)
    primary: Link
    secondary: Link | None = None
    photo_id: uuid.UUID | None = None


class ClassesBlocks(_Block):
    formats: list[ClassFormat] = Field(default_factory=list)
    faq_heading: SectionHeading | None = None
    cta: CallToAction | None = None


# --- contact ----------------------------------------------------------------


class ContactLocation(_Block):
    heading: str = Field(..., min_length=1, max_length=120)
    note: str | None = Field(None, max_length=400)


class ContactBlocks(_Block):
    enquiry_types: list[str] = Field(
        default_factory=list, description="The form's 'Regarding' options"
    )
    location: ContactLocation | None = None

    @field_validator("enquiry_types")
    @classmethod
    def _non_blank(cls, values: list[str]) -> list[str]:
        if any(not v.strip() for v in values):
            raise ValueError("enquiry types cannot be blank")
        return values


# --- performances -----------------------------------------------------------


class ChannelClosing(_Block):
    heading: str = Field(..., min_length=1, max_length=160)
    button_label: str = Field(..., min_length=1, max_length=80)


class PerformancesBlocks(_Block):
    channel_button_label: str | None = Field(None, max_length=80)
    closing: ChannelClosing | None = None


# --- gallery ----------------------------------------------------------------


class GalleryBlocks(_Block):
    count_note: str | None = Field(None, max_length=80, description="Beside the photo count")
    licence_note: str | None = Field(
        None, description="Terms under the grid; target of ImageObject.license"
    )


BLOCK_MODELS: dict[str, type[_Block]] = {
    "home": HomeBlocks,
    "about": AboutBlocks,
    "classes": ClassesBlocks,
    "contact": ContactBlocks,
    "performances": PerformancesBlocks,
    "gallery": GalleryBlocks,
}


def validate_blocks(slug: str, blocks: dict[str, Any]) -> None:
    """Raise ``ValidationError`` if a known slug's blocks are the wrong shape."""
    model = BLOCK_MODELS.get(slug)
    if model is not None:
        model.model_validate(blocks)


def referenced_photo_ids(value: Any) -> set[uuid.UUID]:
    """Every ``photo_id`` / ``*_photo_id`` anywhere in a blocks tree."""
    found: set[uuid.UUID] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == "photo_id" or key.endswith("_photo_id")) and item is not None:
                try:
                    found.add(uuid.UUID(str(item)))
                except ValueError:
                    # Shape errors are validate_blocks' job; skip here.
                    continue
            else:
                found |= referenced_photo_ids(item)
    elif isinstance(value, list):
        for item in value:
            found |= referenced_photo_ids(item)
    return found


__all__ = [
    "BLOCK_MODELS",
    "ValidationError",
    "referenced_photo_ids",
    "validate_blocks",
]
