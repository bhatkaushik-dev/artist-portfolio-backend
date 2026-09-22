"""Enumerations shared by models and schemas."""

from __future__ import annotations

from enum import StrEnum


class PhotoRole(StrEnum):
    """Where a photo is allowed to surface on the site."""

    GALLERY = "gallery"
    HERO = "hero"
    ABOUT = "about"
    CLASSES = "classes"


class EnquiryStatus(StrEnum):
    PENDING = "pending"
    CONTACTED = "contacted"
    CLOSED = "closed"
    SPAM = "spam"


class EnquirySource(StrEnum):
    CONTACT_PAGE = "contact_page"
    CLASSES_PAGE = "classes_page"
    HOME_CTA = "home_cta"
    FOOTER = "footer"
    OTHER = "other"
