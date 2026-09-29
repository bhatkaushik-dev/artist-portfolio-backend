"""Site profile schemas — the contract behind Person/LocalBusiness JSON-LD."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

E164_PATTERN = r"^\+[1-9]\d{7,14}$"


class Address(BaseModel):
    """schema.org PostalAddress, plus the venue lessons are held in.

    Keep every copy of this (site, JSON-LD, directory listings) character-for-
    character identical — consistency is the local-ranking signal.
    """

    model_config = ConfigDict(extra="ignore")

    venue: str | None = Field(None, description="Building or host school, e.g. a music school")
    street_address: str | None = None
    locality: str | None = Field(
        None, description="Neighbourhood, e.g. 'JP Nagar 1st Phase' — joined onto streetAddress"
    )
    area: str | None = Field(
        None, description="Short form for running copy, e.g. 'JP Nagar'"
    )
    city: str | None = Field(None, description="Maps to addressLocality")
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


class TrainingSummary(BaseModel):
    """The credential line repeated across the home, about and classes pages.

    One object rather than a list of entries, so "14+ years under Pt X, B-High
    graded by All India Radio" is edited once and every page follows.
    """

    model_config = ConfigDict(extra="ignore")

    start_age: int | None = Field(None, ge=1, le=120)
    years: int | None = Field(None, ge=0, le=120)
    teacher: str | None = Field(None, max_length=160, description="Current guru")
    father: str | None = Field(None, max_length=160, description="First teacher, if family")
    grade: str | None = Field(None, max_length=40, description="e.g. 'B-High'")
    grading_body: str | None = Field(None, max_length=160, description="e.g. 'All India Radio'")


class School(BaseModel):
    """The teaching practice — MusicSchool/LocalBusiness JSON-LD."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(None, max_length=200)
    alternate_name: str | None = Field(None, max_length=200)
    description: str | None = None
    image_url: str | None = Field(None, max_length=512)
    offer_catalog_name: str | None = Field(None, max_length=200)
    offerings: list[str] = Field(default_factory=list, description="One Offer per course")


def _legacy_training(value: object) -> object:
    # Rows written before the redesign hold a list of lineage entries. Nothing
    # in that shape maps onto the summary, so read it as empty until re-saved.
    return {} if isinstance(value, list) else value


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
    training: TrainingSummary = Field(default_factory=TrainingSummary)

    alternate_names: list[str] = Field(default_factory=list)
    knows_about: list[str] = Field(default_factory=list)
    knows_language: list[str] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)

    opening_hours: list[OpeningHours] = Field(default_factory=list)
    price_range: str | None = None
    currencies_accepted: list[str] = Field(default_factory=list)
    school: School = Field(default_factory=School)

    image_credit_text: str | None = None
    image_copyright_notice: str | None = None
    image_license_url: str | None = None
    image_acquire_license_url: str | None = None
    default_image_url: str | None = None
    logo_url: str | None = None

    bio_summary: str | None = None
    updated_at: datetime

    @field_validator("training", mode="before")
    @classmethod
    def _coerce_training(cls, value: object) -> object:
        return _legacy_training(value)

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
    training: TrainingSummary | None = None

    alternate_names: list[str] | None = None
    knows_about: list[str] | None = None
    knows_language: list[str] | None = None
    awards: list[Award] | None = None

    opening_hours: list[OpeningHours] | None = None
    price_range: str | None = Field(None, max_length=40)
    currencies_accepted: list[str] | None = None
    school: School | None = None

    image_credit_text: str | None = Field(None, max_length=160)
    image_copyright_notice: str | None = Field(None, max_length=200)
    image_license_url: str | None = Field(None, max_length=512)
    image_acquire_license_url: str | None = Field(None, max_length=512)
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
