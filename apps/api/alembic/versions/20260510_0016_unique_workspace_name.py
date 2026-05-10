"""enforce globally-unique workspaces.name

Phase 1 multi-tenancy: a Workspace name should be a global identifier,
not just a per-row label. Existing duplicates (created freely by
earlier signups) get an "(N)" suffix to disambiguate before the
constraint goes on.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Disambiguate any existing duplicates before adding the constraint.
    # Window function gives each duplicate row a 1-based rank by
    # created_at; the first one keeps the bare name, subsequent rows
    # get "Acme (2)", "Acme (3)", ...
    bind.execute(
        sa.text(
            """
            UPDATE workspaces w
            SET name = sub.new_name
            FROM (
                SELECT
                    id,
                    CASE
                        WHEN rn = 1 THEN name
                        ELSE name || ' (' || rn::text || ')'
                    END AS new_name
                FROM (
                    SELECT
                        id,
                        name,
                        ROW_NUMBER() OVER (
                            PARTITION BY name ORDER BY created_at, id
                        ) AS rn
                    FROM workspaces
                ) ranked
                WHERE rn > 1
            ) sub
            WHERE w.id = sub.id
            """
        )
    )
    op.create_unique_constraint("uq_workspaces_name", "workspaces", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_workspaces_name", "workspaces", type_="unique")
