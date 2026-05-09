"""add IN_REVIEW to task_status enum

Section 4 lifecycle update: IN_REVIEW sits between IN_PROGRESS and
DONE for tasks awaiting human / secondary-agent verification (QA,
review, sign-off).

`ALTER TYPE ... ADD VALUE` can't run inside the implicit Alembic
transaction on some Postgres versions, so we wrap the statement in an
``autocommit_block`` to detach it.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'IN_REVIEW' AFTER 'IN_PROGRESS'")


def downgrade() -> None:
    # Postgres can't drop a single ENUM value, so an honest downgrade
    # would rotate the entire type — overkill for a forward-only feature.
    # Any rows in IN_REVIEW would also need rebucketing. Leaving as a
    # no-op; if a real downgrade is ever needed, repurpose migration
    # 0007's rotate-type pattern.
    pass
