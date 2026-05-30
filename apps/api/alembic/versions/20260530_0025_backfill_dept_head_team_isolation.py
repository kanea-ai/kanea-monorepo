"""backfill: a Department Head cannot also sit on a Team

Strict hierarchy rule (Phase 7): a member designated as ``departments.head_id``
holds NO ``team_id`` and NO ``team_role`` — Heads sit above team-level
leadership in the org chart. The service layer enforces this on every
NEW promotion (see ``DepartmentService.create/update`` and
``InviteService.set_member_team``); this migration is the one-shot
data fix-up for any rows that pre-date the rule, plus a re-runnable
safety net for state drift.

Idempotent: re-running it on already-clean data is a no-op.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-30

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Clear team_id + team_role for any member who currently heads a
    # department. The single UPDATE covers both columns so we can't
    # leave behind a half-isolated row.
    op.execute(
        """
        UPDATE members AS m
           SET team_id = NULL,
               team_role = NULL
          FROM departments AS d
         WHERE d.head_id = m.id
           AND (m.team_id IS NOT NULL OR m.team_role IS NOT NULL)
        """
    )


def downgrade() -> None:
    # No reversal — we cleared data we didn't keep around. A downgrade
    # restores the prior (broken) state by doing nothing; new writes
    # following the rule are fine either way.
    pass
