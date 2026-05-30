from __future__ import annotations

from dataclasses import dataclass

from app.application.admin.metrics_ports import AdminMetricsRepository
from app.application.admin.metrics_schemas import (
    PlatformMetricsResponse,
    RecentSignup,
)


@dataclass(slots=True)
class AdminMetricsService:
    metrics: AdminMetricsRepository
    # 7 days matches the spec's "Recent signups (last 7 days list)".
    # Surfacing the constant on the service so a follow-up
    # request to widen the window is a one-line change.
    recent_window_days: int = 7
    recent_limit: int = 50

    async def get_summary(self) -> PlatformMetricsResponse:
        agg = await self.metrics.get_summary()
        signups = await self.metrics.list_recent_signups(
            since_days=self.recent_window_days,
            limit=self.recent_limit,
        )
        return PlatformMetricsResponse(
            total_active_workspaces=agg.total_active_workspaces,
            total_registered_users=agg.total_registered_users,
            total_tokens_used=agg.total_tokens_used,
            recent_signups=[
                RecentSignup(
                    id=u.id,
                    email=u.email,
                    full_name=u.full_name,
                    created_at=u.created_at,
                )
                for u in signups
            ],
        )
