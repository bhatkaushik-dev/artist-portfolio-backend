"""Image pipeline + Supabase Storage operations.

Two concerns live here on purpose, because they are always used together:

1. **Inspection / transcoding (Pillow).** Dimensions are read from the decoded
   image, never trusted from the client, and every upload is normalised into a
   WebP display asset, a high-resolution JPEG download asset, and a small WebP
   thumbnail for grids and pickers.
2. **Bucket I/O.** Talks to Supabase Storage's REST API over ``httpx`` so the
   whole path stays async — the official ``supabase-py`` client is synchronous
   and would block the event loop on every upload.

Pillow decoding and encoding are CPU-bound, so they run in a worker thread.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Pillow decodes many formats; we accept the ones a browser upload realistically
# produces and reject the rest before touching storage.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC", "TIFF", "MPO"}

# Guard against decompression-bomb payloads (Pillow's own limit is advisory).
Image.MAX_IMAGE_PIXELS = 80_000_000


class StorageError(RuntimeError):
    """Raised when Supabase Storage rejects or fails an operation."""


class ImageProcessingError(ValueError):
    """Raised when the uploaded bytes are not a usable image."""


@dataclass(slots=True)
class ProcessedImage:
    """Result of the transcode step. Dimensions describe the *output* assets."""

    width: int
    height: int
    webp_bytes: bytes
    jpeg_bytes: bytes
    thumb_bytes: bytes
    source_format: str


@dataclass(slots=True)
class StoredImage:
    """Where the three assets landed in the bucket."""

    webp_path: str
    jpeg_path: str
    thumb_path: str
    webp_url: str
    jpeg_url: str
    thumb_url: str
    webp_size: int
    jpeg_size: int
    width: int
    height: int

    @property
    def paths(self) -> list[str]:
        return [self.webp_path, self.jpeg_path, self.thumb_path]


# ---------------------------------------------------------------------------
# Pillow
# ---------------------------------------------------------------------------


def _thumbnail_webp(img: Image.Image) -> bytes:
    """Downscaled WebP for grids. Never upscales a small scan."""
    thumb = img.copy()
    edge = settings.IMAGE_THUMB_EDGE_PX
    thumb.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="WEBP", quality=settings.IMAGE_THUMB_QUALITY, method=6)
    return buf.getvalue()


def _thumbnail_from_bytes_sync(raw: bytes) -> bytes:
    with Image.open(io.BytesIO(raw)) as img:
        return _thumbnail_webp(img.convert("RGBA"))


async def thumbnail_from_bytes(raw: bytes) -> bytes:
    """Thumbnail an already-processed asset (backfilling older photos)."""
    return await asyncio.to_thread(_thumbnail_from_bytes_sync, raw)


def thumb_path_for(webp_path: str) -> str:
    """``…/name-abc123.webp`` -> ``…/name-abc123.thumb.webp``."""
    return webp_path.removesuffix(".webp") + ".thumb.webp"


def _transcode_sync(raw: bytes) -> ProcessedImage:
    """Decode, orient, downscale and re-encode. Runs off the event loop."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            source_format = (img.format or "").upper()
            if source_format not in ALLOWED_FORMATS:
                raise ImageProcessingError(
                    f"Unsupported image format {source_format or 'unknown'!r}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_FORMATS))}"
                )

            # EXIF orientation must be baked in before measuring, otherwise a
            # portrait phone photo reports landscape dimensions and the
            # frontend reserves the wrong aspect box.
            img = ImageOps.exif_transpose(img)

            # Flatten alpha onto white for the JPEG; WebP keeps transparency.
            rgba = img.convert("RGBA")
            rgb = Image.new("RGB", rgba.size, (255, 255, 255))
            rgb.paste(rgba, mask=rgba.split()[3])

            max_edge = settings.IMAGE_MAX_EDGE_PX
            if max(rgba.size) > max_edge:
                rgba.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

            width, height = rgba.size

            webp_buf = io.BytesIO()
            rgba.save(
                webp_buf,
                format="WEBP",
                quality=settings.IMAGE_WEBP_QUALITY,
                method=6,
            )

            jpeg_buf = io.BytesIO()
            rgb.save(
                jpeg_buf,
                format="JPEG",
                quality=settings.IMAGE_JPEG_QUALITY,
                optimize=True,
                progressive=True,
                subsampling=0,
            )

            return ProcessedImage(
                width=width,
                height=height,
                webp_bytes=webp_buf.getvalue(),
                jpeg_bytes=jpeg_buf.getvalue(),
                thumb_bytes=_thumbnail_webp(rgba),
                source_format=source_format,
            )
    except UnidentifiedImageError as exc:
        raise ImageProcessingError("Uploaded file is not a recognisable image") from exc
    except Image.DecompressionBombError as exc:
        raise ImageProcessingError("Image exceeds the maximum allowed pixel count") from exc


async def transcode(raw: bytes) -> ProcessedImage:
    """Inspect dimensions and produce WebP + JPEG renditions."""
    if not raw:
        raise ImageProcessingError("Uploaded file is empty")
    if len(raw) > settings.IMAGE_MAX_UPLOAD_BYTES:
        limit_mb = settings.IMAGE_MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ImageProcessingError(
            f"File is {len(raw) / (1024 * 1024):.1f}MB, which exceeds the "
            f"{limit_mb:.1f}MB limit"
        )
    return await asyncio.to_thread(_transcode_sync, raw)


# ---------------------------------------------------------------------------
# Supabase Storage
# ---------------------------------------------------------------------------


def _slugify(value: str, *, max_length: int = 48) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in value.strip()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:max_length] or "image"


class SupabaseStorage:
    """Thin async wrapper over the Storage REST API for one bucket."""

    def __init__(self) -> None:
        self._base = f"{str(settings.SUPABASE_URL).rstrip('/')}/storage/v1"
        self._bucket = settings.SUPABASE_BUCKET
        self._headers = {
            "Authorization": f"Bearer {settings.SUPABASE_KEY}",
            "apikey": settings.SUPABASE_KEY,
        }
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ---------------------------------------------------------

    async def startup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=self._headers,
            timeout=settings.SUPABASE_STORAGE_TIMEOUT_SECONDS,
        )

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Lazily created so scripts (seed.py) can use the service without
            # going through the FastAPI lifespan.
            self._client = httpx.AsyncClient(
                base_url=self._base,
                headers=self._headers,
                timeout=settings.SUPABASE_STORAGE_TIMEOUT_SECONDS,
            )
        return self._client

    # -- helpers -----------------------------------------------------------

    def public_url(self, path: str) -> str:
        return f"{settings.storage_public_base}/{path.lstrip('/')}"

    async def ensure_bucket(self) -> None:
        """Create ``portfolio-media`` as a public bucket if it does not exist."""
        resp = await self.client.get(f"/bucket/{self._bucket}")
        if resp.status_code == 200:
            return
        if resp.status_code not in (400, 404):
            raise StorageError(f"Could not inspect bucket: {resp.status_code} {resp.text}")

        create = await self.client.post(
            "/bucket",
            json={
                "id": self._bucket,
                "name": self._bucket,
                "public": True,
                "file_size_limit": settings.IMAGE_MAX_UPLOAD_BYTES,
                "allowed_mime_types": ["image/webp", "image/jpeg", "image/png"],
            },
        )
        # 409 means another worker won the race — that is a success for us.
        if create.status_code not in (200, 201, 409):
            raise StorageError(f"Could not create bucket: {create.status_code} {create.text}")
        logger.info("Ensured Supabase bucket %r exists", self._bucket)

    # -- objects -----------------------------------------------------------

    async def upload(
        self,
        path: str,
        data: bytes,
        content_type: str,
        *,
        upsert: bool = True,
        cache_seconds: int = 31_536_000,
    ) -> str:
        """Upload one object and return its public URL."""
        resp = await self.client.post(
            f"/object/{self._bucket}/{path.lstrip('/')}",
            content=data,
            headers={
                "Content-Type": content_type,
                # Assets are content-addressed by their random path, so they can
                # be cached immutably for a year.
                "Cache-Control": f"max-age={cache_seconds}, immutable",
                "x-upsert": "true" if upsert else "false",
            },
        )
        if resp.status_code not in (200, 201):
            raise StorageError(f"Upload of {path!r} failed: {resp.status_code} {resp.text}")
        return self.public_url(path)

    async def delete(self, paths: list[str]) -> None:
        """Remove objects. Missing objects are not treated as an error."""
        if not paths:
            return
        resp = await self.client.request(
            "DELETE",
            f"/object/{self._bucket}",
            json={"prefixes": [p.lstrip("/") for p in paths]},
        )
        if resp.status_code not in (200, 204, 404):
            raise StorageError(f"Delete failed: {resp.status_code} {resp.text}")

    # -- pipeline ----------------------------------------------------------

    async def process_and_store(
        self,
        raw: bytes,
        *,
        tenant_slug: str,
        role: str,
        alt: str,
    ) -> StoredImage:
        """Full upload path: inspect → transcode → store all three renditions.

        On a partial failure the already-uploaded renditions are cleaned up so
        the bucket never accumulates orphans without a database row.
        """
        processed = await transcode(raw)

        stem = _slugify(alt)
        # Tenant segment first: one shared bucket, no cross-artist collisions.
        folder = f"{tenant_slug}/{role}/{datetime.now(tz=UTC):%Y/%m}"
        unique = uuid.uuid4().hex[:12]
        webp_path = f"{folder}/{stem}-{unique}.webp"
        jpeg_path = f"{folder}/{stem}-{unique}.jpg"
        thumb_path = thumb_path_for(webp_path)

        webp_url = await self.upload(webp_path, processed.webp_bytes, "image/webp")
        try:
            jpeg_url = await self.upload(jpeg_path, processed.jpeg_bytes, "image/jpeg")
            thumb_url = await self.upload(thumb_path, processed.thumb_bytes, "image/webp")
        except StorageError:
            # Missing objects are ignored by delete, so this is safe whichever
            # upload failed.
            await self.delete([webp_path, jpeg_path, thumb_path])
            raise

        return StoredImage(
            webp_path=webp_path,
            jpeg_path=jpeg_path,
            thumb_path=thumb_path,
            webp_url=webp_url,
            jpeg_url=jpeg_url,
            thumb_url=thumb_url,
            webp_size=len(processed.webp_bytes),
            jpeg_size=len(processed.jpeg_bytes),
            width=processed.width,
            height=processed.height,
        )


storage_service = SupabaseStorage()
