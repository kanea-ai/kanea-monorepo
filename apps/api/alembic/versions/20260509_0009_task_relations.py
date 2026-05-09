"""task_relations table

Models the directed relationships between two tasks. Inverse views
(blocked_by, mitigated_by, duplicated_by) are computed at read time
from the same row stored in the source -> target direction. RELATES_TO
is symmetric — the API queries both ends and unions.

Stored types: BLOCKS, MITIGATES, DUPLICATES, RELATES_TO. Adding a new
relation type later is a one-line ENUM ALTER (Postgres lets us ADD
VALUE in place).

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Use the postgres-dialect ENUM with explicit create_type=False so
    # we own the CREATE TYPE statement. sa.Enum's create_type kwarg is
    # routed through a different code path that still emits the DDL on
    # alembic, leading to "type already exists" failures.
    relation_type = sa.dialects.postgresql.ENUM(
        "BLOCKS",
        "MITIGATES",
        "DUPLICATES",
        "RELATES_TO",
        name="task_relation_type",
        create_type=False,
    )
    relation_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_relations",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "source_task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", relation_type, nullable=False),
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
        sa.CheckConstraint(
            "source_task_id <> target_task_id",
            name="task_relations_no_self_link",
        ),
        sa.UniqueConstraint(
            "source_task_id",
            "target_task_id",
            "relation_type",
            name="uq_task_relations_source_target_type",
        ),
    )
    # Index for the inverse lookup ("blocked by" view of a task).
    op.create_index(
        "ix_task_relations_target_type",
        "task_relations",
        ["target_task_id", "relation_type"],
    )
    op.create_index(
        "ix_task_relations_source_type",
        "task_relations",
        ["source_task_id", "relation_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_relations_source_type", table_name="task_relations")
    op.drop_index("ix_task_relations_target_type", table_name="task_relations")
    op.drop_table("task_relations")
    sa.dialects.postgresql.ENUM(name="task_relation_type", create_type=False).drop(
        op.get_bind(), checkfirst=True
    )
