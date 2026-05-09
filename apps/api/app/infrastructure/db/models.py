from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
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

from app.domain.enums import (
    MemberRole,
    MemberType,
    OAuthProvider,
    ProjectStatus,
    TaskRelationType,
    TaskStatus,
)
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

task_relation_type_enum = PgEnum(
    TaskRelationType,
    name="task_relation_type",
    values_callable=lambda enum: [member.value for member in enum],
    # Created in migration 0009 alongside the table.
    create_type=False,
)

project_status_enum = PgEnum(
    ProjectStatus,
    name="project_status",
    values_callable=lambda enum: [member.value for member in enum],
    # Created in migration 0010 alongside the table.
    create_type=False,
)


class WorkspaceModel(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    task_prefix: Mapped[str] = mapped_column(String(8), nullable=False, default="TASK")
    next_task_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

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


class ProjectModel(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_projects_workspace_id_name"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        project_status_enum, nullable=False, default=ProjectStatus.ACTIVE
    )


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
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
        Index("uq_tasks_workspace_id_seq", "workspace_id", "seq", unique=True),
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
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Optional Workspace -> Project -> Task -> Team links. Both SET NULL
    # on parent delete so the task survives a project/team removal.
    project_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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


class TaskCommentModel(TimestampMixin, Base):
    __tablename__ = "task_comments"
    __table_args__ = (Index("ix_task_comments_task_id_created_at", "task_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Author can be null after the member is deleted (FK SET NULL); the
    # comment body still survives so the conversation history reads.
    author_member_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class TaskRelationModel(TimestampMixin, Base):
    __tablename__ = "task_relations"
    __table_args__ = (
        CheckConstraint(
            "source_task_id <> target_task_id",
            name="task_relations_no_self_link",
        ),
        UniqueConstraint(
            "source_task_id",
            "target_task_id",
            "relation_type",
            name="uq_task_relations_source_target_type",
        ),
        Index("ix_task_relations_target_type", "target_task_id", "relation_type"),
        Index("ix_task_relations_source_type", "source_task_id", "relation_type"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_task_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_task_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[TaskRelationType] = mapped_column(task_relation_type_enum, nullable=False)


class TaskRatingModel(TimestampMixin, Base):
    __tablename__ = "task_ratings"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_task_ratings_rated_member_id", "rated_member_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    rated_by_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rated_member_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
