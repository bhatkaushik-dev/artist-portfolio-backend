"""Captured leads. Persistence happens before any side effect."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EnquiryStatus


class Enquiry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enquiries"
    __table_args__ = (Index("ix_enquiries_status_created_at", "status", "created_at"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    subject: Mapped[str | None] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Free-form so the frontend can add new entry points without a migration.
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="contact_page")

    status: Mapped[EnquiryStatus] = mapped_column(
        SAEnum(
            EnquiryStatus,
            name="enquiry_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=EnquiryStatus.PENDING,
        index=True,
    )

    # --- Request provenance (captured server side, never client supplied) ---
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
    referer: Mapped[str | None] = mapped_column(String(512))

    # --- Notification bookkeeping ------------------------------------------
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_error: Mapped[str | None] = mapped_column(Text)

    admin_notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Enquiry email={self.email!r} status={self.status}>"
