"""``/api/health`` — liveness plus Supabase keep-alive.

Supabase pauses free-tier projects after ~7 days without activity, and an HTTP
200 from the app alone does not count as activity. This endpoint therefore
always issues a real query so the scheduled ping touches Postgres.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import select, text

from app.api.deps import SessionDep
from app.core.config import settings
from app.models.site_profile import SITE_PROFILE_ID, SiteProfile
from app.schemas.bootstrap import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Live DB query + latency (keep-alive target)",
)
async def health(response: Response, session: SessionDep) -> HealthResponse:
    """Returns 200 when the database answers, 503 when it does not.

    A non-200 on failure is what makes this usable as an uptime check; the
    scheduled workflow treats any other status as a page-worthy failure.
    """
    started = time.perf_counter()
    database: str = "down"
    detail: str | None = None

    try:
        # SELECT 1 keeps the compute instance warm; the site_profile read also
        # confirms the schema is actually migrated and reachable.
        await session.execute(text("SELECT 1"))
        profile_name = await session.scalar(
            select(SiteProfile.name).where(SiteProfile.id == SITE_PROFILE_ID)
        )
        database = "up"
        if profile_name is None:
            detail = "Database reachable but site_profile is empty; run seed.py"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        logger.exception("Health check database query failed")

    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    if database == "down":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if database == "up" and detail is None else "degraded",
        database=database,  # type: ignore[arg-type]
        db_latency_ms=latency_ms,
        environment=settings.ENVIRONMENT,
        checked_at=datetime.now(tz=UTC),
        detail=detail,
    )
