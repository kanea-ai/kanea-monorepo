"""notifications table for @mentions

Phase 4: per-user inbox of activity that should surface to a person.
Today only mentions populate it (description / comment), but the
schema is intentionally generic — `type`, `payload` (JSONB), and the
nullable source FKs let later events (assignment, comment-on-watched
task, status changes) plug in without a second migration.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the enum explicitly first; pass create_type=False to the
    # column's Enum() so create_table doesn't try to re-create it under
    # us (which would race + raise even with checkfirst=True).
    notification_type = postgresql.ENUM(
        "MENTION_TASK",
        "MENTION_COMMENT",
        name="notification_type",
        create_type=False,
    )
    sa.Enum(
        "MENTION_TASK",
        "MENTION_COMMENT",
        name="notification_type",
    ).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", notification_type, nullable=False),
        # Source pointers — all nullable. SET NULL on delete so the
        # notification stays visible (with a "[task removed]" fallback
        # in the UI) instead of cascading-deleting user-visible state.
        sa.Column(
            "source_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_comment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_comments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Short denormalised preview. Saves a join on the read path
        # and survives the source row being deleted.
        sa.Column("preview", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Inbox query: latest first, scoped to a user.
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", sa.text("created_at DESC")],
    )
    # Unread count: cheap with a partial index that only keeps unread rows.
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notification_type").drop(op.get_bind(), checkfirst=True)
