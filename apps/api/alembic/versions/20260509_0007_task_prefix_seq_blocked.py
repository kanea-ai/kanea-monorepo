"""task prefix/seq, is_blocked flag, drop BLOCKED status

Reshapes tasks for batch 2:

* `workspaces.task_prefix` (e.g. "DEVOPS") + `workspaces.next_task_seq`
  give every task a human-readable id like ``DEVOPS-001``. The seq is
  bumped atomically (UPDATE ... RETURNING) when a task is created.
* `tasks.seq` stores the per-workspace integer; (workspace_id, seq) is
  unique. Public id is ``{prefix}-{seq:03d}`` and is exposed by the
  api / UI but never used as a primary key.
* `tasks.is_blocked` becomes its own boolean. The TaskStatus enum gets
  ``BLOCKED`` removed — being blocked is orthogonal to the lifecycle
  (a blocked task is still IN_PROGRESS or PENDING under the hood).
* Existing rows with status='BLOCKED' get migrated to
  (status='IN_PROGRESS', is_blocked=true, blocked_reason preserved).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-09

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---------- workspaces: prefix + counter ----------
    op.add_column(
        "workspaces",
        sa.Column(
            "task_prefix",
            sa.String(length=8),
            nullable=False,
            server_default="TASK",
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "next_task_seq",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    # Derive a prefix from each existing workspace's name: alpha chars,
    # uppercased, truncated to 6, fallback "TASK". Truncation happens
    # in the same UPDATE so the value never overflows the varchar(8).
    bind.execute(
        sa.text(
            """
            UPDATE workspaces
            SET task_prefix = SUBSTRING(
                COALESCE(
                    NULLIF(UPPER(REGEXP_REPLACE(name, '[^A-Za-z]', '', 'g')), ''),
                    'TASK'
                )
                FROM 1 FOR 6
            )
            """
        )
    )

    # ---------- tasks: seq + is_blocked ----------
    op.add_column(
        "tasks",
        sa.Column("seq", sa.Integer(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "is_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Backfill seq within each workspace, ordered by created_at.
    bind.execute(
        sa.text(
            """
            WITH numbered AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY workspace_id
                           ORDER BY created_at, id
                       ) AS rn
                FROM tasks
            )
            UPDATE tasks t
            SET seq = numbered.rn
            FROM numbered
            WHERE t.id = numbered.id
            """
        )
    )

    # Bump each workspace's next_task_seq past whatever exists.
    bind.execute(
        sa.text(
            """
            UPDATE workspaces w
            SET next_task_seq = COALESCE((
                SELECT MAX(t.seq) + 1
                FROM tasks t
                WHERE t.workspace_id = w.id
            ), 1)
            """
        )
    )

    op.alter_column("tasks", "seq", nullable=False)
    op.create_index(
        "uq_tasks_workspace_id_seq",
        "tasks",
        ["workspace_id", "seq"],
        unique=True,
    )

    # Existing BLOCKED rows -> (IN_PROGRESS, is_blocked=true). We keep
    # blocked_reason exactly as it was.
    bind.execute(
        sa.text(
            """
            UPDATE tasks
            SET is_blocked = true,
                status = 'IN_PROGRESS'
            WHERE status = 'BLOCKED'
            """
        )
    )

    # ---------- enum cleanup: drop BLOCKED from task_status ----------
    # Postgres can't ALTER TYPE ... DROP VALUE, so we rotate: rename old,
    # create the slim version, alter the column, then drop the old type.
    # Postgres won't auto-cast the column DEFAULT during the type swap,
    # so we drop and reinstate it around the ALTER.
    bind.execute(sa.text("ALTER TYPE task_status RENAME TO task_status_old"))
    bind.execute(
        sa.text("CREATE TYPE task_status AS ENUM " "('PENDING','IN_PROGRESS','DONE','CANCELLED')")
    )
    bind.execute(sa.text("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT"))
    bind.execute(
        sa.text(
            "ALTER TABLE tasks ALTER COLUMN status TYPE task_status "
            "USING status::text::task_status"
        )
    )
    bind.execute(
        sa.text("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'PENDING'::task_status")
    )
    bind.execute(sa.text("DROP TYPE task_status_old"))


def downgrade() -> None:
    bind = op.get_bind()

    # Re-add BLOCKED to the enum first so the column can hold it again.
    bind.execute(sa.text("ALTER TYPE task_status RENAME TO task_status_new"))
    bind.execute(
        sa.text(
            "CREATE TYPE task_status AS ENUM "
            "('PENDING','IN_PROGRESS','BLOCKED','DONE','CANCELLED')"
        )
    )
    bind.execute(sa.text("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT"))
    bind.execute(
        sa.text(
            "ALTER TABLE tasks ALTER COLUMN status TYPE task_status "
            "USING status::text::task_status"
        )
    )
    bind.execute(
        sa.text("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'PENDING'::task_status")
    )
    bind.execute(sa.text("DROP TYPE task_status_new"))

    # Fold the flag back into a status. We can't perfectly restore which
    # tasks were originally BLOCKED in PENDING vs IN_PROGRESS, so collapse
    # to BLOCKED whenever the flag is set — best-effort downgrade.
    bind.execute(sa.text("UPDATE tasks SET status = 'BLOCKED' WHERE is_blocked = true"))

    op.drop_index("uq_tasks_workspace_id_seq", table_name="tasks")
    op.drop_column("tasks", "is_blocked")
    op.drop_column("tasks", "seq")

    op.drop_column("workspaces", "next_task_seq")
    op.drop_column("workspaces", "task_prefix")
