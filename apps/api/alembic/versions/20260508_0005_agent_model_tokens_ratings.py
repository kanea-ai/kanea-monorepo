"""agent.model + task.completed_at + task.tokens_used + task_ratings table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `model` is nullable and only meaningful for AGENT-typed members. We
    # don't constrain it to AGENT in the DB — agents may also be created
    # without a model set, so a partial check would be awkward.
    op.add_column("members", sa.Column("model", sa.String(120), nullable=True))

    # `completed_at` is set when a task transitions to DONE. Backfilled
    # from updated_at for existing DONE tasks so resolution-time stats are
    # meaningful from day one (otherwise old tasks would all show NULL
    # and skew the average).
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tasks SET completed_at = updated_at WHERE status = 'DONE'")

    # `tokens_used` is the running total of LLM tokens an agent has spent
    # on the task. NOT NULL with default 0 so aggregation never has to
    # COALESCE.
    op.add_column(
        "tasks",
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "task_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # one rating per task — re-rating overwrites
        ),
        sa.Column(
            "rated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Set null on member delete so historical ratings survive even if
        # the agent gets removed; the workspace's accuracy history stays
        # intact for the remaining agents.
        sa.Column(
            "rated_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("feedback", sa.Text, nullable=True),
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
        sa.CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )
    op.create_index("ix_task_ratings_rated_member_id", "task_ratings", ["rated_member_id"])


def downgrade() -> None:
    op.drop_index("ix_task_ratings_rated_member_id", table_name="task_ratings")
    op.drop_table("task_ratings")
    op.drop_column("tasks", "tokens_used")
    op.drop_column("tasks", "completed_at")
    op.drop_column("members", "model")
