"""``/api/site`` — the profile singleton."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminDep, SessionDep
from app.models.site_profile import SITE_PROFILE_ID, SiteProfile
from app.schemas.site import SiteProfileRead, SiteProfileUpdate

router = APIRouter(prefix="/site", tags=["site"])


async def load_profile(session: SessionDep) -> SiteProfile:
    """Fetch the singleton or fail with a directive error."""
    profile = await session.get(SiteProfile, SITE_PROFILE_ID)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site profile has not been initialised. Run `python seed.py`.",
        )
    return profile


@router.get(
    "",
    response_model=SiteProfileRead,
    summary="Full profile and schema metadata",
)
async def get_site(session: SessionDep) -> SiteProfile:
    return await load_profile(session)


@router.put(
    "",
    response_model=SiteProfileRead,
    dependencies=[AdminDep],
    summary="Update the profile singleton",
)
async def update_site(payload: SiteProfileUpdate, session: SessionDep) -> SiteProfile:
    profile = await load_profile(session)

    # exclude_unset keeps PUT partial: an omitted key is "leave alone", not
    # "set to null". Callers clear a field by sending an explicit null.
    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in updates.items():
        setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)
    return profile
