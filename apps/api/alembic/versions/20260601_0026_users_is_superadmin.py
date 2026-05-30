"""add users.is_superadmin (platform back-office God-Mode flag)

Boolean column on the global ``users`` table that gates the
``/api/v1/admin/*`` surface served to the internal back-office
(``apps/admin-panel``). Default false; flipped out-of-band via
``scripts.make_superadmin`` — there is NO API path that elevates a
user to superadmin so a compromised account can't bootstrap its own
escalation.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superadmin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_superadmin")
