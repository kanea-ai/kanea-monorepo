from __future__ import annotations

from unittest.mock import MagicMock

from app.api.deps import (
    get_agent_api_key_repository,
    get_audit_log_repository,
    get_audit_log_service,
    get_auth_service,
    get_credentials_repository,
    get_department_repository,
    get_department_service,
    get_member_repository,
    get_password_hasher,
    get_settings,
    get_team_repository,
    get_team_service,
    get_token_service,
    get_user_repository,
    get_workspace_repository,
)
from app.application.audit.service import AuditLogService
from app.application.auth.service import AuthService
from app.application.departments.service import DepartmentService
from app.application.teams.service import TeamService
from app.core.config import Settings
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialsRepository
from app.infrastructure.repositories.department import SqlAlchemyDepartmentRepository
from app.infrastructure.repositories.member import SqlAlchemyMemberRepository
from app.infrastructure.repositories.workspace import SqlAlchemyWorkspaceRepository
from app.infrastructure.security.password import BcryptPasswordHasher
from app.infrastructure.security.tokens import JwtTokenService


def test_get_settings_returns_settings_instance() -> None:
    config = get_settings()
    assert isinstance(config, Settings)


def test_get_password_hasher_is_singleton() -> None:
    a = get_password_hasher()
    b = get_password_hasher()
    assert isinstance(a, BcryptPasswordHasher)
    assert a is b


def test_get_token_service_uses_settings() -> None:
    config = get_settings()
    service = get_token_service(config)
    assert isinstance(service, JwtTokenService)


def test_get_member_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_member_repository(session)
    assert isinstance(repo, SqlAlchemyMemberRepository)


def test_get_credentials_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_credentials_repository(session)
    assert isinstance(repo, SqlAlchemyCredentialsRepository)


def test_get_workspace_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_workspace_repository(session)
    assert isinstance(repo, SqlAlchemyWorkspaceRepository)


def test_get_department_repository_wraps_session() -> None:
    session = MagicMock()
    repo = get_department_repository(session)
    assert isinstance(repo, SqlAlchemyDepartmentRepository)


def test_get_audit_log_service_wires_dependencies() -> None:
    session = MagicMock()
    service = get_audit_log_service(
        audit_logs=get_audit_log_repository(session),
        members=get_member_repository(session),
        teams=get_team_repository(session),
    )
    assert isinstance(service, AuditLogService)


def test_get_department_service_wires_dependencies() -> None:
    session = MagicMock()
    audit_logs = get_audit_log_service(
        audit_logs=get_audit_log_repository(session),
        members=get_member_repository(session),
        teams=get_team_repository(session),
    )
    service = get_department_service(
        departments=get_department_repository(session),
        audit_logs=audit_logs,
        members=get_member_repository(session),
    )
    assert isinstance(service, DepartmentService)


def test_get_team_service_wires_dependencies() -> None:
    """The team service now depends on the department repo for
    cross-tenant validation of department_id and the audit log
    service for org-event recording; the factory threads both."""
    session = MagicMock()
    audit_logs = get_audit_log_service(
        audit_logs=get_audit_log_repository(session),
        members=get_member_repository(session),
        teams=get_team_repository(session),
    )
    service = get_team_service(
        teams=get_team_repository(session),
        departments=get_department_repository(session),
        audit_logs=audit_logs,
    )
    assert isinstance(service, TeamService)


def test_get_auth_service_wires_dependencies() -> None:
    session = MagicMock()
    config = get_settings()
    service = get_auth_service(
        workspaces=get_workspace_repository(session),
        members=get_member_repository(session),
        credentials=get_credentials_repository(session),
        hasher=get_password_hasher(),
        tokens=get_token_service(config),
        users=get_user_repository(session),
        agent_api_keys=get_agent_api_key_repository(session),
    )
    assert isinstance(service, AuthService)
