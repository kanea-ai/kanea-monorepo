"""users table + members.user_id

Phase 1 multi-tenancy split. Today a Member row holds both the
per-workspace identity AND the human's auth identity (email +
credentials.password_hash). That conflates two things and makes
multi-workspace login impossible — the same email exists as N
distinct member rows, each with its own credentials.

This migration introduces a global Users table and links Members to
it via members.user_id. After it lands:

* Auth lives on `users` (email, password_hash, oauth_provider/oauth_id,
  full_name).
* `members` becomes the per-workspace "Membership" — keyed by
  (workspace_id, user_id), with role / team / priority / etc.
* `credentials` keeps only agent_secret_hash for AGENT members; the
  human auth columns are kept-but-unused for one release to avoid a
  risky drop-column-with-rebuild. A future migration cleans them up.

Backfill: for each unique email in members (HUMAN only), create one
user row carrying the EARLIEST member's full_name + the EARLIEST
credentials.password_hash + oauth identity. Then populate
members.user_id by joining on email.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---------- users table ----------
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("email", sa.String(length=254), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "oauth_provider",
            sa.dialects.postgresql.ENUM(name="oauth_provider", create_type=False),
            nullable=True,
        ),
        sa.Column("oauth_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("oauth_provider", "oauth_id", name="uq_users_oauth_provider_oauth_id"),
        sa.CheckConstraint(
            (
                "password_hash IS NOT NULL "
                "OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)"
            ),
            name="users_at_least_one_secret",
        ),
    )

    # ---------- backfill ----------
    # Each unique email becomes one user. We take the earliest member's
    # name and the earliest credentials' password_hash / oauth columns
    # as the canonical identity. Subsequent memberships of the same
    # email all link to this single user row.
    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, email, full_name,
                password_hash, oauth_provider, oauth_id,
                created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                m.email,
                m.name,
                c.password_hash,
                c.oauth_provider,
                c.oauth_id,
                m.created_at,
                m.created_at
            FROM (
                SELECT DISTINCT ON (email)
                    id, email, name, created_at
                FROM members
                WHERE type = 'HUMAN' AND email IS NOT NULL
                ORDER BY email, created_at ASC, id ASC
            ) m
            LEFT JOIN credentials c ON c.member_id = m.id
            """
        )
    )

    # ---------- members.user_id ----------
    op.add_column(
        "members",
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_members_user_id", "members", ["user_id"])

    # Populate user_id by joining on email for HUMAN members. AGENT
    # rows have email=NULL by construction so they keep user_id=NULL.
    bind.execute(
        sa.text(
            """
            UPDATE members m
            SET user_id = u.id
            FROM users u
            WHERE m.email = u.email AND m.type = 'HUMAN'
            """
        )
    )

    # Tighten: every HUMAN member must now point at a user; AGENTs
    # remain user-less. This invariant matches the auth model — humans
    # are global, agents are per-workspace.
    op.create_check_constraint(
        "members_human_has_user",
        "members",
        "(type = 'HUMAN' AND user_id IS NOT NULL) " "OR (type = 'AGENT' AND user_id IS NULL)",
    )

    # Workspaces ↔ users uniqueness: a single user can appear at most
    # once per workspace (no duplicate memberships).
    op.create_unique_constraint(
        "uq_members_workspace_id_user_id",
        "members",
        ["workspace_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_members_workspace_id_user_id", "members", type_="unique")
    op.drop_constraint("members_human_has_user", "members", type_="check")
    op.drop_index("ix_members_user_id", table_name="members")
    op.drop_column("members", "user_id")
    op.drop_table("users")
