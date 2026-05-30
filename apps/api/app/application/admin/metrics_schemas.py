from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RecentSignup(BaseModel):
    """One row on the dashboard's "Recent signups" list. The
    minimum identifying surface so the operator can click through to
    the user dialog without paying for the full user payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    created_at: datetime


class PlatformMetricsResponse(BaseModel):
    """Top-of-dashboard counters. Computed in a single SQL pass via
    three correlated scalar subqueries (see
    ``SqlAlchemyAdminMetricsRepository.get_summary``) so the back-
    office landing page loads in one round-trip."""

    model_config = ConfigDict(from_attributes=True)

    total_active_workspaces: int
    total_registered_users: int
    total_tokens_used: int
    recent_signups: list[RecentSignup]
