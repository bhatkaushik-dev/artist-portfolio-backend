"""Site profile schemas — the contract behind Person/LocalBusiness JSON-LD."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

E164_PATTERN = r"^\+[1-9]\d{7,14}$"


class Address(BaseModel):
    """schema.org PostalAddress."""

    model_config = ConfigDict(extra="ignore")

    street_address: str | None = None
    locality: str | None = Field(None, description="City — maps to addressLocality")
    region: str | None = Field(None, description="State — maps to addressRegion")
    postal_code: str | None = None
    country: str = Field("IN", description="ISO 3166-1 alpha-2")


class Geo(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class SocialLink(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform: str
    url: str
    handle: str | None = None


class TrainingEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    institution: str | None = None
    teacher: str | None = None
    gharana: str | None = None
    years: str | None = None


class OpeningHours(BaseModel):
    """schema.org OpeningHoursSpecification."""

    model_config = ConfigDict(extra="ignore")

    days: list[str] = Field(..., min_length=1, description="e.g. ['Monday','Tuesday']")
    opens: str = Field(..., description="HH:MM, 24h")
    closes: str = Field(..., description="HH:MM, 24h")


class Award(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    awarded_by: str | None = None
    year: int | None = None


class SiteProfileRead(ORMModel):
    name: str
    short_name: str | None = None
    role: str
    tagline: str | None = None
    locale: str

    email: EmailStr | None = None
    phone: str | None = Field(None, description="E.164")
    phone_display: str | None = None
    website_url: str | None = None

    address: Address = Field(default_factory=Address)
    geo_lat: float | None = None
    geo_lng: float | None = None
    area_served: list[str] = Field(default_factory=list)

    social_links: list[SocialLink] = Field(default_factory=list)
    training: list[TrainingEntry] = Field(default_factory=list)

    alternate_names: list[str] = Field(default_factory=list)
    knows_about: list[str] = Field(default_factory=list)
    knows_language: list[str] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)

    opening_hours: list[OpeningHours] = Field(default_factory=list)
    price_range: str | None = None
    currencies_accepted: list[str] = Field(default_factory=list)

    image_license_url: str | None = None
    default_image_url: str | None = None
    logo_url: str | None = None

    bio_summary: str | None = None
    updated_at: datetime

    @property
    def geo(self) -> Geo | None:
        """Convenience accessor for schema builders."""
        if self.geo_lat is None or self.geo_lng is None:
            return None
        return Geo(latitude=self.geo_lat, longitude=self.geo_lng)


class SiteProfileUpdate(BaseModel):
    """Partial update. Only supplied keys are written."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(None, min_length=1, max_length=160)
    short_name: str | None = Field(None, max_length=80)
    role: str | None = Field(None, min_length=1, max_length=160)
    tagline: str | None = Field(None, max_length=280)
    locale: str | None = Field(None, max_length=16)

    email: EmailStr | None = None
    phone: str | None = Field(None, pattern=E164_PATTERN)
    phone_display: str | None = Field(None, max_length=40)
    website_url: str | None = Field(None, max_length=512)

    address: Address | None = None
    geo_lat: float | None = Field(None, ge=-90, le=90)
    geo_lng: float | None = Field(None, ge=-180, le=180)
    area_served: list[str] | None = None

    social_links: list[SocialLink] | None = None
    training: list[TrainingEntry] | None = None

    alternate_names: list[str] | None = None
    knows_about: list[str] | None = None
    knows_language: list[str] | None = None
    awards: list[Award] | None = None

    opening_hours: list[OpeningHours] | None = None
    price_range: str | None = Field(None, max_length=40)
    currencies_accepted: list[str] | None = None

    image_license_url: str | None = Field(None, max_length=512)
    default_image_url: str | None = Field(None, max_length=512)
    logo_url: str | None = Field(None, max_length=512)

    bio_summary: str | None = None

    @field_validator("opening_hours")
    @classmethod
    def _validate_hours(cls, value: list[OpeningHours] | None) -> list[OpeningHours] | None:
        if value:
            for slot in value:
                if slot.opens >= slot.closes:
                    raise ValueError(
                        f"opening_hours: opens ({slot.opens}) must precede closes ({slot.closes})"
                    )
        return value
