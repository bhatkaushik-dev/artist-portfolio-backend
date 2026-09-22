"""FAQ entries feeding the FAQPage JSON-LD block."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FAQ(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "faqs"
    __table_args__ = (Index("ix_faqs_active_sort_order", "is_active", "sort_order"),)

    question: Mapped[str] = mapped_column(String(320), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional scoping so a page can render only its own subset.
    page_slug: Mapped[str | None] = mapped_column(String(80), index=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<FAQ question={self.question[:40]!r}>"
