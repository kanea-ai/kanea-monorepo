"""add oauth_provider/oauth_id to credentials, relax at_least_one_secret

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


oauth_provider = postgresql.ENUM("GOOGLE", "GITHUB", name="oauth_provider", create_type=False)


def upgrade() -> None:
    oauth_provider.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "credentials",
        sa.Column("oauth_provider", oauth_provider, nullable=True),
    )
    op.add_column(
        "credentials",
        sa.Column("oauth_id", sa.String(255), nullable=True),
    )

    # An OAuth identity (provider, oauth_id) is globally unique. Two members
    # in different workspaces can't share the same Google sub or GitHub user
    # id — would-be duplicates link to whichever account claimed it first.
    op.create_unique_constraint(
        "uq_credentials_oauth_provider_oauth_id",
        "credentials",
        ["oauth_provider", "oauth_id"],
    )

    # Drop the old "at_least_one_secret" check (password_hash OR
    # agent_secret_hash) and add a relaxed version that also accepts an
    # OAuth identity as the secret material.
    op.drop_constraint("ck_credentials_at_least_one_secret", "credentials", type_="check")
    op.create_check_constraint(
        "at_least_one_secret",
        "credentials",
        (
            "password_hash IS NOT NULL "
            "OR agent_secret_hash IS NOT NULL "
            "OR (oauth_provider IS NOT NULL AND oauth_id IS NOT NULL)"
        ),
    )


def downgrade() -> None:
    op.drop_constraint("ck_credentials_at_least_one_secret", "credentials", type_="check")
    op.create_check_constraint(
        "at_least_one_secret",
        "credentials",
        "password_hash IS NOT NULL OR agent_secret_hash IS NOT NULL",
    )

    op.drop_constraint("uq_credentials_oauth_provider_oauth_id", "credentials", type_="unique")
    op.drop_column("credentials", "oauth_id")
    op.drop_column("credentials", "oauth_provider")

    oauth_provider.drop(op.get_bind(), checkfirst=True)
