"""members.team_role enum column

Adds an intra-team rank for each member: HEAD / MANAGER / LEAD /
MEMBER. Distinct from members.role, which is the workspace-wide
permission grade (OWNER / ADMIN / MEMBER).

The column is nullable — members not assigned to a team have no team
role. When members.team_id is set, members.team_role is expected to
be set too; we don't enforce that with a CHECK constraint to keep the
backfill simple, but the application layer fills the role on assign.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    team_role = sa.dialects.postgresql.ENUM(
        "HEAD",
        "MANAGER",
        "LEAD",
        "MEMBER",
        name="team_role",
        create_type=False,
    )
    team_role.create(op.get_bind(), checkfirst=True)

    op.add_column("members", sa.Column("team_role", team_role, nullable=True))


def downgrade() -> None:
    op.drop_column("members", "team_role")
    sa.dialects.postgresql.ENUM(name="team_role", create_type=False).drop(
        op.get_bind(), checkfirst=True
    )
