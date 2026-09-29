"""Migration: content model for the redesigned portfolio.

    python migrate_content_v2.py
    python seed.py --tenant kaushik-bhat   # then refill the new fields

What changes:

* ``site_profile`` gains ``school`` and three image-rights columns.
* ``site_profile.training`` becomes a summary object. A legacy list of lineage
  entries has nothing that maps onto it, so it is reset to ``{}``.
* ``site_profile.address`` splits the neighbourhood from the city: the old
  ``locality`` (which held the city) moves to ``city``.
* ``page_content`` gains ``eyebrow``/``heading``/``highlight``, a
  ``header_photo_id`` foreign key, and ``og_title``/``og_description``.
* Every tenant gets the starter pages it is missing (home, performances,
  gallery), unpublished, so the admin can edit them.

Idempotent — every step checks before it acts, so re-running is harmless. Page
``blocks`` are left alone; re-seed (or edit in the admin) to move them to the
new shapes. Take a database backup first all the same.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.api.v1.tenants import STARTER_PAGES
from app.db.session import dispose_engine, engine

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("migrate")

NEW_COLUMNS: dict[str, tuple[str, ...]] = {
    "site_profile": (
        "school JSONB NOT NULL DEFAULT '{}'::jsonb",
        "image_credit_text VARCHAR(160)",
        "image_copyright_notice VARCHAR(200)",
        "image_acquire_license_url VARCHAR(512)",
    ),
    "page_content": (
        "eyebrow VARCHAR(120)",
        "heading VARCHAR(200)",
        "highlight VARCHAR(200)",
        "header_photo_id UUID",
        "og_title VARCHAR(200)",
        "og_description VARCHAR(400)",
    ),
}

HEADER_PHOTO_FK = "fk_page_content_header_photo_id_photos"


async def run() -> None:
    async with engine.begin() as conn:
        if not await conn.scalar(text("SELECT to_regclass('public.tenants')")):
            logger.error("No tenants table — run migrate_multitenant.py first")
            return

        for table, columns in NEW_COLUMNS.items():
            for column in columns:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column}")
                )
            logger.info("%-14s %d column(s) ensured", table, len(columns))

        exists = await conn.scalar(
            text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": HEADER_PHOTO_FK},
        )
        if not exists:
            await conn.execute(
                text(
                    f"ALTER TABLE page_content ADD CONSTRAINT {HEADER_PHOTO_FK} "
                    "FOREIGN KEY (header_photo_id) REFERENCES photos (id) ON DELETE SET NULL"
                )
            )
            logger.info("page_content   header_photo_id -> photos.id (ON DELETE SET NULL)")

        rows = (
            await conn.execute(
                text(
                    "UPDATE site_profile SET training = '{}'::jsonb "
                    "WHERE jsonb_typeof(training) = 'array'"
                )
            )
        ).rowcount
        logger.info("site_profile   training reset to a summary on %d row(s)", rows)

        rows = (
            await conn.execute(
                text(
                    "UPDATE site_profile "
                    "SET address = (address - 'locality') "
                    "    || jsonb_build_object('city', address -> 'locality') "
                    "WHERE address ? 'locality' AND NOT address ? 'city'"
                )
            )
        ).rowcount
        logger.info("site_profile   address.locality moved to address.city on %d row(s)", rows)

        # blocks/seo_keywords/noindex only have Python-side defaults, so a raw
        # INSERT must supply them.
        for slug, title in STARTER_PAGES.items():
            rows = (
                await conn.execute(
                    text(
                        "INSERT INTO page_content "
                        "(tenant_id, slug, title, blocks, seo_keywords, noindex, is_published) "
                        "SELECT t.id, :slug, :title, '{}'::jsonb, '[]'::jsonb, false, false "
                        "FROM tenants t "
                        "WHERE NOT EXISTS (SELECT 1 FROM page_content p "
                        "                  WHERE p.tenant_id = t.id AND p.slug = :slug)"
                    ),
                    {"slug": slug, "title": title},
                )
            ).rowcount
            if rows:
                logger.info("page_content   /%s created for %d tenant(s)", slug, rows)

    await dispose_engine()
    logger.info("Migration complete — re-run seed.py to fill the new fields")


if __name__ == "__main__":
    asyncio.run(run())
