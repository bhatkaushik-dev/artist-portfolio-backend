"""``/api/bootstrap`` — the single fetch that hydrates the Next.js ISR cache.

All five content queries are issued concurrently against independent sessions,
so the payload costs roughly one round trip rather than five. That matters: this
endpoint runs on every revalidation and on every cold build.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantDep
from app.db.session import SessionFactory
from app.models.faq import FAQ
from app.models.page_content import PageContent
from app.models.photo import Photo
from app.models.site_profile import SiteProfile
from app.models.video import Video
from app.schemas.bootstrap import BootstrapResponse
from app.schemas.faq import FAQRead
from app.schemas.page import PageContentRead
from app.schemas.photo import PhotoRead
from app.schemas.site import SiteProfileRead
from app.schemas.video import VideoRead

router = APIRouter(tags=["bootstrap"])


async def _in_session(runner, tenant_id: uuid.UUID):
    """Run one query in its own session (concurrent use of one is unsafe)."""
    async with SessionFactory() as session:
        return await runner(session, tenant_id)


async def _load_site(session: AsyncSession, tenant_id: uuid.UUID) -> SiteProfile | None:
    return await session.scalar(
        select(SiteProfile).where(SiteProfile.tenant_id == tenant_id)
    )


async def _load_pages(session: AsyncSession, tenant_id: uuid.UUID) -> list[PageContent]:
    result = await session.execute(
        select(PageContent)
        .where(PageContent.tenant_id == tenant_id, PageContent.is_published.is_(True))
        .order_by(PageContent.slug)
    )
    return list(result.scalars())


async def _load_photos(session: AsyncSession, tenant_id: uuid.UUID) -> list[Photo]:
    result = await session.execute(
        select(Photo)
        .where(Photo.tenant_id == tenant_id, Photo.is_active.is_(True))
        .order_by(Photo.role, Photo.sort_order, Photo.created_at)
    )
    return list(result.scalars())


async def _load_videos(session: AsyncSession, tenant_id: uuid.UUID) -> list[Video]:
    result = await session.execute(
        select(Video)
        .where(Video.tenant_id == tenant_id, Video.is_active.is_(True))
        .order_by(
            Video.featured.desc(), Video.sort_order, Video.upload_date.desc().nullslast()
        )
    )
    return list(result.scalars())


async def _load_faqs(session: AsyncSession, tenant_id: uuid.UUID) -> list[FAQ]:
    result = await session.execute(
        select(FAQ)
        .where(FAQ.tenant_id == tenant_id, FAQ.is_active.is_(True))
        .order_by(FAQ.sort_order, FAQ.created_at)
    )
    return list(result.scalars())


@router.get(
    "/bootstrap",
    response_model=BootstrapResponse,
    summary="Everything the frontend needs, in one payload",
)
async def bootstrap(response: Response, tenant: TenantDep) -> BootstrapResponse:
    site, pages, photos, videos, faqs = await asyncio.gather(
        _in_session(_load_site, tenant.id),
        _in_session(_load_pages, tenant.id),
        _in_session(_load_photos, tenant.id),
        _in_session(_load_videos, tenant.id),
        _in_session(_load_faqs, tenant.id),
    )

    if site is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Site profile has not been initialised. "
                f"Run `python seed.py --tenant {tenant.slug}`."
            ),
        )

    photo_models = [PhotoRead.model_validate(p) for p in photos]
    by_role: dict[str, list[PhotoRead]] = defaultdict(list)
    for original, model in zip(photos, photo_models, strict=True):
        by_role[original.role.value].append(model)

    # Latest mutation across every content table — a cheap cache key for ISR.
    timestamps = [site.updated_at, *(p.updated_at for p in pages)]
    timestamps += [p.updated_at for p in photos]
    timestamps += [v.updated_at for v in videos]
    timestamps += [f.updated_at for f in faqs]
    content_version = max((t for t in timestamps if t is not None), default=None)

    payload = BootstrapResponse(
        generated_at=datetime.now(tz=UTC),
        content_version=content_version,
        site=SiteProfileRead.model_validate(site),
        pages={page.slug: PageContentRead.model_validate(page) for page in pages},
        photos=photo_models,
        photos_by_role=dict(by_role),
        videos=[VideoRead.model_validate(v) for v in videos],
        faqs=[FAQRead.model_validate(f) for f in faqs],
    )

    if content_version is not None:
        # Lets Next.js (or a CDN in front of it) short-circuit unchanged builds.
        response.headers["ETag"] = f'W/"{content_version.timestamp():.0f}"'
        response.headers["Last-Modified"] = content_version.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
    return payload
