"""Application settings.

Every value is sourced from the environment (or a local ``.env``) so the same
image can be promoted between environments without a rebuild.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BeforeValidator, Field, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: Any) -> Any:
    """Accept either a JSON array or a plain comma separated string.

    Platform dashboards (Render, Railway, Fly) only allow flat strings, so
    ``CORS_ORIGINS=https://a.com,https://b.com`` has to keep working.
    """
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return []
    if text.startswith("["):
        return json.loads(text)
    return [item.strip() for item in text.split(",") if item.strip()]


# NoDecode stops pydantic-settings from JSON-parsing the raw env value itself;
# without it a bare comma-separated string raises before _split_csv ever runs.
CSVList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime -----------------------------------------------------------
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    PROJECT_NAME: str = "Artist Portfolio API"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = False

    # --- Database ----------------------------------------------------------
    # Supabase hands out a libpq URL; we normalise it for asyncpg below.
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False
    # Supabase's pooler (port 6543, "transaction" mode) cannot hold prepared
    # statements. Leave this on whenever DATABASE_URL points at the pooler.
    DB_DISABLE_PREPARED_STATEMENTS: bool = True

    # --- Supabase ----------------------------------------------------------
    SUPABASE_URL: AnyHttpUrl
    SUPABASE_KEY: str = Field(
        ...,
        description="service_role key — server side only, never shipped to the browser",
    )
    SUPABASE_BUCKET: str = "portfolio-media"
    SUPABASE_STORAGE_TIMEOUT_SECONDS: float = 30.0

    # --- Image pipeline ----------------------------------------------------
    IMAGE_MAX_UPLOAD_BYTES: int = 15 * 1024 * 1024
    IMAGE_MAX_EDGE_PX: int = 2560
    IMAGE_WEBP_QUALITY: int = 82
    IMAGE_JPEG_QUALITY: int = 90

    # --- Lead capture ------------------------------------------------------
    WHATSAPP_PHONE: str = Field(
        ...,
        description="Digits only, country code first, no '+' (wa.me format)",
    )
    ENQUIRY_NOTIFY_EMAIL: str | None = None

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = True

    # --- Integrations ------------------------------------------------------
    YOUTUBE_API_KEY: str | None = None

    # --- Access control ----------------------------------------------------
    # Per-tenant write credentials live in the ``tenants`` table; this key only
    # gates tenant management (creating an artist, rotating their keys).
    SUPER_ADMIN_KEY: str = Field(
        ..., description="Global secret for tenant management routes only"
    )
    CORS_ORIGINS: CSVList = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """``DATABASE_URL`` normalised for the asyncpg driver.

        asyncpg rejects libpq-only query args such as ``sslmode``, and Supabase
        includes them by default, so they are stripped here rather than in every
        deployment's env var.
        """
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(self.DATABASE_URL)
        scheme = parts.scheme
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+asyncpg"

        libpq_only = {"sslmode", "ssl", "channel_binding", "options", "target_session_attrs"}
        query = urlencode(
            [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in libpq_only]
        )
        return urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def storage_public_base(self) -> str:
        """Public object base URL for the media bucket."""
        host = str(self.SUPABASE_URL).rstrip("/")
        return f"{host}/storage/v1/object/public/{self.SUPABASE_BUCKET}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def email_enabled(self) -> bool:
        """Whether SMTP can send at all. The recipient is resolved per tenant."""
        return bool(self.SMTP_HOST)


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the env is parsed once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
