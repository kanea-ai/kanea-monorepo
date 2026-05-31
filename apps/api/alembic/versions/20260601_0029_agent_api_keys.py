"""agent_api_keys table + drop credentials.agent_secret_hash

Single auth path for AGENT members. The new ``agent_api_keys`` table
holds N keys per agent, each with its own per-key revocation +
last_used_at. The legacy ``credentials.agent_secret_hash`` column is
dropped in the same migration — agents no longer require a
``credentials`` row at all; their auth secret lives entirely in the
new table.

Pre-flight: this migration DELETEs any orphan ``credentials`` rows
that satisfied only the now-removed ``agent_secret_hash`` clause
(rows with NULL password_hash AND NULL oauth_provider). It prints
the count and member_ids of those rows before deleting so the
operator can confirm the blast radius matches expectation. Per the
clean-break decision (no real production agent keys exist at the
time of this migration), this is acceptable.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create the new table + supporting index.
    op.create_table(
        "agent_api_keys",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # HMAC-SHA-256 of the key body, hex-encoded (64 chars). UNIQUE
        # backs the O(log n) lookup at /auth/agent-token exchange time
        # and trivially defends against the astronomically-unlikely hash
        # collision case.
        sa.Column("secret_hash", sa.CHAR(64), nullable=False, unique=True),
        # Unhashed for the UI fingerprint ("kna_live_…AbCd"). Never used
        # for auth — purely greppable / displayable identification.
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("last4", sa.String(8), nullable=False),
        # Optional operator label ("ci-runner", "qa-script", …).
        sa.Column("label", sa.String(80), nullable=True),
        # Audit: which member minted the key. RESTRICT so we surface
        # the dependency cleanly if an operator tries to hard-delete
        # an admin that has live keys outstanding.
        sa.Column(
            "created_by_member_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_api_keys_member_id",
        "agent_api_keys",
        ["member_id"],
    )

    # 2. Pre-flight: identify orphan credentials rows we're about to
    #    delete. These are credentials that satisfied only the legacy
    #    agent_secret_hash clause of the old CHECK constraint — they
    #    have no password and no OAuth identity. Under the new shape
    #    they'd fail the rewritten CHECK, so they have to go before
    #    we replace the constraint.
    bind = op.get_bind()
    orphans = bind.execute(
        sa.text(
            "SELECT id, member_id FROM credentials "
            "WHERE password_hash IS NULL "
            "AND oauth_provider IS NULL AND oauth_id IS NULL"
        )
    ).fetchall()
    print(f"[migration 0029] orphan credentials rows about to be deleted: " f"count={len(orphans)}")
    for row in orphans:
        print(f"[migration 0029]   credential={row[0]} member={row[1]}")

    # 3. Delete the orphans. Per the clean-break decision, no real
    #    production agent keys exist at the time of this migration —
    #    only throwaway test agents whose secrets are disposable.
    op.execute(
        "DELETE FROM credentials WHERE password_hash IS NULL "
        "AND oauth_provider IS NULL AND oauth_id IS NULL"
    )

    # 4. Replace the CHECK constraint BEFORE dropping the column it
    #    references. New shape: a credentials row must carry either a
    #    password or an OAuth identity. AGENT members no longer have
    #    a credentials row at all.
    op.drop_constraint("at_least_one_secret", "credentials", type_="check")
    op.create_check_constraint(
        "at_least_one_secret",
        "credentials",
        "password_hash IS NOT NULL " "OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)",
    )

    # 5. Drop the now-unreferenced column.
    op.drop_column("credentials", "agent_secret_hash")


def downgrade() -> None:
    # WARNING: downgrade restores the SCHEMA only — it cannot recover
    # the agent_secret_hash values that 0029 dropped, nor the orphan
    # credentials rows that 0029 deleted. Running this on real data
    # leaves agents unable to authenticate until they re-key. Treat as
    # rollback-for-tests only.
    op.add_column(
        "credentials",
        sa.Column("agent_secret_hash", sa.String(255), nullable=True),
    )
    op.drop_constraint("at_least_one_secret", "credentials", type_="check")
    op.create_check_constraint(
        "at_least_one_secret",
        "credentials",
        "password_hash IS NOT NULL "
        "OR agent_secret_hash IS NOT NULL "
        "OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)",
    )
    op.drop_index("ix_agent_api_keys_member_id", table_name="agent_api_keys")
    op.drop_table("agent_api_keys")
