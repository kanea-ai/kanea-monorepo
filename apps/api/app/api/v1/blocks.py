"""``/blocks`` — paginated, filterable, sortable Blocks page.

Distinct from ``/tasks`` (which the Board view consumes unpaginated)
because the Blocks list is a different surface: it's reviewed top-
down by the team's leadership, can be long, and benefits from
priority + recency views.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import PrincipalDep, TaskServiceDep
from app.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, Page
from app.application.tasks.schemas import TaskResponse
from app.domain.enums import BlocksSort, TaskStatus

router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.get(
    "",
    response_model=Page[TaskResponse],
    status_code=status.HTTP_200_OK,
)
async def list_blocks(
    principal: PrincipalDep,
    service: TaskServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    # Filters — all optional, narrow the result set in SQL.
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    team_id: Annotated[UUID | None, Query()] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    assignee_id: Annotated[UUID | None, Query()] = None,
    # Sort. Default is priority (lower numerical priority = higher
    # rank), so the most urgent blocks land first.
    sort: Annotated[BlocksSort, Query()] = BlocksSort.PRIORITY,
) -> Page[TaskResponse]:
    """Paginated list of blocked tasks with filter + sort controls.

    Visibility mirrors /tasks: non-admin principals only see their
    own assigned blocks, even if they pass a different
    ``assignee_id``. The query param is silently overridden in that
    case.
    """
    return await service.list_blocks(
        principal,
        status=status_filter,
        team_id=team_id,
        project_id=project_id,
        assignee_id=assignee_id,
        sort=sort,
        skip=skip,
        limit=limit,
    )
