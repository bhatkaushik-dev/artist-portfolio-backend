"""YouTube Data API v3 metadata sync.

Only the fields VideoObject JSON-LD needs are pulled: title, description,
publishedAt (``uploadDate``), contentDetails.duration and the best thumbnail.

The service degrades gracefully: with no ``YOUTUBE_API_KEY`` configured it
returns ``None`` and the caller falls back to whatever the admin typed, so a
missing key never blocks video creation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/youtube/v3/videos"

# Ordered best → worst; YouTube omits the larger ones for older uploads.
THUMBNAIL_PREFERENCE = ("maxres", "standard", "high", "medium", "default")


@dataclass(slots=True)
class YouTubeMetadata:
    youtube_id: str
    title: str | None = None
    description: str | None = None
    upload_date: datetime | None = None
    duration: str | None = None
    thumbnail_url: str | None = None


def fallback_thumbnail_url(youtube_id: str) -> str:
    """Deterministic thumbnail that works without an API key."""
    return f"https://i.ytimg.com/vi/{youtube_id}/maxresdefault.jpg"


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # YouTube returns RFC 3339 with a trailing 'Z'.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Unparseable publishedAt from YouTube: %r", value)
        return None


def _pick_thumbnail(thumbnails: dict) -> str | None:
    for key in THUMBNAIL_PREFERENCE:
        entry = thumbnails.get(key)
        if isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    return None


async def fetch_metadata(youtube_id: str) -> YouTubeMetadata | None:
    """Fetch metadata for one video, or ``None`` when unavailable.

    Returns ``None`` (rather than raising) for a missing key, a network error or
    an unknown video id, so the caller can always proceed.
    """
    if not settings.YOUTUBE_API_KEY:
        logger.info("YOUTUBE_API_KEY unset; skipping metadata sync for %s", youtube_id)
        return None

    params = {
        "part": "snippet,contentDetails",
        "id": youtube_id,
        "key": settings.YOUTUBE_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("YouTube metadata fetch failed for %s: %s", youtube_id, exc)
        return None

    items = payload.get("items") or []
    if not items:
        logger.warning("YouTube returned no item for id %s", youtube_id)
        return None

    snippet = items[0].get("snippet", {})
    details = items[0].get("contentDetails", {})

    return YouTubeMetadata(
        youtube_id=youtube_id,
        title=snippet.get("title"),
        description=snippet.get("description"),
        upload_date=_parse_published_at(snippet.get("publishedAt")),
        duration=details.get("duration"),
        thumbnail_url=_pick_thumbnail(snippet.get("thumbnails", {})),
    )
