"""Gallery / hero imagery with pipeline-derived dimensions."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PhotoRole


class Photo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One uploaded image, stored three times: WebP for display, JPEG for
    download, and a small WebP thumbnail for grids.

    ``width``/``height`` are always read off the decoded image by the upload
    pipeline — never accepted from the client — because ImageObject JSON-LD and
    the frontend's ``next/image`` sizing must agree exactly.
    """

    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint("width > 0 AND height > 0", name="positive_dimensions"),
        Index("ix_photos_role_sort_order", "role", "sort_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[PhotoRole] = mapped_column(
        SAEnum(PhotoRole, name="photo_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PhotoRole.GALLERY,
    )

    # Display asset (WebP) and original-quality asset (JPEG).
    src: Mapped[str] = mapped_column(String(512), nullable=False)
    download_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # Small WebP for grids and pickers. Nullable only for rows uploaded before
    # thumbnails existed; migrate_photo_thumbs.py backfills them.
    thumb_url: Mapped[str | None] = mapped_column(String(512))

    # Bucket-relative keys, kept so deletes can clean up storage.
    storage_path_webp: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path_jpeg: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path_thumb: Mapped[str | None] = mapped_column(String(512))

    @property
    def storage_paths(self) -> list[str]:
        return [
            p
            for p in (self.storage_path_webp, self.storage_path_jpeg, self.storage_path_thumb)
            if p
        ]

    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    alt: Mapped[str] = mapped_column(String(320), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(500))
    credit: Mapped[str | None] = mapped_column(String(160))

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    byte_size_webp: Mapped[int | None] = mapped_column(Integer)
    byte_size_jpeg: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Photo role={self.role} {self.width}x{self.height}>"
