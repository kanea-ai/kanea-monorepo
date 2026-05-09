"""task_requests table — cross-team request workflow

Section 3: a standard MEMBER can't drop work onto another team's
board. They file a request from their source task and a MANAGER /
LEAD on their own team fulfills it by minting a task on the target
team and linking the two with a BLOCKS relation.

Status vocabulary lives at the application layer (RequestStatus
StrEnum) — varchar storage so adding new states later is code-only.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_requests",
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
            "requested_team_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requester_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("suggested_title", sa.String(length=200), nullable=False),
        sa.Column("suggested_description", sa.Text(), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column(
            "fulfilled_task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column(
            "resolver_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # The leadership inbox query — list pending requests where the
    # source task lives on a given team.
    op.create_index(
        "ix_task_requests_source_task_id",
        "task_requests",
        ["source_task_id"],
    )
    op.create_index(
        "ix_task_requests_requested_team_id_status",
        "task_requests",
        ["requested_team_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_requests_requested_team_id_status", table_name="task_requests")
    op.drop_index("ix_task_requests_source_task_id", table_name="task_requests")
    op.drop_table("task_requests")
