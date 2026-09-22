"""Singleton row backing ``/api/site`` and the Person/LocalBusiness JSON-LD."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# The profile is a singleton: one row, pinned at id == 1.
SITE_PROFILE_ID = 1


class SiteProfile(Base, TimestampMixin):
    """One row only — enforced by a CHECK constraint on the primary key."""

    __tablename__ = "site_profile"
    __table_args__ = (
        CheckConstraint(f"id = {SITE_PROFILE_ID}", name="singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SITE_PROFILE_ID)

    # --- Identity ----------------------------------------------------------
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(160), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(280))
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en_IN")

    # --- Contact -----------------------------------------------------------
    email: Mapped[str | None] = mapped_column(String(255))
    # Stored strictly in E.164 so it can be reused verbatim in JSON-LD.
    phone: Mapped[str | None] = mapped_column(String(20))
    phone_display: Mapped[str | None] = mapped_column(String(40))
    website_url: Mapped[str | None] = mapped_column(String(512))

    # --- Location ----------------------------------------------------------
    # PostalAddress shaped: {street_address, locality, region, postal_code, country}
    address: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lng: Mapped[float | None] = mapped_column(Float)
    area_served: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- Social / provenance ----------------------------------------------
    # [{platform, url, handle}] — feeds Person.sameAs
    social_links: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{institution, teacher, gharana, years}]
    training: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    alternate_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    knows_about: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    knows_language: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    awards: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- LocalBusiness -----------------------------------------------------
    # OpeningHoursSpecification shaped: [{days[], opens, closes}]
    opening_hours: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    price_range: Mapped[str | None] = mapped_column(String(40))
    currencies_accepted: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # --- Media -------------------------------------------------------------
    image_license_url: Mapped[str | None] = mapped_column(String(512))
    default_image_url: Mapped[str | None] = mapped_column(String(512))
    logo_url: Mapped[str | None] = mapped_column(String(512))

    bio_summary: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SiteProfile name={self.name!r}>"
