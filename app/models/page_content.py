"""Per-route copy, structured blocks and SEO metadata."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PageContent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single routable page (``about``, ``classes``, ``contact``, ...).

    ``blocks`` is JSONB: story chapters, class formats and CTAs evolve faster
    than a migration cycle. The known keys for each slug are validated on write
    (see ``app/schemas/page_blocks.py``); anything else passes through.
    """

    __tablename__ = "page_content"
    # Every tenant needs its own "about" page, so the slug is unique per tenant.
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_page_content_tenant_id_slug"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # The page's name (nav label, breadcrumb) — not its on-page heading.
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(320))

    # --- Header ------------------------------------------------------------
    # Every page header reads: small-caps eyebrow, then the h1 as ``heading``
    # followed by ``highlight`` set in gold ("Tabla Classes in" + "JP Nagar").
    eyebrow: Mapped[str | None] = mapped_column(String(120))
    heading: Mapped[str | None] = mapped_column(String(200))
    highlight: Mapped[str | None] = mapped_column(String(200))
    intro: Mapped[str | None] = mapped_column(Text)
    # SET NULL so deleting a photo degrades the header rather than 500ing it.
    header_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("photos.id", ondelete="SET NULL")
    )

    body: Mapped[str | None] = mapped_column(Text)

    blocks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- SEO ---------------------------------------------------------------
    seo_title: Mapped[str | None] = mapped_column(String(200))
    seo_description: Mapped[str | None] = mapped_column(String(400))
    # Social cards may word things differently; fall back to the seo_* pair.
    og_title: Mapped[str | None] = mapped_column(String(200))
    og_description: Mapped[str | None] = mapped_column(String(400))
    seo_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    canonical_path: Mapped[str | None] = mapped_column(String(255))
    og_image_url: Mapped[str | None] = mapped_column(String(512))
    noindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PageContent slug={self.slug!r}>"
