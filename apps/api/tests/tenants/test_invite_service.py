from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.tasks.schemas import Principal
from app.application.tenants.schemas import (
    InviteAcceptRequest,
    InviteCreateRequest,
)
from app.application.tenants.service import INVITE_TTL_DAYS, InviteService, _hash_token
from app.domain.entities import Invite, Workspace
from app.domain.enums import MemberRole, MemberType
from app.domain.exceptions import (
    EmailAlreadyExistsError,
    ForbiddenError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteNotFoundError,
)
from tests.auth.factories import make_human


def _principal(
    *, role: MemberRole = MemberRole.WORKSPACE_OWNER, workspace_id=None, member_id=None
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1 if role is MemberRole.WORKSPACE_OWNER else 5,
        scope="human",
        role=role,
    )


@pytest.fixture
def invites() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def tenant_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def workspaces() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_members() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def credentials() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def hasher() -> MagicMock:
    h = MagicMock()
    h.hash.side_effect = lambda raw: f"bcrypt${raw}"
    return h


@pytest.fixture
def tokens() -> MagicMock:
    t = MagicMock()
    t.issue_human_token.return_value = ("human.jwt", 3600)
    return t


@pytest.fixture
def users() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    invites: AsyncMock,
    tenant_members: AsyncMock,
    workspaces: AsyncMock,
    auth_members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
    users: AsyncMock,
) -> InviteService:
    return InviteService(
        invites=invites,
        members=tenant_members,
        workspaces=workspaces,
        auth_members=auth_members,
        credentials=credentials,
        hasher=hasher,
        tokens=tokens,
        accept_url_base="https://app.kanea.ai",
        users=users,
    )


# ---------- create_invite ----------


async def test_create_invite_owner_can_invite(service: InviteService, invites: AsyncMock) -> None:
    invites.create.side_effect = lambda i: i
    principal = _principal(role=MemberRole.WORKSPACE_OWNER)

    response = await service.create_invite(
        InviteCreateRequest(email="bob@kanea.ai", role=MemberRole.WORKSPACE_USER), principal
    )

    assert response.email == "bob@kanea.ai"
    assert response.role is MemberRole.WORKSPACE_USER
    assert response.workspace_id == principal.workspace_id
    # Raw token leaks once; the URL embeds it.
    assert response.token
    assert response.accept_url == f"https://app.kanea.ai/invite/{response.token}"
    # Expiry is roughly TTL_DAYS in the future. Service uses naive UTC
    # internally; comparing in the same shape avoids tz mismatch.
    now = datetime.utcnow()
    assert response.expires_at > now
    assert response.expires_at < now + timedelta(days=INVITE_TTL_DAYS + 1)

    # Persisted invite stores the hash, not the raw token.
    invites.create.assert_awaited_once()
    persisted: Invite = invites.create.await_args.args[0]
    assert persisted.token_hash == _hash_token(response.token)
    assert persisted.workspace_id == principal.workspace_id
    assert persisted.invited_by_id == principal.member_id


async def test_create_invite_admin_can_invite(service: InviteService, invites: AsyncMock) -> None:
    invites.create.side_effect = lambda i: i
    principal = _principal(role=MemberRole.WORKSPACE_ADMIN)
    response = await service.create_invite(InviteCreateRequest(email="bob@kanea.ai"), principal)
    assert response.email == "bob@kanea.ai"


async def test_create_invite_member_forbidden(service: InviteService) -> None:
    principal = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.create_invite(InviteCreateRequest(email="bob@kanea.ai"), principal)


async def test_create_invite_owner_role_rejected(service: InviteService) -> None:
    """OWNER must be created via signup, never via invite — the schema's
    is_role_inviteable() check is enforced at the service layer too."""
    principal = _principal(role=MemberRole.WORKSPACE_OWNER)
    with pytest.raises(ForbiddenError, match="OWNER"):
        await service.create_invite(
            InviteCreateRequest(email="bob@kanea.ai", role=MemberRole.WORKSPACE_OWNER),
            principal,
        )


# ---------- get_invite_preview ----------


def _active_invite(**overrides) -> Invite:
    base = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "invited_by_id": uuid4(),
        "email": "bob@kanea.ai",
        "role": MemberRole.WORKSPACE_USER,
        "token_hash": "ignored-by-mocks",
        "expires_at": datetime.utcnow() + timedelta(days=3),
        "accepted_at": None,
    }
    base.update(overrides)
    return Invite(**base)


def _workspace(name: str = "Acme") -> Workspace:
    now = datetime.utcnow()
    return Workspace(
        id=uuid4(),
        name=name,
        slug="acme-abc123",
        task_prefix="ACME",
        next_task_seq=1,
        created_at=now,
        updated_at=now,
    )


async def test_preview_returns_workspace_summary(
    service: InviteService, invites: AsyncMock, workspaces: AsyncMock
) -> None:
    invite = _active_invite()
    workspace = _workspace(name="Acme Corp")
    invites.get_by_token_hash.return_value = invite
    workspaces.get_by_id.return_value = workspace

    preview = await service.get_invite_preview("the-raw-token")

    assert preview.workspace_name == "Acme Corp"
    assert preview.email == invite.email
    assert preview.role is MemberRole.WORKSPACE_USER


async def test_preview_unknown_token(service: InviteService, invites: AsyncMock) -> None:
    invites.get_by_token_hash.return_value = None
    with pytest.raises(InviteNotFoundError):
        await service.get_invite_preview("nope")


async def test_preview_expired(service: InviteService, invites: AsyncMock) -> None:
    invites.get_by_token_hash.return_value = _active_invite(
        expires_at=datetime.utcnow() - timedelta(seconds=1)
    )
    with pytest.raises(InviteExpiredError):
        await service.get_invite_preview("expired")


async def test_preview_already_accepted(service: InviteService, invites: AsyncMock) -> None:
    invites.get_by_token_hash.return_value = _active_invite(accepted_at=datetime.utcnow())
    with pytest.raises(InviteAlreadyAcceptedError):
        await service.get_invite_preview("used")


# ---------- accept_invite ----------


async def test_accept_invite_creates_user_and_member(
    service: InviteService,
    invites: AsyncMock,
    auth_members: AsyncMock,
    users: AsyncMock,
    tokens: MagicMock,
) -> None:
    """Phase 1: invite acceptance creates a global User + a Member
    linked to it. No more credentials row for human auth — that lives
    on users now."""
    invite = _active_invite(role=MemberRole.WORKSPACE_ADMIN)
    invites.get_by_token_hash.return_value = invite
    auth_members.get_by_email.return_value = None
    users.get_by_email.return_value = None  # brand-new user
    users.create.side_effect = lambda u: u
    auth_members.create.side_effect = lambda m: m
    invites.mark_accepted.return_value = invite

    response = await service.accept_invite(
        "raw",
        InviteAcceptRequest(full_name="Bob", password="hunter2hunter2"),  # pragma: allowlist secret
    )
    assert response.access_token == "human.jwt"

    # Global User created with the hashed password.
    users.create.assert_awaited_once()
    created_user = users.create.await_args.args[0]
    assert created_user.email == invite.email
    assert created_user.password_hash == "bcrypt$hunter2hunter2"  # pragma: allowlist secret

    # Member links to that user, carries the invited role.
    auth_members.create.assert_awaited_once()
    created_member = auth_members.create.await_args.args[0]
    assert created_member.workspace_id == invite.workspace_id
    assert created_member.user_id == created_user.id
    assert created_member.role is MemberRole.WORKSPACE_ADMIN
    assert created_member.type is MemberType.HUMAN
    invites.mark_accepted.assert_awaited_once_with(invite.id)


async def test_accept_invite_links_to_existing_user(
    service: InviteService,
    invites: AsyncMock,
    auth_members: AsyncMock,
    users: AsyncMock,
) -> None:
    """If the invitee's email already has a User from another
    workspace, accept just creates a new Member pointing at that user
    — without resetting the password."""
    invite = _active_invite()
    invites.get_by_token_hash.return_value = invite
    auth_members.get_by_email.return_value = None

    from datetime import UTC, datetime

    from app.domain.entities import User as UserEntity

    existing = UserEntity(
        id=uuid4(),
        email=invite.email,
        full_name="Bob",
        password_hash="bcrypt$existing",  # pragma: allowlist secret
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    users.get_by_email.return_value = existing
    auth_members.create.side_effect = lambda m: m
    invites.mark_accepted.return_value = invite

    await service.accept_invite(
        "raw",
        InviteAcceptRequest(full_name="Bob", password="ignored-pwd!!"),  # pragma: allowlist secret
    )
    # No user was created — the existing one is reused.
    users.create.assert_not_called()
    created_member = auth_members.create.await_args.args[0]
    assert created_member.user_id == existing.id


async def test_accept_invite_rejects_when_email_already_in_workspace(
    service: InviteService, invites: AsyncMock, auth_members: AsyncMock
) -> None:
    invite = _active_invite()
    invites.get_by_token_hash.return_value = invite
    # Existing member with the same email AND same workspace.
    auth_members.get_by_email.return_value = make_human(
        email=invite.email, workspace_id=invite.workspace_id
    )

    with pytest.raises(EmailAlreadyExistsError):
        await service.accept_invite(
            "raw",
            InviteAcceptRequest(full_name="Bob", password="abcdefgh"),  # pragma: allowlist secret
        )


# ---------- list_workspace_members ----------


async def test_list_members_admin_sees_everyone(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    """OWNER/ADMIN principals get the workspace-wide listing — no
    visibility scoping is layered on the repo call."""
    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    tenant_members.list_for_workspace.return_value = []
    await service.list_workspace_members(p)
    tenant_members.list_for_workspace.assert_awaited_once_with(
        p.workspace_id,
        name=None,
        member_id=None,
        role=None,
        team_id=None,
        project_id=None,
        humans_only=False,
        visibility_team_id=None,
        visibility_self_id=None,
    )


async def test_list_members_passes_filters_through(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.application.tenants.schemas import MemberFilters

    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    tenant_members.list_for_workspace.return_value = []
    project_id = uuid4()
    team_id = uuid4()
    await service.list_workspace_members(
        p,
        MemberFilters(
            name="al",
            role=MemberRole.WORKSPACE_USER,
            team_id=team_id,
            project_id=project_id,
            humans_only=True,
        ),
    )
    tenant_members.list_for_workspace.assert_awaited_once_with(
        p.workspace_id,
        name="al",
        member_id=None,
        role=MemberRole.WORKSPACE_USER,
        team_id=team_id,
        project_id=project_id,
        humans_only=True,
        visibility_team_id=None,
        visibility_self_id=None,
    )


async def test_list_members_non_admin_scoped_to_team(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    """A regular MEMBER who's on a team sees teammates + themselves."""
    p = _principal(role=MemberRole.WORKSPACE_USER)
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.team_id = uuid4()
    tenant_members.get_by_id.return_value = self_member
    tenant_members.list_for_workspace.return_value = []

    await service.list_workspace_members(p)
    call = tenant_members.list_for_workspace.await_args
    assert call.kwargs["visibility_team_id"] == self_member.team_id
    assert call.kwargs["visibility_self_id"] == p.member_id


async def test_list_members_non_admin_no_team_self_only(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    """A regular MEMBER who isn't on a team sees only themselves."""
    p = _principal(role=MemberRole.WORKSPACE_USER)
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.team_id = None
    tenant_members.get_by_id.return_value = self_member
    tenant_members.list_for_workspace.return_value = []

    await service.list_workspace_members(p)
    call = tenant_members.list_for_workspace.await_args
    assert call.kwargs["visibility_team_id"] is None
    assert call.kwargs["visibility_self_id"] == p.member_id


# ---------- get_member ----------


async def test_get_member_admin_sees_anyone_in_workspace(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    target = make_human(workspace_id=p.workspace_id)
    tenant_members.get_by_id.return_value = target
    out = await service.get_member(target.id, p)
    assert out.id == target.id


async def test_get_member_non_admin_can_fetch_self(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    p = _principal(role=MemberRole.WORKSPACE_USER)
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    tenant_members.get_by_id.return_value = self_member
    out = await service.get_member(p.member_id, p)
    assert out.id == p.member_id


async def test_get_member_non_admin_can_fetch_teammate(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.domain.exceptions import ForbiddenError

    p = _principal(role=MemberRole.WORKSPACE_USER)
    team_id = uuid4()
    teammate = make_human(workspace_id=p.workspace_id)
    teammate.team_id = team_id
    self_member = make_human(member_id=p.member_id, workspace_id=p.workspace_id)
    self_member.team_id = team_id
    # First lookup is the target (teammate); second is "self".
    tenant_members.get_by_id.side_effect = [teammate, self_member]
    out = await service.get_member(teammate.id, p)
    assert out.id == teammate.id

    # Stranger (different team) -> ForbiddenError.
    stranger = make_human(workspace_id=p.workspace_id)
    stranger.team_id = uuid4()
    tenant_members.get_by_id.side_effect = [stranger, self_member]
    with pytest.raises(ForbiddenError):
        await service.get_member(stranger.id, p)


async def test_get_member_cross_workspace_404s(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.domain.exceptions import InvalidMemberTypeError

    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    foreign = make_human()  # different workspace_id
    tenant_members.get_by_id.return_value = foreign
    with pytest.raises(InvalidMemberTypeError):
        await service.get_member(foreign.id, p)


# ---------- update_member_profile ----------


async def test_update_member_profile_admin_can_rename(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.application.tenants.schemas import UpdateMemberProfileRequest

    p = _principal(role=MemberRole.WORKSPACE_ADMIN)
    target = make_human(workspace_id=p.workspace_id)
    tenant_members.get_by_id.return_value = target
    tenant_members.update_profile.return_value = target

    await service.update_member_profile(target.id, UpdateMemberProfileRequest(name="Renamed"), p)
    tenant_members.update_profile.assert_awaited_once_with(
        target.id, name="Renamed", role=None, priority=None
    )


async def test_update_member_profile_member_forbidden(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.application.tenants.schemas import UpdateMemberProfileRequest
    from app.domain.exceptions import ForbiddenError

    p = _principal(role=MemberRole.WORKSPACE_USER)
    with pytest.raises(ForbiddenError):
        await service.update_member_profile(uuid4(), UpdateMemberProfileRequest(name="x"), p)


async def test_update_member_profile_blocks_demoting_last_owner(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.application.tenants.schemas import UpdateMemberProfileRequest
    from app.domain.exceptions import ForbiddenError

    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = make_human(workspace_id=p.workspace_id)
    target.role = MemberRole.WORKSPACE_OWNER
    tenant_members.get_by_id.return_value = target
    # Only the target is an OWNER -> demoting would leave none.
    tenant_members.list_for_workspace.return_value = [target]

    with pytest.raises(ForbiddenError, match="last workspace owner"):
        await service.update_member_profile(
            target.id,
            UpdateMemberProfileRequest(role=MemberRole.WORKSPACE_ADMIN),
            p,
        )


async def test_update_member_profile_demotion_ok_when_other_owner_exists(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    from app.application.tenants.schemas import UpdateMemberProfileRequest

    p = _principal(role=MemberRole.WORKSPACE_OWNER)
    target = make_human(workspace_id=p.workspace_id)
    target.role = MemberRole.WORKSPACE_OWNER
    other_owner = make_human(workspace_id=p.workspace_id)
    other_owner.role = MemberRole.WORKSPACE_OWNER
    tenant_members.get_by_id.return_value = target
    tenant_members.list_for_workspace.return_value = [target, other_owner]
    tenant_members.update_profile.return_value = target

    await service.update_member_profile(
        target.id,
        UpdateMemberProfileRequest(role=MemberRole.WORKSPACE_ADMIN),
        p,
    )
    tenant_members.update_profile.assert_awaited_once()
