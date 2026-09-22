"""``/api/pages`` — copy, structured blocks and SEO metadata per route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantAdminDep, TenantDep
from app.models.page_content import PageContent
from app.models.tenant import Tenant
from app.schemas.page import PageContentRead, PageContentUpdate

router = APIRouter(prefix="/pages", tags=["pages"])

SlugPath = Path(
    ...,
    pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$",
    examples=["about", "classes", "contact"],
    description="Lowercase kebab-case route segment",
)


async def _get_page(session: AsyncSession, tenant: Tenant, slug: str) -> PageContent:
    page = await session.scalar(
        select(PageContent).where(
            PageContent.tenant_id == tenant.id, PageContent.slug == slug
        )
    )
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No page content for slug {slug!r}",
        )
    return page


@router.get("", response_model=list[PageContentRead], summary="List all pages")
async def list_pages(session: SessionDep, tenant: TenantDep) -> list[PageContent]:
    result = await session.execute(
        select(PageContent)
        .where(PageContent.tenant_id == tenant.id)
        .order_by(PageContent.slug)
    )
    return list(result.scalars())


@router.get(
    "/{slug}",
    response_model=PageContentRead,
    summary="Copy, blocks and SEO for one route",
)
async def get_page(
    session: SessionDep, tenant: TenantDep, slug: str = SlugPath
) -> PageContent:
    return await _get_page(session, tenant, slug)


@router.put(
    "/{slug}",
    response_model=PageContentRead,
    summary="Update copy, blocks and SEO tags",
)
async def update_page(
    payload: PageContentUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
    slug: str = SlugPath,
) -> PageContent:
    page = await _get_page(session, tenant, slug)

    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(page, field, value)

    await session.commit()
    await session.refresh(page)
    return page
