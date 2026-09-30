"""Migration: close Supabase's auto-generated REST API over our tables.

    python migrate_enable_rls.py

Supabase exposes every ``public`` table through PostgREST to the ``anon`` and
``authenticated`` roles, and the anon key is public by design. Nothing here
uses that API — the backend connects as ``postgres``, which bypasses RLS — so
the tables are locked down completely:

* RLS is enabled on every table in ``public``, with no policies, so PostgREST
  sees zero rows and cannot write.
* ``anon``/``authenticated`` lose their grants on existing tables and
  sequences, and the default privileges that would hand them new ones.

Idempotent — re-running is harmless, and it also covers tables added later.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.db.session import dispose_engine, engine

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("migrate")

API_ROLES = "anon, authenticated"


async def run() -> None:
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                    "ORDER BY c.relname"
                )
            )
        ).scalars().all()

        for table in tables:
            await conn.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
            logger.info("%-14s RLS enabled", table)

        await conn.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {API_ROLES}"))
        await conn.execute(text(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {API_ROLES}"))
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                f"REVOKE ALL ON TABLES FROM {API_ROLES}"
            )
        )
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
                f"REVOKE ALL ON SEQUENCES FROM {API_ROLES}"
            )
        )
        logger.info("public         grants revoked from %s (existing and future)", API_ROLES)

    await dispose_engine()
    logger.info("Migration complete")


if __name__ == "__main__":
    asyncio.run(run())
