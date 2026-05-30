"""partial unique indices: at most ONE MANAGER and ONE LEAD per team

The team-leadership invariant (one MANAGER and one LEAD per team) is
enforced primarily at the service layer in
``InviteService.set_member_team`` — assigning a new MANAGER/LEAD
demotes the sitting holder in the same transaction. These indices are
the DB-level belt to that service-level brace: a concurrent write that
races the service check still fails fast.

Partial indices (``WHERE team_role = 'MANAGER'`` / ``... = 'LEAD'``)
instead of plain UNIQUE constraints so the constraint only applies to
the two ranks that need it; MEMBER rows are unbounded per team.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-30

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Data fix-up: if a team currently has more than one MANAGER (or
    # LEAD), keep the earliest by created_at and demote the rest to
    # MEMBER so the unique index can be built. Idempotent — re-running
    # on already-conformant data is a no-op.
    for role in ("MANAGER", "LEAD"):
        op.execute(
            f"""
            UPDATE members
               SET team_role = 'MEMBER'
             WHERE id IN (
                     SELECT m.id FROM members m
                      WHERE m.team_role = '{role}'
                        AND m.team_id IS NOT NULL
                        AND m.id <> (
                             SELECT m2.id FROM members m2
                              WHERE m2.team_id = m.team_id
                                AND m2.team_role = '{role}'
                              ORDER BY m2.created_at, m2.id
                              LIMIT 1
                            )
                   )
            """
        )

    op.create_index(
        "uq_members_team_id_one_manager",
        "members",
        ["team_id"],
        unique=True,
        postgresql_where="team_role = 'MANAGER'",
    )
    op.create_index(
        "uq_members_team_id_one_lead",
        "members",
        ["team_id"],
        unique=True,
        postgresql_where="team_role = 'LEAD'",
    )


def downgrade() -> None:
    op.drop_index("uq_members_team_id_one_lead", table_name="members")
    op.drop_index("uq_members_team_id_one_manager", table_name="members")
