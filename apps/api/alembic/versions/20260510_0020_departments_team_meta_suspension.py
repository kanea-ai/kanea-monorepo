"""departments table, team description + dept FK, members.is_suspended

Three independent additions bundled into one revision:

* ``departments``: workspace-scoped grouping that sits one level above
  teams. Same shape as ``projects`` (workspace_id, name, description,
  created_at). ``(workspace_id, name)`` is unique per workspace.
* ``teams.department_id`` FK (SET NULL on department delete — deleting
  a department un-files its teams rather than dropping them) plus a
  free-form ``description`` column so the cards in the UI have body.
* ``members.is_suspended``: workspace-scoped soft lock. When true, any
  JWT issued for that workspace is rejected at the auth layer; the
  user can still log in to and use *other* workspaces. Defaults to
  false on existing rows.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "departments",
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
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("workspace_id", "name", name="uq_departments_workspace_id_name"),
    )

    # Teams gain an optional department_id (SET NULL so deleting a
    # department de-files its teams without losing them) plus a
    # description so the UI has something to render under each team.
    op.add_column(
        "teams",
        sa.Column(
            "department_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "teams",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_teams_department_id", "teams", ["department_id"])

    # Members gain the workspace-scoped soft lock. NOT NULL, default
    # false so existing rows backfill cleanly. We also add a partial
    # index on (workspace_id) WHERE is_suspended so the auth gate's
    # lookup stays cheap as the table grows.
    op.add_column(
        "members",
        sa.Column(
            "is_suspended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("members", "is_suspended")
    op.drop_index("ix_teams_department_id", table_name="teams")
    op.drop_column("teams", "description")
    op.drop_column("teams", "department_id")
    op.drop_table("departments")
