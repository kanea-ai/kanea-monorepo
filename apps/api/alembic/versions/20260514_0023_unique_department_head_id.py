"""unique partial index on departments.head_id

A member can be the head of at most ONE Department. The application
layer enforces this in DepartmentService (see
``_ensure_head_not_taken``); this migration adds the DB-level safety
net so a concurrent insert/update that races the service check still
fails fast.

Partial index (``WHERE head_id IS NOT NULL``) instead of a plain
UNIQUE constraint because many departments may legitimately have no
head (head_id is NULL), and Postgres' standard UNIQUE semantics treat
NULLs as distinct anyway — the partial form makes the intent explicit
and keeps the index small.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-14

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Data fixup: if any member currently heads more than one
    # department (only possible because 0022 didn't enforce the
    # uniqueness), keep the earliest department and NULL the rest so
    # the unique index can be built. This is idempotent — re-running
    # on already-unique data is a no-op.
    op.execute(
        """
        UPDATE departments
           SET head_id = NULL
         WHERE id IN (
                 SELECT d.id FROM departments d
                  WHERE d.head_id IS NOT NULL
                    AND d.id <> (
                         SELECT d2.id FROM departments d2
                          WHERE d2.head_id = d.head_id
                          ORDER BY d2.created_at, d2.id
                          LIMIT 1
                       )
              )
        """
    )

    # Replace the non-unique ix_departments_head_id (added in 0022)
    # with a partial unique index of the same shape — the lookup path
    # stays cheap and uniqueness is enforced at the same time.
    op.drop_index("ix_departments_head_id", table_name="departments")
    op.create_index(
        "uq_departments_head_id_not_null",
        "departments",
        ["head_id"],
        unique=True,
        postgresql_where="head_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_departments_head_id_not_null", table_name="departments")
    op.create_index("ix_departments_head_id", "departments", ["head_id"])
