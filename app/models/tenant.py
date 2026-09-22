"""One artist's workspace — every content row hangs off a tenant."""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Also the media storage prefix, so it must stay URL- and path-safe.
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)

    # Public: shipped in the frontend bundle, identifies which tenant to read.
    site_key: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    # Secret: authenticates writes *and* resolves the tenant they apply to.
    admin_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Tenant slug={self.slug!r}>"
