"""Aggregate router mounted at ``/api``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    bootstrap,
    enquiries,
    faqs,
    health,
    me,
    pages,
    photos,
    site,
    tenants,
    videos,
)

api_router = APIRouter()

# health first so it stays reachable even if a content router misbehaves
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(tenants.router)
api_router.include_router(bootstrap.router)
api_router.include_router(site.router)
api_router.include_router(pages.router)
api_router.include_router(photos.router)
api_router.include_router(videos.router)
api_router.include_router(faqs.router)
api_router.include_router(enquiries.router)
