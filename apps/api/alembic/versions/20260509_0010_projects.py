"""projects table + tasks.project_id/team_id

Establishes the Workspace -> Project -> Task -> Team hierarchy:

* projects (workspace-scoped) hold a name, description, and status
  (ACTIVE / ARCHIVED). Tasks can optionally belong to a project.
* tasks gain a nullable project_id (SET NULL on project delete so
  tasks survive a project removal) and a nullable team_id (SET NULL
  on team delete). Both are optional at the data layer — backlog
  tasks live without a project, and a task can be team-less.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    project_status = sa.dialects.postgresql.ENUM(
        "ACTIVE",
        "ARCHIVED",
        name="project_status",
        create_type=False,
    )
    project_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "projects",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", project_status, nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_projects_workspace_id_name"),
    )

    # tasks gain optional links into the new dimensions. SET NULL on
    # delete so a project/team removal never orphans the task itself.
    op.add_column(
        "tasks",
        sa.Column(
            "project_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "team_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_team_id", "tasks", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_team_id", table_name="tasks")
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_column("tasks", "team_id")
    op.drop_column("tasks", "project_id")
    op.drop_table("projects")
    sa.dialects.postgresql.ENUM(name="project_status", create_type=False).drop(
        op.get_bind(), checkfirst=True
    )
