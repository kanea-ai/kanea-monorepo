from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AuditLogServiceDep, WorkspaceAdminDep
from app.application.audit.schemas import AuditLogResponse
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/logs",
    response_model=Page[AuditLogResponse],
    status_code=status.HTTP_200_OK,
)
async def list_audit_logs(
    admin: WorkspaceAdminDep,
    service: AuditLogServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Page[AuditLogResponse]:
    """Workspace audit trail. Admin-only at the route level; visibility
    is then narrowed in the service layer based on the principal's
    role + priority:

    - Owner: every row in the workspace.
    - Admin, priority ≤ 2: department/team/member rows.
    - Admin, priority ≤ 3: team rows for teams they MANAGE on, plus
      every team in any department they HEAD.
    - Anyone else: empty page (the route guard rejects USER role
      first, so this branch is only hit by unusual admin priorities).

    Pagination is ``?skip``/``?limit``; the response carries the
    unfiltered ``total`` (post-visibility scope) so the UI can render
    page-number controls. The (created_at DESC, id DESC) order matches
    the ``ix_audit_logs_workspace_created`` index so paging over a hot
    feed stays cheap.
    """
    return await service.list_for_principal(admin, skip=skip, limit=limit)
