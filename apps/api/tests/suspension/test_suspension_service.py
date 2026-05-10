"""Service-level tests for InviteService.set_member_suspension.

Contract:
- WORKSPACE_OWNER / WORKSPACE_ADMIN can suspend a peer.
- Plain MEMBER role is rejected.
- Cross-tenant member id 404s.
- A principal cannot suspend themselves.
- Suspending the last *active* WORKSPACE_OWNER is rejected.
- Revoke (is_suspended=false) is always allowed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import SetMemberSuspensionRequest
from app.application.tenants.service import InviteService
from app.domain.entities import Member
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import ForbiddenError, InvalidMemberTypeError


def _principal(
    *,
    role: MemberRole = MemberRole.WORKSPACE_OWNER,
    workspace_id=None,
    member_id=None,
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1 if role is MemberRole.WORKSPACE_OWNER else 5,
        scope="human",
        role=role,
    )


def _member(
    workspace_id, *, role: MemberRole = MemberRole.WORKSPACE_USER, suspended=False
) -> Member:
    now = datetime.now(UTC)
    return Member(
        id=uuid4(),
        workspace_id=workspace_id,
        type=MemberType.HUMAN,
        name="Alice",
        email="a@example.com",
        priority=3,
        role=role,
        is_suspended=suspended,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def members_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(members_repo: AsyncMock) -> InviteService:
    return InviteService(
        invites=AsyncMock(),
        members=members_repo,
        workspaces=AsyncMock(),
        auth_members=AsyncMock(),
        credentials=AsyncMock(),
        hasher=AsyncMock(),
        tokens=AsyncMock(),
        accept_url_base="http://example",
    )


# ---------- RBAC ----------


async def test_member_role_cannot_suspend(service: InviteService, members_repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    members_repo.get_by_id.return_value = _member(p.workspace_id)
    with pytest.raises(ForbiddenError):
        await service.set_member_suspension(
            uuid4(), SetMemberSuspensionRequest(is_suspended=True), p
        )
    members_repo.set_suspended.assert_not_called()


async def test_admin_can_suspend(service: InviteService, members_repo: AsyncMock) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    target = _member(p.workspace_id)
    members_repo.get_by_id.return_value = target
    members_repo.set_suspended.return_value = target

    await service.set_member_suspension(target.id, SetMemberSuspensionRequest(is_suspended=True), p)
    members_repo.set_suspended.assert_awaited_once_with(target.id, is_suspended=True)


# ---------- tenant isolation ----------


async def test_cross_tenant_member_404s(service: InviteService, members_repo: AsyncMock) -> None:
    p = _principal()
    members_repo.get_by_id.return_value = _member(uuid4())  # other workspace
    with pytest.raises(InvalidMemberTypeError):
        await service.set_member_suspension(
            uuid4(), SetMemberSuspensionRequest(is_suspended=True), p
        )


# ---------- self-suspend protection ----------


async def test_principal_cannot_suspend_self(
    service: InviteService, members_repo: AsyncMock
) -> None:
    p = _principal()
    self_member = _member(p.workspace_id)
    # Pin self_member.id to the principal to simulate "self-suspend".
    self_member.id = p.member_id
    members_repo.get_by_id.return_value = self_member
    with pytest.raises(ForbiddenError):
        await service.set_member_suspension(
            p.member_id, SetMemberSuspensionRequest(is_suspended=True), p
        )


async def test_principal_can_revoke_self(service: InviteService, members_repo: AsyncMock) -> None:
    """Revoke is always safe — even revoking your own suspension
    (admins can recover from accidental self-state)."""
    p = _principal()
    self_member = _member(p.workspace_id, suspended=True)
    self_member.id = p.member_id
    members_repo.get_by_id.return_value = self_member
    members_repo.set_suspended.return_value = self_member
    members_repo.list_for_workspace.return_value = ([], len([]))

    await service.set_member_suspension(
        p.member_id, SetMemberSuspensionRequest(is_suspended=False), p
    )
    members_repo.set_suspended.assert_awaited_once_with(p.member_id, is_suspended=False)


# ---------- last-owner protection ----------


async def test_cannot_suspend_last_active_owner(
    service: InviteService, members_repo: AsyncMock
) -> None:
    p = _principal()
    only_owner = _member(p.workspace_id, role=MemberRole.WORKSPACE_OWNER)
    members_repo.get_by_id.return_value = only_owner
    members_repo.list_for_workspace.return_value = ([only_owner], len([only_owner]))
    with pytest.raises(ForbiddenError):
        await service.set_member_suspension(
            only_owner.id, SetMemberSuspensionRequest(is_suspended=True), p
        )
    members_repo.set_suspended.assert_not_called()


async def test_can_suspend_owner_when_another_active_owner_remains(
    service: InviteService, members_repo: AsyncMock
) -> None:
    p = _principal()
    target_owner = _member(p.workspace_id, role=MemberRole.WORKSPACE_OWNER)
    other_owner = _member(p.workspace_id, role=MemberRole.WORKSPACE_OWNER)
    members_repo.get_by_id.return_value = target_owner
    members_repo.list_for_workspace.return_value = (
        [target_owner, other_owner],
        len([target_owner, other_owner]),
    )
    members_repo.set_suspended.return_value = target_owner

    await service.set_member_suspension(
        target_owner.id, SetMemberSuspensionRequest(is_suspended=True), p
    )
    members_repo.set_suspended.assert_awaited_once_with(target_owner.id, is_suspended=True)


async def test_already_suspended_owner_does_not_count_as_active(
    service: InviteService, members_repo: AsyncMock
) -> None:
    """If the only "other" owner is already suspended, the workspace
    has no active owner path apart from the target — so suspending the
    target must be refused."""
    p = _principal()
    target_owner = _member(p.workspace_id, role=MemberRole.WORKSPACE_OWNER)
    other_owner = _member(p.workspace_id, role=MemberRole.WORKSPACE_OWNER, suspended=True)
    members_repo.get_by_id.return_value = target_owner
    members_repo.list_for_workspace.return_value = (
        [target_owner, other_owner],
        len([target_owner, other_owner]),
    )
    with pytest.raises(ForbiddenError):
        await service.set_member_suspension(
            target_owner.id, SetMemberSuspensionRequest(is_suspended=True), p
        )
