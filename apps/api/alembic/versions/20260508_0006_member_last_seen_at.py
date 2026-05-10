"""members.last_seen_at for agent heartbeat / health-status

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable. Only meaningful for AGENT-typed members; humans can leave
    # it null. Stamped on each agent JWT issuance and on explicit
    # heartbeat calls. Drives the derived health_status field on agent
    # detail responses.
    op.add_column("members", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("members", "last_seen_at")
