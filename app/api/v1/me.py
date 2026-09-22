"""``/api/me`` — who does this admin key belong to?

Content reads are keyed by ``X-Site-Key``, but an artist only ever holds their
``admin_key``. Without this route an admin client can authenticate yet still not
read anything, because it has no way to learn its own site key.

Returning ``TenantRead`` discloses nothing the caller does not already own: the
site key is public by design (it ships in the frontend bundle) and ``admin_key``
is absent from that schema.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TenantAdminDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "",
    response_model=TenantRead,
    summary="The tenant this admin key belongs to",
)
async def read_me(tenant: TenantAdminDep) -> Tenant:
    return tenant
