from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum  # noqa: N811
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import MemberRole, MemberType, OAuthProvider, TaskStatus
from app.infrastructure.db.base import Base, TimestampMixin

member_type_enum = PgEnum(
    MemberType,
    name="member_type",
    values_callable=lambda enum: [member.value for member in enum],
    create_type=True,
)

member_role_enum = PgEnum(
    MemberRole,
    name="member_role",
    values_callable=lambda enum: [member.value for member in enum],
    create_type=True,
)

task_status_enum = PgEnum(
    TaskStatus,
    name="task_status",
    values_callable=lambda enum: [member.value for member in enum],
    create_type=True,
)

oauth_provider_enum = PgEnum(
    OAuthProvider,
    name="oauth_provider",
    values_callable=lambda enum: [member.value for member in enum],
    create_type=True,
)


class WorkspaceModel(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)

    teams: Mapped[list[TeamModel]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    members: Mapped[list[MemberModel]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[TaskModel]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class TeamModel(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_teams_workspace_id_name"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="teams")
    members: Mapped[list[MemberModel]] = relationship(back_populates="team")


class MemberModel(TimestampMixin, Base):
    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "email", name="uq_members_workspace_id_email"),
        CheckConstraint(
            "(type = 'HUMAN' AND email IS NOT NULL) OR (type = 'AGENT')",
            name="human_must_have_email",
        ),
        Index("ix_members_workspace_id_type", "workspace_id", "type"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[MemberType] = mapped_column(member_type_enum, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[MemberRole] = mapped_column(
        member_role_enum, nullable=False, default=MemberRole.MEMBER
    )

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="members")
    team: Mapped[TeamModel | None] = relationship(back_populates="members")
    credentials: Mapped[CredentialsModel | None] = relationship(
        back_populates="member",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CredentialsModel(TimestampMixin, Base):
    __tablename__ = "credentials"
    __table_args__ = (
        CheckConstraint(
            (
                "password_hash IS NOT NULL "
                "OR agent_secret_hash IS NOT NULL "
                "OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)"
            ),
            name="at_least_one_secret",
        ),
        UniqueConstraint(
            "oauth_provider", "oauth_id", name="uq_credentials_oauth_provider_oauth_id"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[OAuthProvider | None] = mapped_column(oauth_provider_enum, nullable=True)
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    member: Mapped[MemberModel] = relationship(back_populates="credentials")


class TaskModel(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_workspace_id_status", "workspace_id", "status"),
        Index("ix_tasks_assignee_id_status", "assignee_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        task_status_enum, nullable=False, default=TaskStatus.PENDING
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    workspace: Mapped[WorkspaceModel] = relationship(back_populates="tasks")
    creator: Mapped[MemberModel] = relationship(foreign_keys=[created_by_id])
    assignee: Mapped[MemberModel | None] = relationship(foreign_keys=[assignee_id])


class InviteModel(TimestampMixin, Base):
    __tablename__ = "invites"
    __table_args__ = (Index("ix_invites_workspace_id_email", "workspace_id", "email"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invited_by_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[MemberRole] = mapped_column(member_role_enum, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
