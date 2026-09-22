"""``/api/enquiries`` — resilient lead capture.

Sequence, deliberately: persist → commit → queue notification → respond with a
WhatsApp fallback. The visitor gets an actionable link even if mail is down.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import SessionDep, TenantAdminDep, TenantDep, client_ip
from app.core.config import settings
from app.models.enquiry import Enquiry
from app.models.enums import EnquiryStatus
from app.models.site_profile import SiteProfile
from app.schemas.enquiry import (
    EnquiryCreate,
    EnquiryCreateResponse,
    EnquiryListResponse,
    EnquiryRead,
    EnquiryStatusUpdate,
)
from app.services.enquiry_service import build_whatsapp_url, notify_new_enquiry

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


@router.post(
    "",
    response_model=EnquiryCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture a lead, notify in the background, return a WhatsApp link",
)
async def create_enquiry(
    payload: EnquiryCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    tenant: TenantDep,
) -> EnquiryCreateResponse:
    enquiry = Enquiry(
        tenant_id=tenant.id,
        name=payload.name,
        email=str(payload.email),
        phone=payload.phone,
        subject=payload.subject,
        message=payload.message,
        source=payload.source,
        status=EnquiryStatus.PENDING,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
    )

    session.add(enquiry)
    await session.commit()
    await session.refresh(enquiry)

    # Queued only after the commit, so the task can always re-read the row.
    if settings.email_enabled:
        background_tasks.add_task(notify_new_enquiry, enquiry.id)

    # The artist's own number, so each tenant's leads reach the right phone.
    profile_phone = await session.scalar(
        select(SiteProfile.phone).where(SiteProfile.tenant_id == tenant.id)
    )

    return EnquiryCreateResponse(
        id=enquiry.id,
        status="persisted",
        whatsapp_url=build_whatsapp_url(
            name=payload.name,
            subject=payload.subject,
            message=payload.message,
            phone=profile_phone,
        ),
        notification_queued=settings.email_enabled,
    )


@router.get(
    "",
    response_model=EnquiryListResponse,
    summary="Admin: list leads, newest first",
)
async def list_enquiries(
    session: SessionDep,
    tenant: TenantAdminDep,
    status_filter: EnquiryStatus | None = Query(
        None, alias="status", description="Filter by lead status"
    ),
    source: str | None = Query(None, max_length=64),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> EnquiryListResponse:
    filters = [Enquiry.tenant_id == tenant.id]
    if status_filter is not None:
        filters.append(Enquiry.status == status_filter)
    if source is not None:
        filters.append(Enquiry.source == source)

    total = await session.scalar(
        select(func.count()).select_from(Enquiry).where(*filters)
    )
    rows = await session.execute(
        select(Enquiry)
        .where(*filters)
        .order_by(Enquiry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return EnquiryListResponse(
        items=[EnquiryRead.model_validate(row) for row in rows.scalars()],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{enquiry_id}",
    response_model=EnquiryRead,
    summary="Admin: update lead status or notes",
)
async def update_enquiry(
    enquiry_id: uuid.UUID,
    payload: EnquiryStatusUpdate,
    session: SessionDep,
    tenant: TenantAdminDep,
) -> Enquiry:
    enquiry = await session.scalar(
        select(Enquiry).where(
            Enquiry.id == enquiry_id, Enquiry.tenant_id == tenant.id
        )
    )
    if enquiry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enquiry not found"
        )

    enquiry.status = payload.status
    if payload.admin_notes is not None:
        enquiry.admin_notes = payload.admin_notes

    await session.commit()
    await session.refresh(enquiry)
    return enquiry
