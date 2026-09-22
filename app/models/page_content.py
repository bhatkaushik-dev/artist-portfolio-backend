"""Per-route copy, structured blocks and SEO metadata."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PageContent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single routable page (``about``, ``classes``, ``contact``, ...).

    ``blocks`` is deliberately schemaless JSONB: bio paragraphs, repertoire
    lists and class levels all evolve faster than a migration cycle, and the
    frontend validates their shape at the component boundary.
    """

    __tablename__ = "page_content"

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(320))
    intro: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)

    blocks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # --- SEO ---------------------------------------------------------------
    seo_title: Mapped[str | None] = mapped_column(String(200))
    seo_description: Mapped[str | None] = mapped_column(String(400))
    seo_keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    canonical_path: Mapped[str | None] = mapped_column(String(255))
    og_image_url: Mapped[str | None] = mapped_column(String(512))
    noindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PageContent slug={self.slug!r}>"
