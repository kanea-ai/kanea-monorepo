from __future__ import annotations

# Platform back-office surface. Every endpoint under ``/api/v1/admin``
# is gated by ``SuperadminDep`` (the ``get_current_superadmin``
# dependency). Workspace OWNERs cannot reach these routes — the
# ``users.is_superadmin`` flag is platform-level, separate from any
# workspace role.
from fastapi import APIRouter, status

from app.api.deps import SuperadminDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def admin_health(superadmin: SuperadminDep) -> dict[str, str]:
    """Liveness probe for the back-office surface. Doubles as a
    smoke check that ``SuperadminDep`` is wired: hitting this route
    with any non-superadmin JWT must 403. Returns the resolved
    superadmin's email so the caller can confirm which identity
    passed the gate."""
    return {"status": "ok", "email": superadmin.email}
