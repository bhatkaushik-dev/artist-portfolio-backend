"""Who may sign in to the admin panel.

Sign-in is by Google, but only for addresses listed here — there is no self
sign-up. This is also what bootstraps the very first account, since you cannot
sign in before a row exists.

    python manage_users.py --create-table
    python manage_users.py add you@gmail.com --super
    python manage_users.py add artist@gmail.com --tenant kaushik-bhat
    python manage_users.py list
    python manage_users.py disable artist@gmail.com
    python manage_users.py remove artist@gmail.com
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select, text

from app.db.session import engine
from app.models.tenant import Tenant
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger("users")


async def create_table() -> None:
    """Create the ``users`` table if it is not there yet."""
    async with engine.begin() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('public.users')"))
        if exists:
            log.info("users table already exists")
            return
        await conn.run_sync(User.__table__.create)
        log.info("created the users table")


async def add(email: str, tenant_slug: str | None, is_super: bool) -> None:
    email = email.strip().lower()
    if not is_super and not tenant_slug:
        sys.exit("Pass either --super or --tenant <slug>")
    if is_super and tenant_slug:
        sys.exit("A super admin manages every artist, so --tenant does not apply")

    async with engine.begin() as conn:
        tenant_id = None
        if tenant_slug:
            tenant_id = await conn.scalar(
                select(Tenant.id).where(Tenant.slug == tenant_slug)
            )
            if tenant_id is None:
                sys.exit(f"No artist with slug {tenant_slug!r}")

        existing = await conn.scalar(select(User.id).where(User.email == email))
        if existing:
            await conn.execute(
                User.__table__.update()
                .where(User.id == existing)
                .values(tenant_id=tenant_id, is_super=is_super, is_active=True)
            )
            log.info("updated %s", email)
        else:
            await conn.execute(
                User.__table__.insert().values(
                    email=email, tenant_id=tenant_id, is_super=is_super, is_active=True
                )
            )
            log.info("added %s", email)

    where = "super admin" if is_super else f"artist {tenant_slug!r}"
    log.info("%s can now sign in as %s", email, where)


async def set_active(email: str, active: bool) -> None:
    email = email.strip().lower()
    async with engine.begin() as conn:
        result = await conn.execute(
            User.__table__.update().where(User.email == email).values(is_active=active)
        )
        if result.rowcount == 0:
            sys.exit(f"No user with email {email!r}")
    log.info("%s is now %s", email, "active" if active else "disabled")


async def remove(email: str) -> None:
    email = email.strip().lower()
    async with engine.begin() as conn:
        result = await conn.execute(User.__table__.delete().where(User.email == email))
        if result.rowcount == 0:
            sys.exit(f"No user with email {email!r}")
    log.info("removed %s", email)


async def show() -> None:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(User.email, User.is_super, User.is_active, User.last_login_at, Tenant.slug)
                .outerjoin(Tenant, Tenant.id == User.tenant_id)
                .order_by(User.email)
            )
        ).all()

    if not rows:
        log.info("no users yet — add one with: python manage_users.py add you@gmail.com --super")
        return

    for row in rows:
        role = "super admin" if row.is_super else (row.slug or "no artist")
        state = "" if row.is_active else "  [disabled]"
        seen = row.last_login_at.strftime("%Y-%m-%d %H:%M") if row.last_login_at else "never"
        log.info("%-38s %-16s last seen %s%s", row.email, role, seen, state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--create-table", action="store_true", help="Create the users table, then exit")
    sub = parser.add_subparsers(dest="command")

    add_cmd = sub.add_parser("add", help="Allow an email address to sign in")
    add_cmd.add_argument("email")
    add_cmd.add_argument("--tenant", help="Artist slug this person may edit")
    add_cmd.add_argument("--super", action="store_true", dest="is_super")

    sub.add_parser("list", help="Show everyone who may sign in")

    for name, help_text in (("disable", "Block sign-in"), ("enable", "Restore sign-in")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("email")

    remove_cmd = sub.add_parser("remove", help="Delete the account entirely")
    remove_cmd.add_argument("email")

    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.create_table:
                await create_table()
                if not args.command:
                    return
            if args.command == "add":
                await create_table()
                await add(args.email, args.tenant, args.is_super)
            elif args.command == "list":
                await show()
            elif args.command == "disable":
                await set_active(args.email, False)
            elif args.command == "enable":
                await set_active(args.email, True)
            elif args.command == "remove":
                await remove(args.email)
            elif not args.create_table:
                parser.print_help()
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
