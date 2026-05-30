"""add workspaces.suspended_at (soft-suspension stamp)

Nullable ``TIMESTAMPTZ`` on the workspaces table. Flipped by
``PATCH /api/v1/admin/workspaces/{id}/suspend`` from the back-office.
``get_current_principal`` short-circuits with 403 for any workspace-
scoped request while the column is non-NULL — soft delete by design so
no tenant data is ever lost on an accidental click.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "suspended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_workspaces_suspended_at",
        "workspaces",
        ["suspended_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_suspended_at", table_name="workspaces")
    op.drop_column("workspaces", "suspended_at")
