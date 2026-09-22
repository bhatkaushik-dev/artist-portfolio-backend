"""YouTube-backed performance videos (VideoObject JSON-LD source)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Video(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "videos"
    __table_args__ = (Index("ix_videos_featured_sort_order", "featured", "sort_order"),)

    youtube_id: Mapped[str] = mapped_column(
        String(24), nullable=False, unique=True, index=True
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # VideoObject.uploadDate — the real YouTube publish date when synced.
    upload_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # ISO-8601 duration (e.g. PT12M31S) as required by VideoObject.
    duration: Mapped[str | None] = mapped_column(String(32))
    thumbnail_url: Mapped[str | None] = mapped_column(String(512))

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    metadata_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_id}"

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.youtube_id}"

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Video youtube_id={self.youtube_id!r}>"
