"""Migration: grid thumbnails for photos.

    python migrate_photo_thumbs.py

Adds ``photos.thumb_url`` / ``photos.storage_path_thumb``, then backfills every
photo that has no thumbnail yet: downloads its display WebP, downscales it to
``IMAGE_THUMB_EDGE_PX`` and uploads it next to the original as
``<name>.thumb.webp``. New uploads get a thumbnail from the pipeline itself.

Idempotent — only rows still missing a thumbnail are touched, so an interrupted
run can simply be repeated.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import select, text, update

from app.db.session import SessionFactory, dispose_engine, engine
from app.models.photo import Photo
from app.services.storage_service import storage_service, thumb_path_for, thumbnail_from_bytes

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("migrate")


async def run() -> None:
    async with engine.begin() as conn:
        for column in ("thumb_url VARCHAR(512)", "storage_path_thumb VARCHAR(512)"):
            await conn.execute(text(f"ALTER TABLE photos ADD COLUMN IF NOT EXISTS {column}"))
    logger.info("photos         thumbnail columns ensured")

    done = failed = 0
    async with SessionFactory() as session, httpx.AsyncClient(timeout=60) as http:
        # Plain tuples, not ORM rows: a rollback would expire rows still to be
        # processed, and lazy-loading them in async code raises.
        pending = (
            await session.execute(
                select(Photo.id, Photo.src, Photo.storage_path_webp, Photo.alt).where(
                    Photo.thumb_url.is_(None)
                )
            )
        ).all()
        logger.info("photos         %d without a thumbnail", len(pending))

        for photo_id, src, webp_path, alt in pending:
            try:
                resp = await http.get(src)
                resp.raise_for_status()
                thumb = await thumbnail_from_bytes(resp.content)
                path = thumb_path_for(webp_path)
                url = await storage_service.upload(path, thumb, "image/webp")
                await session.execute(
                    update(Photo)
                    .where(Photo.id == photo_id)
                    .values(thumb_url=url, storage_path_thumb=path)
                )
                # Commit per photo so a failure midway keeps what already worked.
                await session.commit()
                done += 1
                logger.info(
                    "  %-60s %4d KB -> %3d KB",
                    alt[:60],
                    len(resp.content) // 1024,
                    len(thumb) // 1024,
                )
            except Exception:
                await session.rollback()
                failed += 1
                logger.exception("  failed: %s", alt[:60])

    await storage_service.shutdown()
    await dispose_engine()
    logger.info("Backfilled %d thumbnail(s), %d failed", done, failed)


if __name__ == "__main__":
    asyncio.run(run())
