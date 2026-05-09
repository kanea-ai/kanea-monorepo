"""task_activities audit log

Append-only event log of structural changes to a task — status flips,
block/unblock, assignment, project / team moves, ratings. The table
backs the agent-facing history endpoints: an LLM analysing what went
right/wrong on a project reads the activity stream alongside the
comment thread.

`event_type` is a free-form varchar so new event kinds can land
without a migration. The application layer pins the vocabulary via
the TaskActivityType StrEnum.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_activities",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        # JSONB holds event-shaped detail: from/to status, reason text,
        # actor delegation pair, etc. Indexed only on the standard
        # (task_id, created_at) — payload querying is expected to be
        # ad-hoc and small per task.
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_task_activities_task_id_created_at",
        "task_activities",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_activities_task_id_created_at", table_name="task_activities")
    op.drop_table("task_activities")
