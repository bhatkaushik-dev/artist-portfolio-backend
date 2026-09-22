"""``/api/tenants`` — onboarding an artist. Super-admin only.

Creating a tenant hands back two credentials: a public ``site_key`` the artist's
frontend ships in its bundle, and a secret ``admin_key`` for writes. The admin
key is returned exactly once, here and on rotate.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, SuperAdminDep
from app.core.security import new_admin_key, new_site_key, slugify
from app.models.page_content import PageContent
from app.models.site_profile import SiteProfile
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantCredentials, TenantRead, TenantUpdate

router = APIRouter(
    prefix="/tenants",
    tags=["tenants"],
    dependencies=[SuperAdminDep],
)

# ``PUT /api/site`` and ``PUT /api/pages/{slug}`` update in place and 404 on a
# missing row — there is no POST for either, because in the single-tenant days
# seed.py always created them. A tenant that starts empty would therefore be
# uneditable over the API, so onboarding lays down the rows the artist is then
# expected to fill in. Everything else (photos, videos, FAQs) has a real POST
# and legitimately starts empty.
STARTER_PAGES = ("about", "classes", "contact")


async def _get_tenant(session: SessionDep, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return tenant


@router.post(
    "",
    response_model=TenantCredentials,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard an artist and issue their keys",
)
async def create_tenant(payload: TenantCreate, session: SessionDep) -> Tenant:
    slug = payload.slug or slugify(payload.name)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not derive a slug from that name; pass one explicitly",
        )

    tenant = Tenant(
        name=payload.name,
        slug=slug,
        site_key=new_site_key(),
        admin_key=new_admin_key(),
    )
    session.add(tenant)
    try:
        await session.flush()

        session.add(
            SiteProfile(tenant_id=tenant.id, name=payload.name, role="Artist")
        )
        session.add_all(
            PageContent(
                tenant_id=tenant.id,
                slug=page_slug,
                title=page_slug.capitalize(),
                is_published=False,
            )
            for page_slug in STARTER_PAGES
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant slug {slug!r} is already taken",
        ) from exc

    await session.refresh(tenant)
    return tenant


@router.get("", response_model=list[TenantRead], summary="List artists")
async def list_tenants(
    session: SessionDep,
    include_inactive: bool = Query(False),
) -> list[Tenant]:
    stmt = select(Tenant)
    if not include_inactive:
        stmt = stmt.where(Tenant.is_active.is_(True))
    result = await session.execute(stmt.order_by(Tenant.created_at))
    return list(result.scalars())


@router.patch(
    "/{tenant_id}",
    response_model=TenantRead,
    summary="Rename an artist or deactivate them",
)
async def update_tenant(
    tenant_id: uuid.UUID, payload: TenantUpdate, session: SessionDep
) -> Tenant:
    tenant = await _get_tenant(session, tenant_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)

    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.post(
    "/{tenant_id}/rotate-keys",
    response_model=TenantCredentials,
    summary="Issue a fresh admin key; the old one stops working immediately",
)
async def rotate_keys(
    tenant_id: uuid.UUID,
    session: SessionDep,
    site_key: bool = Query(
        False,
        description="Also rotate the public site key — requires a frontend redeploy",
    ),
) -> Tenant:
    tenant = await _get_tenant(session, tenant_id)

    tenant.admin_key = new_admin_key()
    if site_key:
        tenant.site_key = new_site_key()

    await session.commit()
    await session.refresh(tenant)
    return tenant
