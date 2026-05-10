"""rename WORKSPACE_MEMBER → WORKSPACE_USER + audit_logs table

Two adjacent RBAC changes bundled into one revision:

* Workspace-level role enum: ``WORKSPACE_MEMBER`` is renamed to
  ``WORKSPACE_USER`` to disambiguate it from the team-level
  ``TeamRole.MEMBER`` and to read more clearly in the new RBAC matrix
  ("system users" vs. "team members" are different concepts).

  Postgres ALTER TYPE ... RENAME VALUE rewrites every existing row
  atomically, so no separate data backfill is needed. Both ``members``
  and ``invites`` reference this enum; they're updated implicitly.

* New ``audit_logs`` table for the unified workspace audit trail. One
  row per administrative event:

  * ``actor_member_id``  — who did it (SET NULL on member delete so
    the row survives)
  * ``action``           — e.g. CREATED / UPDATED / DELETED / SUSPENDED
  * ``resource_type``    — DEPARTMENT / TEAM / MEMBER / WORKSPACE
  * ``resource_id``      — uuid of the affected row, NULL for events
                           that target the workspace itself
  * ``changes``          — JSONB diff (before/after for updates,
                           captured fields for creates/deletes)

  This complements the existing ``task_activities`` table — that one
  stays for per-task events; ``audit_logs`` is for org/RBAC events.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Drop the column default first; ALTER TYPE ... RENAME VALUE bumps
    # against the literal default 'WORKSPACE_MEMBER'::member_role
    # otherwise.
    bind.execute(sa.text("ALTER TABLE members ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text("ALTER TYPE member_role RENAME VALUE 'WORKSPACE_MEMBER' TO 'WORKSPACE_USER'")
    )
    bind.execute(
        sa.text("ALTER TABLE members ALTER COLUMN role SET DEFAULT 'WORKSPACE_USER'::member_role")
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Actor goes null when the member is deleted — we keep the
        # row so the audit trail survives.
        sa.Column(
            "actor_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        # Nullable for events that target the workspace itself rather
        # than a child resource.
        sa.Column(
            "resource_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "changes",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_logs_workspace_created",
        "audit_logs",
        ["workspace_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_audit_logs_resource",
        "audit_logs",
        ["workspace_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index("ix_audit_logs_workspace_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE members ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text("ALTER TYPE member_role RENAME VALUE 'WORKSPACE_USER' TO 'WORKSPACE_MEMBER'")
    )
    bind.execute(
        sa.text("ALTER TABLE members ALTER COLUMN role SET DEFAULT 'WORKSPACE_MEMBER'::member_role")
    )
