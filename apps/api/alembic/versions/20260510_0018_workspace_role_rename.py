"""rename member_role values to WORKSPACE_*

Phase 1 disambiguates workspace-level roles from team roles. The
existing `member_role` Postgres enum had values OWNER / ADMIN /
MEMBER which clashed with TeamRole.MEMBER and read ambiguously in
JWTs and audit logs.

Postgres can't rename a single enum value once a column references
the type, so we rotate: rename old type out, create the new one with
the WORKSPACE_* names, alter the column with a USING cast that maps
old → new, drop the old.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Rotate: keep the old type around long enough to USING-cast each
    # row to the new one, then drop. The same dance migration 0007 used
    # to drop BLOCKED from task_status.
    bind.execute(sa.text("ALTER TYPE member_role RENAME TO member_role_old"))
    bind.execute(
        sa.text(
            "CREATE TYPE member_role AS ENUM "
            "('WORKSPACE_OWNER','WORKSPACE_ADMIN','WORKSPACE_MEMBER')"
        )
    )
    bind.execute(sa.text("ALTER TABLE members ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text(
            """
            ALTER TABLE members
            ALTER COLUMN role TYPE member_role
            USING (
                CASE role::text
                    WHEN 'OWNER'  THEN 'WORKSPACE_OWNER'::member_role
                    WHEN 'ADMIN'  THEN 'WORKSPACE_ADMIN'::member_role
                    WHEN 'MEMBER' THEN 'WORKSPACE_MEMBER'::member_role
                END
            )
            """
        )
    )
    # Same pattern for invites.role.
    bind.execute(sa.text("ALTER TABLE invites ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text(
            """
            ALTER TABLE invites
            ALTER COLUMN role TYPE member_role
            USING (
                CASE role::text
                    WHEN 'OWNER'  THEN 'WORKSPACE_OWNER'::member_role
                    WHEN 'ADMIN'  THEN 'WORKSPACE_ADMIN'::member_role
                    WHEN 'MEMBER' THEN 'WORKSPACE_MEMBER'::member_role
                END
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE members ALTER COLUMN role " "SET DEFAULT 'WORKSPACE_MEMBER'::member_role"
        )
    )
    bind.execute(sa.text("DROP TYPE member_role_old"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TYPE member_role RENAME TO member_role_new"))
    bind.execute(sa.text("CREATE TYPE member_role AS ENUM ('OWNER','ADMIN','MEMBER')"))
    bind.execute(sa.text("ALTER TABLE members ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text(
            """
            ALTER TABLE members
            ALTER COLUMN role TYPE member_role
            USING (
                CASE role::text
                    WHEN 'WORKSPACE_OWNER'  THEN 'OWNER'::member_role
                    WHEN 'WORKSPACE_ADMIN'  THEN 'ADMIN'::member_role
                    WHEN 'WORKSPACE_MEMBER' THEN 'MEMBER'::member_role
                END
            )
            """
        )
    )
    bind.execute(sa.text("ALTER TABLE invites ALTER COLUMN role DROP DEFAULT"))
    bind.execute(
        sa.text(
            """
            ALTER TABLE invites
            ALTER COLUMN role TYPE member_role
            USING (
                CASE role::text
                    WHEN 'WORKSPACE_OWNER'  THEN 'OWNER'::member_role
                    WHEN 'WORKSPACE_ADMIN'  THEN 'ADMIN'::member_role
                    WHEN 'WORKSPACE_MEMBER' THEN 'MEMBER'::member_role
                END
            )
            """
        )
    )
    bind.execute(sa.text("ALTER TABLE members ALTER COLUMN role SET DEFAULT 'MEMBER'::member_role"))
    bind.execute(sa.text("DROP TYPE member_role_new"))
