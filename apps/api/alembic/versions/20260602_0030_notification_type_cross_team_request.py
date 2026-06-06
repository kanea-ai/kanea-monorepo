"""Add CROSS_TEAM_REQUEST to the notification_type native enum

The ``notification_type`` Postgres enum was created by migration 0019
with only ``MENTION_TASK`` and ``MENTION_COMMENT``. The cross-team
request feature later added ``NotificationType.CROSS_TEAM_REQUEST`` in
the Python enum and mapped the column with ``create_type=False`` — so
SQLAlchemy never emits the ``ALTER TYPE`` itself. No migration added
the value, so the production database's enum never learned it.

The result was a production-only crash: every cross-team request
(``POST /tasks/{id}/requests``) succeeded in minting the target task,
relation and request row, then 500'd at the notification insert with
``invalid input value for enum notification_type: "CROSS_TEAM_REQUEST"``,
rolling the whole create back. The test suite never caught it because
the integration harness builds enum types from the model metadata
(which already contains the value) rather than from the migrations.

This migration adds the missing value. ``ADD VALUE IF NOT EXISTS`` is
idempotent, so it is safe on any database whose enum already has the
value (e.g. one built from metadata in a test environment). PostgreSQL
permits ``ALTER TYPE ... ADD VALUE`` inside a transaction on 12+; the
new value is not used within this migration's transaction.

There is no downgrade: PostgreSQL has no ``ALTER TYPE ... DROP VALUE``.
Removing the value would require recreating the type and rewriting
every dependent column, which is out of scope for a reversible
migration; ``downgrade`` is therefore a documented no-op.

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'CROSS_TEAM_REQUEST'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating
    # it and rewriting every dependent column. Intentional no-op; see the
    # module docstring.
    pass
