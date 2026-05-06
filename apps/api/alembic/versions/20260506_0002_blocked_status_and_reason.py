"""add BLOCKED to task_status enum and blocked_reason column

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as long
    # as the new value isn't used in the same transaction. We only add a new
    # plain TEXT column below, so this is safe.
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'BLOCKED'")

    op.add_column(
        "tasks",
        sa.Column("blocked_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "blocked_reason")
    # Postgres has no native way to remove an enum value. Recreating the type
    # would require rewriting the column for every row. We accept that
    # downgrading leaves 'BLOCKED' in the enum as an inert value.
