"""Gallery / hero imagery with pipeline-derived dimensions."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PhotoRole


class Photo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One uploaded image, stored twice: WebP for display, JPEG for download.

    ``width``/``height`` are always read off the decoded image by the upload
    pipeline — never accepted from the client — because ImageObject JSON-LD and
    the frontend's ``next/image`` sizing must agree exactly.
    """

    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint("width > 0 AND height > 0", name="positive_dimensions"),
        Index("ix_photos_role_sort_order", "role", "sort_order"),
    )

    role: Mapped[PhotoRole] = mapped_column(
        SAEnum(PhotoRole, name="photo_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PhotoRole.GALLERY,
    )

    # Display asset (WebP) and original-quality asset (JPEG).
    src: Mapped[str] = mapped_column(String(512), nullable=False)
    download_url: Mapped[str] = mapped_column(String(512), nullable=False)

    # Bucket-relative keys, kept so deletes can clean up storage.
    storage_path_webp: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path_jpeg: Mapped[str] = mapped_column(String(512), nullable=False)

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
