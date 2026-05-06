"""initial schema: workspaces, teams, members, credentials, tasks

Revision ID: 0001
Revises:
Create Date: 2026-05-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


member_type = postgresql.ENUM("HUMAN", "AGENT", name="member_type", create_type=False)
task_status = postgresql.ENUM(
    "PENDING", "IN_PROGRESS", "DONE", "CANCELLED", name="task_status", create_type=False
)


def upgrade() -> None:
    member_type.create(op.get_bind(), checkfirst=True)
    task_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id",
                ondelete="CASCADE",
                name="fk_teams_workspace_id_workspaces",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_teams_workspace_id_name"),
    )
    op.create_index("ix_teams_workspace_id", "teams", ["workspace_id"], unique=False)

    op.create_table(
        "members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id", ondelete="CASCADE", name="fk_members_workspace_id_workspaces"
            ),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL", name="fk_members_team_id_teams"),
            nullable=True,
        ),
        sa.Column("type", member_type, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_id", "email", name="uq_members_workspace_id_email"),
        sa.CheckConstraint(
            "(type = 'HUMAN' AND email IS NOT NULL) OR (type = 'AGENT')",
            name="ck_members_human_must_have_email",
        ),
    )
    op.create_index("ix_members_team_id", "members", ["team_id"], unique=False)
    op.create_index("ix_members_email", "members", ["email"], unique=False)
    op.create_index(
        "ix_members_workspace_id_type", "members", ["workspace_id", "type"], unique=False
    )

    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "members.id", ondelete="CASCADE", name="fk_credentials_member_id_members"
            ),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("agent_secret_hash", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("member_id", name="uq_credentials_member_id"),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR agent_secret_hash IS NOT NULL",
            name="ck_credentials_at_least_one_secret",
        ),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id", ondelete="CASCADE", name="fk_tasks_workspace_id_workspaces"
            ),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT", name="fk_tasks_created_by_id_members"),
            nullable=False,
        ),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL", name="fk_tasks_assignee_id_members"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", task_status, nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_tasks_workspace_id_status", "tasks", ["workspace_id", "status"], unique=False
    )
    op.create_index("ix_tasks_assignee_id_status", "tasks", ["assignee_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_assignee_id_status", table_name="tasks")
    op.drop_index("ix_tasks_workspace_id_status", table_name="tasks")
    op.drop_table("tasks")

    op.drop_table("credentials")

    op.drop_index("ix_members_workspace_id_type", table_name="members")
    op.drop_index("ix_members_email", table_name="members")
    op.drop_index("ix_members_team_id", table_name="members")
    op.drop_table("members")

    op.drop_index("ix_teams_workspace_id", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_table("workspaces")

    bind = op.get_bind()
    task_status.drop(bind, checkfirst=True)
    member_type.drop(bind, checkfirst=True)
