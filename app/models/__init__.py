"""SQLAlchemy models.

Importing every model here guarantees ``Base.metadata`` is fully populated
before ``create_all`` or an Alembic autogenerate run.
"""

from app.db.base import Base
from app.models.enquiry import Enquiry
from app.models.enums import EnquirySource, EnquiryStatus, PhotoRole
from app.models.faq import FAQ
from app.models.page_content import PageContent
from app.models.photo import Photo
from app.models.site_profile import SITE_PROFILE_ID, SiteProfile
from app.models.video import Video

__all__ = [
    "FAQ",
    "SITE_PROFILE_ID",
    "Base",
    "Enquiry",
    "EnquirySource",
    "EnquiryStatus",
    "PageContent",
    "Photo",
    "PhotoRole",
    "SiteProfile",
    "Video",
]
