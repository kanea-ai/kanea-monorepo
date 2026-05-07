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
    *, role: MemberRole = MemberRole.OWNER, workspace_id=None, member_id=None
) -> Principal:
    return Principal(
        member_id=member_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        type=MemberType.HUMAN,
        priority=1 if role is MemberRole.OWNER else 5,
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
def service(
    invites: AsyncMock,
    tenant_members: AsyncMock,
    workspaces: AsyncMock,
    auth_members: AsyncMock,
    credentials: AsyncMock,
    hasher: MagicMock,
    tokens: MagicMock,
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
    )


# ---------- create_invite ----------


async def test_create_invite_owner_can_invite(service: InviteService, invites: AsyncMock) -> None:
    invites.create.side_effect = lambda i: i
    principal = _principal(role=MemberRole.OWNER)

    response = await service.create_invite(
        InviteCreateRequest(email="bob@kanea.ai", role=MemberRole.MEMBER), principal
    )

    assert response.email == "bob@kanea.ai"
    assert response.role is MemberRole.MEMBER
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
    principal = _principal(role=MemberRole.ADMIN)
    response = await service.create_invite(InviteCreateRequest(email="bob@kanea.ai"), principal)
    assert response.email == "bob@kanea.ai"


async def test_create_invite_member_forbidden(service: InviteService) -> None:
    principal = _principal(role=MemberRole.MEMBER)
    with pytest.raises(ForbiddenError):
        await service.create_invite(InviteCreateRequest(email="bob@kanea.ai"), principal)


async def test_create_invite_owner_role_rejected(service: InviteService) -> None:
    """OWNER must be created via signup, never via invite — the schema's
    is_role_inviteable() check is enforced at the service layer too."""
    principal = _principal(role=MemberRole.OWNER)
    with pytest.raises(ForbiddenError, match="OWNER"):
        await service.create_invite(
            InviteCreateRequest(email="bob@kanea.ai", role=MemberRole.OWNER),
            principal,
        )


# ---------- get_invite_preview ----------


def _active_invite(**overrides) -> Invite:
    base = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "invited_by_id": uuid4(),
        "email": "bob@kanea.ai",
        "role": MemberRole.MEMBER,
        "token_hash": "ignored-by-mocks",
        "expires_at": datetime.utcnow() + timedelta(days=3),
        "accepted_at": None,
    }
    base.update(overrides)
    return Invite(**base)


def _workspace(name: str = "Acme") -> Workspace:
    now = datetime.utcnow()
    return Workspace(id=uuid4(), name=name, slug="acme-abc123", created_at=now, updated_at=now)


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
    assert preview.role is MemberRole.MEMBER


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


async def test_accept_invite_creates_member_and_credentials(
    service: InviteService,
    invites: AsyncMock,
    auth_members: AsyncMock,
    credentials: AsyncMock,
    tokens: MagicMock,
) -> None:
    invite = _active_invite(role=MemberRole.ADMIN)
    invites.get_by_token_hash.return_value = invite
    auth_members.get_by_email.return_value = None
    auth_members.create.side_effect = lambda m: m
    credentials.create.side_effect = lambda c: c
    invites.mark_accepted.return_value = invite

    response = await service.accept_invite(
        "raw",
        InviteAcceptRequest(full_name="Bob", password="hunter2hunter2"),  # pragma: allowlist secret
    )

    assert response.access_token == "human.jwt"

    # Member created with the invited role + workspace.
    auth_members.create.assert_awaited_once()
    created = auth_members.create.await_args.args[0]
    assert created.workspace_id == invite.workspace_id
    assert created.email == invite.email
    assert created.role is MemberRole.ADMIN
    assert created.type is MemberType.HUMAN

    # Credentials carry hashed password (not plaintext).
    credentials.create.assert_awaited_once()
    creds = credentials.create.await_args.args[0]
    assert creds.member_id == created.id
    assert creds.password_hash == "bcrypt$hunter2hunter2"  # pragma: allowlist secret

    # Invite is consumed.
    invites.mark_accepted.assert_awaited_once_with(invite.id)


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


async def test_list_members_filters_to_principal_workspace(
    service: InviteService, tenant_members: AsyncMock
) -> None:
    p = _principal(role=MemberRole.OWNER)
    tenant_members.list_for_workspace.return_value = []
    await service.list_workspace_members(p)
    tenant_members.list_for_workspace.assert_awaited_once_with(p.workspace_id)
