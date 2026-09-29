"""``/api/pages`` — copy, structured blocks and SEO metadata per route."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantAdminDep, TenantDep
from app.models.page_content import PageContent
from app.models.photo import Photo
from app.models.tenant import Tenant
from app.schemas.page import PageContentRead, PageContentUpdate
from app.schemas.page_blocks import referenced_photo_ids, validate_blocks

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


def _unprocessable(loc: list[str | int], msg: str) -> HTTPException:
    """A 422 shaped like FastAPI's own, so clients map it onto the field."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["body", *loc], "msg": msg, "type": "value_error"}],
    )


def _check_blocks(slug: str, blocks: dict) -> None:
    try:
        validate_blocks(slug, blocks)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {"loc": ["body", "blocks", *err["loc"]], "msg": err["msg"], "type": err["type"]}
                for err in exc.errors()
            ],
        ) from exc


async def _check_photos(
    session: AsyncSession,
    tenant: Tenant,
    header_photo_id: uuid.UUID | None,
    blocks: dict | None,
) -> None:
    """Every referenced photo must exist and belong to this tenant.

    Without this, a pasted id from another artist's library would render their
    photo, and a stale id would render nothing, silently.
    """
    wanted: dict[uuid.UUID, list[str | int]] = {}
    if header_photo_id is not None:
        wanted[header_photo_id] = ["header_photo_id"]
    if blocks:
        for photo_id in referenced_photo_ids(blocks):
            wanted.setdefault(photo_id, ["blocks"])
    if not wanted:
        return

    found = set(
        (
            await session.execute(
                select(Photo.id).where(Photo.tenant_id == tenant.id, Photo.id.in_(list(wanted)))
            )
        ).scalars()
    )
    for photo_id, loc in wanted.items():
        if photo_id not in found:
            raise _unprocessable(loc, f"Photo {photo_id} does not exist in this library")


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
    updates = payload.model_dump(exclude_unset=True)

    if updates.get("blocks") is not None:
        _check_blocks(slug, updates["blocks"])
    await _check_photos(session, tenant, updates.get("header_photo_id"), updates.get("blocks"))

    for field, value in updates.items():
        setattr(page, field, value)

    await session.commit()
    await session.refresh(page)
    return page
