"""add member_role enum + role column, invites table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-07

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


member_role = postgresql.ENUM("OWNER", "ADMIN", "MEMBER", name="member_role", create_type=False)


def upgrade() -> None:
    member_role.create(op.get_bind(), checkfirst=True)

    # `role` defaults to MEMBER for new rows. Existing members get
    # backfilled below: priority=1 (the workspace owner inserted at
    # signup) -> OWNER; everyone else -> MEMBER.
    op.add_column(
        "members",
        sa.Column(
            "role",
            member_role,
            nullable=False,
            server_default="MEMBER",
        ),
    )
    op.execute("UPDATE members SET role = 'OWNER' WHERE priority = 1")

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invited_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", member_role, nullable=False),
        # SHA-256 of the raw token. The raw token is returned to the inviter
        # exactly once (in the response body) and then discarded. Lookup is
        # by hash so a DB leak doesn't grant immediate access — would-be
        # attackers still need to reverse SHA-256.
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_invites_workspace_id_email", "invites", ["workspace_id", "email"])


def downgrade() -> None:
    op.drop_index("ix_invites_workspace_id_email", table_name="invites")
    op.drop_table("invites")
    op.drop_column("members", "role")
    member_role.drop(op.get_bind(), checkfirst=True)
