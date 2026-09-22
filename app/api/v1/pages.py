"""``/api/pages`` — copy, structured blocks and SEO metadata per route."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models.page_content import PageContent
from app.schemas.page import PageContentRead, PageContentUpdate

router = APIRouter(prefix="/pages", tags=["pages"])

SlugPath = Path(
    ...,
    pattern=r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$",
    examples=["about", "classes", "contact"],
    description="Lowercase kebab-case route segment",
)


async def _get_page(session: SessionDep, slug: str) -> PageContent:
    page = (
        await session.execute(select(PageContent).where(PageContent.slug == slug))
    ).scalar_one_or_none()
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No page content for slug {slug!r}",
        )
    return page


@router.get("", response_model=list[PageContentRead], summary="List all pages")
async def list_pages(session: SessionDep) -> list[PageContent]:
    result = await session.execute(select(PageContent).order_by(PageContent.slug))
    return list(result.scalars())


@router.get(
    "/{slug}",
    response_model=PageContentRead,
    summary="Copy, blocks and SEO for one route",
)
async def get_page(session: SessionDep, slug: str = SlugPath) -> PageContent:
    return await _get_page(session, slug)


@router.put(
    "/{slug}",
    response_model=PageContentRead,
    dependencies=[AdminDep],
    summary="Update copy, blocks and SEO tags",
)
async def update_page(
    payload: PageContentUpdate,
    session: SessionDep,
    slug: str = SlugPath,
) -> PageContent:
    page = await _get_page(session, slug)

    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(page, field, value)

    await session.commit()
    await session.refresh(page)
    return page
