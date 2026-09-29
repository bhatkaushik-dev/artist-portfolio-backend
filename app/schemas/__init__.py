"""Pydantic v2 request/response schemas."""

from app.schemas.bootstrap import BootstrapResponse, HealthResponse
from app.schemas.enquiry import (
    EnquiryCreate,
    EnquiryCreateResponse,
    EnquiryListResponse,
    EnquiryRead,
    EnquiryStatusUpdate,
)
from app.schemas.faq import FAQCreate, FAQRead, FAQUpdate
from app.schemas.page import PageContentRead, PageContentUpdate, PageSEO
from app.schemas.photo import (
    PhotoOrderUpdate,
    PhotoRead,
    PhotoUpdate,
    PhotoUploadMeta,
)
from app.schemas.site import (
    Address,
    Award,
    Geo,
    OpeningHours,
    School,
    SiteProfileRead,
    SiteProfileUpdate,
    SocialLink,
    TrainingSummary,
)
from app.schemas.video import VideoCreate, VideoRead, VideoUpdate

__all__ = [
    "Address",
    "Award",
    "BootstrapResponse",
    "EnquiryCreate",
    "EnquiryCreateResponse",
    "EnquiryListResponse",
    "EnquiryRead",
    "EnquiryStatusUpdate",
    "FAQCreate",
    "FAQRead",
    "FAQUpdate",
    "Geo",
    "HealthResponse",
    "OpeningHours",
    "PageContentRead",
    "PageContentUpdate",
    "PageSEO",
    "PhotoOrderUpdate",
    "PhotoRead",
    "PhotoUpdate",
    "PhotoUploadMeta",
    "School",
    "SiteProfileRead",
    "SiteProfileUpdate",
    "SocialLink",
    "TrainingSummary",
    "VideoCreate",
    "VideoRead",
    "VideoUpdate",
]
