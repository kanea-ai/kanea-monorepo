"""backfill workspace owners stuck as MEMBER

Earlier batches issued the workspace creator with role=MEMBER (the
dataclass default). The bug was fixed in code, but existing rows
remain stuck — their JWTs claim role=MEMBER and the admin UI is out
of reach.

This migration promotes the *earliest HUMAN member of each workspace*
to OWNER, but only if they're currently MEMBER. Workspaces that
already have a correct OWNER are no-op'd by the WHERE clause.

The heuristic is safe because:
- Registration creates the owner first (timestamp-wise) before any
  invite acceptances.
- We filter to type='HUMAN' and email IS NOT NULL so AGENT-typed
  rows are never picked.
- The role='MEMBER' filter rules out workspaces that already have
  the correct OWNER (those rows would be 'OWNER' already).

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Postgres `DISTINCT ON` keeps the first row per workspace_id
    # ordered by created_at — that's the workspace creator.
    bind.execute(
        sa.text(
            """
            UPDATE members
            SET role = 'OWNER'
            WHERE id IN (
                SELECT DISTINCT ON (workspace_id) id
                FROM members
                WHERE type = 'HUMAN' AND email IS NOT NULL
                ORDER BY workspace_id, created_at ASC, id ASC
            )
            AND role = 'MEMBER'
            """
        )
    )


def downgrade() -> None:
    # No-op. We won't demote anyone — there's no clean way to
    # distinguish promoted-by-this-migration owners from organic
    # owners without an audit column we don't have. Leaving them as
    # OWNER is harmless on downgrade.
    pass
