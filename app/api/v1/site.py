"""``/api/site`` — one profile per tenant."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantAdminDep, TenantDep
from app.models.site_profile import SiteProfile
from app.models.tenant import Tenant
from app.schemas.site import SiteProfileRead, SiteProfileUpdate

router = APIRouter(prefix="/site", tags=["site"])


async def load_profile(session: AsyncSession, tenant: Tenant) -> SiteProfile:
    """Fetch this tenant's profile or fail with a directive error."""
    profile = await session.scalar(
        select(SiteProfile).where(SiteProfile.tenant_id == tenant.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Site profile has not been initialised. "
                f"Run `python seed.py --tenant {tenant.slug}`."
            ),
        )
    return profile


@router.get(
    "",
    response_model=SiteProfileRead,
    summary="Full profile and schema metadata",
)
async def get_site(session: SessionDep, tenant: TenantDep) -> SiteProfile:
    return await load_profile(session, tenant)


@router.put(
    "",
    response_model=SiteProfileRead,
    summary="Update the profile",
)
async def update_site(
    payload: SiteProfileUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
) -> SiteProfile:
    profile = await load_profile(session, tenant)

    # exclude_unset keeps PUT partial: an omitted key is "leave alone", not
    # "set to null". Callers clear a field by sending an explicit null.
    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in updates.items():
        setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)
    return profile
