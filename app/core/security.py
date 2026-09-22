"""Credential generation for tenant keys."""

from __future__ import annotations

import re
import secrets

# Long enough that a lookup by exact match needs no rate limiting to stay safe.
ADMIN_KEY_BYTES = 32
SITE_KEY_BYTES = 16

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def new_admin_key() -> str:
    """Secret write credential for one tenant."""
    return secrets.token_urlsafe(ADMIN_KEY_BYTES)


def new_site_key() -> str:
    """Public read credential, safe to ship in a frontend bundle."""
    return secrets.token_urlsafe(SITE_KEY_BYTES)


def slugify(value: str) -> str:
    """Lowercase kebab-case, usable in a storage path and a URL."""
    return _SLUG_STRIP.sub("-", value.lower()).strip("-")
