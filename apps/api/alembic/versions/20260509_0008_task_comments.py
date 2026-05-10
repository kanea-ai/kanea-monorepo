"""task_comments table

Per-task discussion thread, ordered by created_at. Authors are members
(human or agent) — `author_member_id` uses SET NULL on delete so the
comment thread survives even after a member is removed.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_comments",
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
            "author_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
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
    )
    op.create_index(
        "ix_task_comments_task_id_created_at",
        "task_comments",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_comments_task_id_created_at", table_name="task_comments")
    op.drop_table("task_comments")
