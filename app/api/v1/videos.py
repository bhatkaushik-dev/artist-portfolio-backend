"""``/api/videos`` — YouTube-backed performance videos."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantAdminDep, TenantDep
from app.models.tenant import Tenant
from app.models.video import Video
from app.schemas.video import VideoCreate, VideoRead, VideoUpdate
from app.services.youtube_service import fallback_thumbnail_url, fetch_metadata

router = APIRouter(prefix="/videos", tags=["videos"])


async def _get_video(
    session: AsyncSession, tenant: Tenant, video_id: uuid.UUID
) -> Video:
    """Scope the lookup by tenant so a guessed id from another tenant 404s."""
    video = await session.scalar(
        select(Video).where(Video.id == video_id, Video.tenant_id == tenant.id)
    )
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )
    return video


@router.get("", response_model=list[VideoRead], summary="Ordered video list")
async def list_videos(
    session: SessionDep,
    tenant: TenantDep,
    featured: bool | None = Query(None, description="Filter to featured videos only"),
    include_inactive: bool = Query(False),
) -> list[Video]:
    stmt = select(Video).where(Video.tenant_id == tenant.id)
    if featured is not None:
        stmt = stmt.where(Video.featured.is_(featured))
    if not include_inactive:
        stmt = stmt.where(Video.is_active.is_(True))

    # Featured first, then explicit order, then newest upload.
    stmt = stmt.order_by(
        Video.featured.desc(), Video.sort_order, Video.upload_date.desc().nullslast()
    )
    return list((await session.execute(stmt)).scalars())


@router.post(
    "",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a video by YouTube id, syncing metadata when possible",
)
async def create_video(
    payload: VideoCreate, session: SessionDep, tenant: TenantAdminDep
) -> Video:
    existing = await session.scalar(
        select(Video).where(
            Video.tenant_id == tenant.id, Video.youtube_id == payload.youtube_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video {payload.youtube_id} already exists",
        )

    synced = None
    if payload.sync_metadata:
        synced = await fetch_metadata(payload.youtube_id)

    def pick(explicit, remote, default=None):
        """Admin-supplied values always win over synced ones."""
        if explicit is not None:
            return explicit
        if remote is not None:
            return remote
        return default

    video = Video(
        tenant_id=tenant.id,
        youtube_id=payload.youtube_id,
        title=pick(
            payload.title,
            synced.title if synced else None,
            f"Performance {payload.youtube_id}",
        ),
        description=pick(payload.description, synced.description if synced else None),
        upload_date=pick(payload.upload_date, synced.upload_date if synced else None),
        duration=pick(payload.duration, synced.duration if synced else None),
        thumbnail_url=pick(
            payload.thumbnail_url,
            synced.thumbnail_url if synced else None,
            fallback_thumbnail_url(payload.youtube_id),
        ),
        sort_order=payload.order,
        featured=payload.featured,
        metadata_synced_at=datetime.now(tz=UTC) if synced else None,
    )

    session.add(video)
    try:
        await session.commit()
    except IntegrityError as exc:  # concurrent create on the same id
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video {payload.youtube_id} already exists",
        ) from exc
    await session.refresh(video)
    return video


@router.put(
    "/{video_id}",
    response_model=VideoRead,
    summary="Update video fields",
)
async def update_video(
    video_id: uuid.UUID,
    payload: VideoUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
) -> Video:
    video = await _get_video(session, tenant, video_id)

    updates = payload.model_dump(exclude_unset=True)
    if "order" in updates:
        updates["sort_order"] = updates.pop("order")
    for field, value in updates.items():
        setattr(video, field, value)

    await session.commit()
    await session.refresh(video)
    return video


@router.post(
    "/{video_id}/sync",
    response_model=VideoRead,
    summary="Re-pull metadata from the YouTube Data API",
)
async def sync_video(
    video_id: uuid.UUID, session: SessionDep, tenant: TenantAdminDep
) -> Video:
    video = await _get_video(session, tenant, video_id)

    synced = await fetch_metadata(video.youtube_id)
    if synced is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="YouTube metadata unavailable (missing API key or unknown video)",
        )

    video.title = synced.title or video.title
    video.description = synced.description or video.description
    video.upload_date = synced.upload_date or video.upload_date
    video.duration = synced.duration or video.duration
    video.thumbnail_url = synced.thumbnail_url or video.thumbnail_url
    video.metadata_synced_at = datetime.now(tz=UTC)

    await session.commit()
    await session.refresh(video)
    return video


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    # A 204 must not carry a body, so the default JSONResponse cannot be used.
    response_class=Response,
    summary="Remove a video",
)
async def delete_video(
    video_id: uuid.UUID, session: SessionDep, tenant: TenantAdminDep
) -> None:
    video = await _get_video(session, tenant, video_id)
    await session.delete(video)
    await session.commit()
