"""departments.head_id FK + drop HEAD from team_role enum

Moves the "Head" concept off ``members.team_role`` (a per-team rank) and
onto a new ``departments.head_id`` FK pointing at a member. A Head is
now an attribute of a Department, not of a Team.

Two changes in one revision:

* ``departments.head_id``: nullable uuid FK → ``members.id`` ON DELETE
  SET NULL. A Department may exist without a designated Head; when the
  head is removed from the workspace the FK is silently cleared so the
  Department row outlives them.
* ``team_role`` Postgres enum: drop the ``HEAD`` value. Members that
  used to be ``team_role='HEAD'`` are migrated to ``'MANAGER'`` in the
  same alter. They are NOT auto-elevated to department head — that's
  an operator action and would be ambiguous when a former HEAD's team
  had no department.

Postgres can't ``DROP VALUE`` from an existing enum directly, so the
column is migrated to a freshly-created enum type with USING-clause
remapping; the old type is then dropped and the new one renamed back
to ``team_role`` so subsequent migrations + the SQLAlchemy mapping
keep referring to the same name.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-14

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- 1. departments.head_id ----------
    op.add_column(
        "departments",
        sa.Column(
            "head_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_departments_head_id", "departments", ["head_id"])

    # ---------- 2. drop HEAD from team_role enum ----------
    # Create a fresh enum without HEAD, swap the column to it with a
    # USING clause that remaps HEAD -> MANAGER, then drop the old type
    # and rename the new one back to `team_role`.
    op.execute("CREATE TYPE team_role_new AS ENUM ('MANAGER', 'LEAD', 'MEMBER')")
    op.execute(
        """
        ALTER TABLE members
          ALTER COLUMN team_role TYPE team_role_new
          USING (
            CASE team_role::text
              WHEN 'HEAD' THEN 'MANAGER'::team_role_new
              ELSE team_role::text::team_role_new
            END
          )
        """
    )
    op.execute("DROP TYPE team_role")
    op.execute("ALTER TYPE team_role_new RENAME TO team_role")


def downgrade() -> None:
    # Re-introduce HEAD on the enum (no data is restored — former HEADs
    # remain as MANAGERs).
    op.execute("CREATE TYPE team_role_new AS ENUM ('HEAD', 'MANAGER', 'LEAD', 'MEMBER')")
    op.execute(
        """
        ALTER TABLE members
          ALTER COLUMN team_role TYPE team_role_new
          USING (team_role::text::team_role_new)
        """
    )
    op.execute("DROP TYPE team_role")
    op.execute("ALTER TYPE team_role_new RENAME TO team_role")

    op.drop_index("ix_departments_head_id", table_name="departments")
    op.drop_column("departments", "head_id")
