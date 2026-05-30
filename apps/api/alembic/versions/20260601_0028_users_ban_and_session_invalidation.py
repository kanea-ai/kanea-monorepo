"""add users.is_banned + users.sessions_invalidated_at

Two back-office-driven controls on the global User row:

* ``is_banned`` (bool, NOT NULL, default false) — platform-wide ban
  flipped by the ``/api/v1/admin/users/{id}/ban`` endpoint. While
  True, ``get_current_principal`` short-circuits every authenticated
  request with 403; the underlying tenancy isn't touched, so a
  re-enable restores access without any data shuffling.

* ``sessions_invalidated_at`` (timestamptz, nullable) — stateless
  session kill-switch. The back-office's force-password-reset stamps
  this column with ``now()``; the auth dep rejects any JWT whose
  ``iat`` is older than the stamp. Lets us invalidate live sessions
  without an external blacklist or token store.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_banned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "sessions_invalidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_invalidated_at")
    op.drop_column("users", "is_banned")
