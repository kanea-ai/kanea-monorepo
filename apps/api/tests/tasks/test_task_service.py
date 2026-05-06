"""TDD tests for the Task delegation hierarchy rule.

Hierarchy contract under test:

* Each member has an integer ``priority`` claim.
* Lower numbers represent higher rank: CEO = 1, ..., Agent = 5.
* A requester may delegate a task ONLY to a member whose numerical priority
  is *strictly greater* than their own (i.e. lower rank).

Concretely: an Agent (priority 5) attempting to assign work to the CEO
(priority 1) must be rejected with ``DelegationForbiddenError`` (-> HTTP 403
at the API boundary). Equal-priority delegations are also forbidden.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import DelegateTaskRequest, TaskResponse
from app.application.tasks.service import TaskService
from app.domain.enums import MemberType
from app.domain.exceptions import DelegationForbiddenError, TaskNotFoundError
from tests.auth.factories import make_agent, make_human
from tests.tasks.factories import make_principal, make_task


@pytest.fixture
def task_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def member_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(task_repo: AsyncMock, member_repo: AsyncMock) -> TaskService:
    return TaskService(tasks=task_repo, members=member_repo)


# ---------- success path ----------


async def test_ceo_can_delegate_to_manager(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    ceo = make_principal(workspace_id=workspace_id, priority=1)
    manager = make_human(workspace_id=workspace_id, priority=3, email="m@kanea.ai")
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = manager
    assigned = make_task(task_id=task.id, workspace_id=workspace_id, assignee_id=manager.id)
    task_repo.assign.return_value = assigned

    result = await service.delegate(task.id, DelegateTaskRequest(member_id=manager.id), ceo)

    assert isinstance(result, TaskResponse)
    assert result.id == task.id
    assert result.assignee_id == manager.id
    task_repo.assign.assert_awaited_once_with(task_id=task.id, assignee_id=manager.id)


async def test_manager_can_delegate_to_agent(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    manager = make_principal(workspace_id=workspace_id, priority=3)
    agent = make_agent(workspace_id=workspace_id, priority=5)
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = agent
    task_repo.assign.return_value = make_task(
        task_id=task.id, workspace_id=workspace_id, assignee_id=agent.id
    )

    result = await service.delegate(task.id, DelegateTaskRequest(member_id=agent.id), manager)

    assert result.assignee_id == agent.id


# ---------- the headline rule ----------


async def test_agent_cannot_delegate_to_ceo(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    """Agent (priority 5) -> CEO (priority 1) is the canonical forbidden case."""
    workspace_id = uuid4()
    agent = make_principal(
        workspace_id=workspace_id,
        member_type=MemberType.AGENT,
        priority=5,
        scope="agent",
    )
    ceo = make_human(workspace_id=workspace_id, priority=1, email="ceo@kanea.ai")
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = ceo

    with pytest.raises(DelegationForbiddenError):
        await service.delegate(task.id, DelegateTaskRequest(member_id=ceo.id), agent)

    task_repo.assign.assert_not_awaited()


@pytest.mark.parametrize(
    ("requester_priority", "target_priority"),
    [
        (5, 1),  # Agent -> CEO
        (5, 4),  # Agent -> Senior
        (3, 2),  # Manager -> Director
        (2, 1),  # Director -> CEO
    ],
)
async def test_higher_rank_target_is_rejected(
    service: TaskService,
    task_repo: AsyncMock,
    member_repo: AsyncMock,
    requester_priority: int,
    target_priority: int,
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=requester_priority)
    target = make_human(
        workspace_id=workspace_id,
        priority=target_priority,
        email=f"p{target_priority}@kanea.ai",
    )
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = target

    with pytest.raises(DelegationForbiddenError):
        await service.delegate(task.id, DelegateTaskRequest(member_id=target.id), requester)

    task_repo.assign.assert_not_awaited()


async def test_equal_priority_is_rejected(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    """Peers cannot delegate to peers — strict inequality is required."""
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=3)
    peer = make_human(workspace_id=workspace_id, priority=3, email="peer@kanea.ai")
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = peer

    with pytest.raises(DelegationForbiddenError):
        await service.delegate(task.id, DelegateTaskRequest(member_id=peer.id), requester)

    task_repo.assign.assert_not_awaited()


@pytest.mark.parametrize(
    ("requester_priority", "target_priority"),
    [
        (1, 2),  # CEO -> Director
        (1, 5),  # CEO -> Agent
        (3, 4),  # Manager -> Senior
        (4, 5),  # Senior -> Agent
    ],
)
async def test_lower_rank_target_is_allowed(
    service: TaskService,
    task_repo: AsyncMock,
    member_repo: AsyncMock,
    requester_priority: int,
    target_priority: int,
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=requester_priority)
    target = make_human(
        workspace_id=workspace_id,
        priority=target_priority,
        email=f"p{target_priority}@kanea.ai",
    )
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = target
    task_repo.assign.return_value = make_task(
        task_id=task.id, workspace_id=workspace_id, assignee_id=target.id
    )

    result = await service.delegate(task.id, DelegateTaskRequest(member_id=target.id), requester)

    assert result.assignee_id == target.id
    task_repo.assign.assert_awaited_once()


# ---------- agent-as-target is allowed when rank permits ----------


async def test_ceo_can_delegate_to_agent(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    """The hierarchy rule is rank-based, not type-based: a CEO may task an Agent."""
    workspace_id = uuid4()
    ceo = make_principal(workspace_id=workspace_id, priority=1)
    agent = make_agent(workspace_id=workspace_id, priority=5)
    task = make_task(workspace_id=workspace_id)
    task_repo.get_by_id.return_value = task
    member_repo.get_by_id.return_value = agent
    task_repo.assign.return_value = make_task(
        task_id=task.id, workspace_id=workspace_id, assignee_id=agent.id
    )

    result = await service.delegate(task.id, DelegateTaskRequest(member_id=agent.id), ceo)

    assert result.assignee_id == agent.id


# ---------- not-found and tenancy guards ----------


async def test_unknown_task_raises_not_found(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    requester = make_principal(priority=1)
    task_repo.get_by_id.return_value = None

    with pytest.raises(TaskNotFoundError):
        await service.delegate(uuid4(), DelegateTaskRequest(member_id=uuid4()), requester)

    member_repo.get_by_id.assert_not_awaited()


async def test_task_in_other_workspace_is_hidden(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    requester = make_principal(priority=1)
    foreign_task = make_task()  # different workspace_id
    task_repo.get_by_id.return_value = foreign_task

    with pytest.raises(TaskNotFoundError):
        await service.delegate(foreign_task.id, DelegateTaskRequest(member_id=uuid4()), requester)

    member_repo.get_by_id.assert_not_awaited()


async def test_unknown_assignee_raises_not_found(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task_repo.get_by_id.return_value = make_task(workspace_id=workspace_id)
    member_repo.get_by_id.return_value = None

    with pytest.raises(TaskNotFoundError):
        await service.delegate(uuid4(), DelegateTaskRequest(member_id=uuid4()), requester)

    task_repo.assign.assert_not_awaited()


async def test_assignee_in_other_workspace_is_hidden(
    service: TaskService, task_repo: AsyncMock, member_repo: AsyncMock
) -> None:
    workspace_id = uuid4()
    requester = make_principal(workspace_id=workspace_id, priority=1)
    task_repo.get_by_id.return_value = make_task(workspace_id=workspace_id)
    member_repo.get_by_id.return_value = make_human(priority=3)  # different workspace

    with pytest.raises(TaskNotFoundError):
        await service.delegate(uuid4(), DelegateTaskRequest(member_id=uuid4()), requester)

    task_repo.assign.assert_not_awaited()
