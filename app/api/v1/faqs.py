"""``/api/faqs`` — FAQPage content."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models.faq import FAQ
from app.schemas.faq import FAQCreate, FAQRead, FAQUpdate

router = APIRouter(prefix="/faqs", tags=["faqs"])


async def _get_faq(session: SessionDep, faq_id: uuid.UUID) -> FAQ:
    faq = await session.get(FAQ, faq_id)
    if faq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found")
    return faq


@router.get("", response_model=list[FAQRead], summary="Ordered FAQ list")
async def list_faqs(
    session: SessionDep,
    page_slug: str | None = Query(None, description="Scope to one page"),
    include_inactive: bool = Query(False),
) -> list[FAQ]:
    stmt = select(FAQ)
    if page_slug is not None:
        stmt = stmt.where(FAQ.page_slug == page_slug)
    if not include_inactive:
        stmt = stmt.where(FAQ.is_active.is_(True))

    stmt = stmt.order_by(FAQ.sort_order, FAQ.created_at)
    return list((await session.execute(stmt)).scalars())


@router.post(
    "",
    response_model=FAQRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AdminDep],
    summary="Create an FAQ entry",
)
async def create_faq(payload: FAQCreate, session: SessionDep) -> FAQ:
    data = payload.model_dump()
    faq = FAQ(sort_order=data.pop("order"), **data)
    session.add(faq)
    await session.commit()
    await session.refresh(faq)
    return faq


@router.put(
    "/{faq_id}",
    response_model=FAQRead,
    dependencies=[AdminDep],
    summary="Update an FAQ entry",
)
async def update_faq(
    faq_id: uuid.UUID, payload: FAQUpdate, session: SessionDep
) -> FAQ:
    faq = await _get_faq(session, faq_id)

    updates = payload.model_dump(exclude_unset=True)
    if "order" in updates:
        updates["sort_order"] = updates.pop("order")
    for field, value in updates.items():
        setattr(faq, field, value)

    await session.commit()
    await session.refresh(faq)
    return faq


@router.delete(
    "/{faq_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    # A 204 must not carry a body, so the default JSONResponse cannot be used.
    response_class=Response,
    dependencies=[AdminDep],
    summary="Delete an FAQ entry",
)
async def delete_faq(faq_id: uuid.UUID, session: SessionDep) -> None:
    faq = await _get_faq(session, faq_id)
    await session.delete(faq)
    await session.commit()
