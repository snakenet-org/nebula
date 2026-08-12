#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Dashboard summary + daily extraction/failure series — backs the frontend's home page.
@ai-context: Both routes require only get_current_user (no admin gate). GitHub #4: an admin sees
  system-wide data (project_ids=None); a non-admin is scoped to
  `nebula.projects.list_editable_project_ids` (Projects they own or are an EDITOR share on) — see
  nebula.dashboard's module docstring for exactly what that means per stat/series.
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import dashboard as dashboard_service
from nebula import projects as projects_service
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.dashboard import DailySeriesResponse, DashboardSummaryResponse
from nebula.models.tables import UserAccount


class DashboardRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/summary", self.summary, methods=["GET"], response_model=DashboardSummaryResponse
        )
        self.add_api_route(
            "/series", self.series, methods=["GET"], response_model=DailySeriesResponse
        )

    @staticmethod
    async def _scope(session: AsyncSession, actor: UserAccount) -> list[uuid.UUID] | None:
        """None (unscoped) for an admin; the caller's owned+editor Project ids otherwise."""
        if actor.is_admin:
            return None
        return await projects_service.list_editable_project_ids(session, actor)

    async def summary(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> DashboardSummaryResponse:
        project_ids = await self._scope(session, actor)
        counts = await dashboard_service.summary_counts(session, project_ids=project_ids)
        return DashboardSummaryResponse(**counts)

    async def series(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> DailySeriesResponse:
        project_ids = await self._scope(session, actor)
        series = await dashboard_service.extraction_series(session, project_ids=project_ids)
        return DailySeriesResponse(**series)


router = DashboardRouter()
