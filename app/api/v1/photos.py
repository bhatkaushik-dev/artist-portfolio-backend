"""``/api/photos`` — listing, the upload pipeline, reordering and deletion."""

from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, TenantAdminDep, TenantDep
from app.models.enums import PhotoRole
from app.models.photo import Photo
from app.models.tenant import Tenant
from app.schemas.photo import PhotoOrderUpdate, PhotoRead, PhotoUpdate, PhotoUploadMeta
from app.services.storage_service import (
    ImageProcessingError,
    StorageError,
    storage_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/photos", tags=["photos"])


async def _get_photo(
    session: AsyncSession, tenant: Tenant, photo_id: uuid.UUID
) -> Photo:
    """Scope the lookup by tenant so a guessed id from another tenant 404s."""
    photo = await session.scalar(
        select(Photo).where(Photo.id == photo_id, Photo.tenant_id == tenant.id)
    )
    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found"
        )
    return photo


@router.get("", response_model=list[PhotoRead], summary="List photos, optionally by role")
async def list_photos(
    session: SessionDep,
    tenant: TenantDep,
    role: PhotoRole | None = Query(None, description="Filter by placement role"),
    include_inactive: bool = Query(False, description="Admin preview of hidden photos"),
) -> list[Photo]:
    stmt = select(Photo).where(Photo.tenant_id == tenant.id)
    if role is not None:
        stmt = stmt.where(Photo.role == role)
    if not include_inactive:
        stmt = stmt.where(Photo.is_active.is_(True))

    stmt = stmt.order_by(Photo.role, Photo.sort_order, Photo.created_at)
    return list((await session.execute(stmt)).scalars())


@router.post(
    "/upload",
    response_model=PhotoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image; dimensions are derived, never supplied",
)
async def upload_photo(
    session: SessionDep,
    tenant: TenantAdminDep,
    file: UploadFile = File(..., description="Source image (JPEG/PNG/WebP/HEIC/TIFF)"),
    alt: str = Form(..., description="Required for accessibility and ImageObject"),
    caption: str | None = Form(None),
    credit: str | None = Form(None),
    role: PhotoRole = Form(PhotoRole.GALLERY),
    order: int | None = Form(None, ge=0),
) -> Photo:
    """Inspect with Pillow, transcode to WebP + JPEG, store, then record.

    Storage is written before the database row so a failed upload cannot leave a
    row pointing at a URL that 404s — the inverse (an orphaned object) is
    cleaned up explicitly below.
    """
    try:
        meta = PhotoUploadMeta(
            alt=alt, caption=caption, credit=credit, role=role, order=order
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
        ) from exc

    raw = await file.read()
    await file.close()

    try:
        stored = await storage_service.process_and_store(
            raw, tenant_slug=tenant.slug, role=meta.role.value, alt=meta.alt
        )
    except ImageProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except StorageError as exc:
        logger.exception("Supabase Storage upload failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Media storage unavailable: {exc}",
        ) from exc

    if meta.order is None:
        # Append to the end of its role bucket.
        next_order = await session.scalar(
            select(func.coalesce(func.max(Photo.sort_order) + 1, 0)).where(
                Photo.tenant_id == tenant.id, Photo.role == meta.role
            )
        )
        sort_order = int(next_order or 0)
    else:
        sort_order = meta.order

    photo = Photo(
        tenant_id=tenant.id,
        role=meta.role,
        src=stored.webp_url,
        download_url=stored.jpeg_url,
        storage_path_webp=stored.webp_path,
        storage_path_jpeg=stored.jpeg_path,
        width=stored.width,
        height=stored.height,
        alt=meta.alt,
        caption=meta.caption,
        credit=meta.credit,
        sort_order=sort_order,
        byte_size_webp=stored.webp_size,
        byte_size_jpeg=stored.jpeg_size,
    )

    session.add(photo)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # Don't leave the bucket holding assets nothing references.
        await storage_service.delete([stored.webp_path, stored.jpeg_path])
        raise
    await session.refresh(photo)
    return photo


@router.patch(
    "/{photo_id}/order",
    response_model=list[PhotoRead],
    summary="Move a photo to a new position within its role",
)
async def reorder_photo(
    photo_id: uuid.UUID,
    payload: PhotoOrderUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
) -> list[Photo]:
    """Reposition one photo and renumber its role bucket contiguously.

    Returns the whole bucket so the admin UI can re-render from the response
    instead of guessing the resulting order.
    """
    photo = await _get_photo(session, tenant, photo_id)

    siblings = list(
        (
            await session.execute(
                select(Photo)
                .where(Photo.tenant_id == tenant.id, Photo.role == photo.role)
                .order_by(Photo.sort_order, Photo.created_at)
            )
        ).scalars()
    )

    siblings.remove(photo)
    target = min(payload.order, len(siblings))
    siblings.insert(target, photo)

    for index, item in enumerate(siblings):
        item.sort_order = index

    await session.commit()
    return siblings


@router.patch(
    "/{photo_id}",
    response_model=PhotoRead,
    summary="Update photo metadata (never dimensions)",
)
async def update_photo(
    photo_id: uuid.UUID,
    payload: PhotoUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
) -> Photo:
    photo = await _get_photo(session, tenant, photo_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(photo, field, value)
    await session.commit()
    await session.refresh(photo)
    return photo


@router.delete(
    "/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    # A 204 must not carry a body, so the default JSONResponse cannot be used.
    response_class=Response,
    summary="Delete the storage objects and the row",
)
async def delete_photo(
    photo_id: uuid.UUID, session: SessionDep, tenant: TenantAdminDep
) -> None:
    photo = await _get_photo(session, tenant, photo_id)
    paths = [photo.storage_path_webp, photo.storage_path_jpeg]

    # Row first: a stale object in a public bucket is harmless, whereas a row
    # whose files are gone renders as a broken image on every ISR pass.
    await session.delete(photo)
    await session.commit()

    try:
        await storage_service.delete(paths)
    except StorageError:
        logger.exception("Orphaned storage objects after deleting photo %s: %s", photo_id, paths)
