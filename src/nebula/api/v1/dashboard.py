#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Dashboard summary + daily extraction/failure series — backs the frontend's home page.
@ai-context: Both routes require only get_current_user (no admin gate — see nebular.dashboard's
  module docstring for why).
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import dashboard as dashboard_service
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.models.dashboard import DailySeriesResponse, DashboardSummaryResponse
from nebular.models.tables import UserAccount


class DashboardRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/summary", self.summary, methods=["GET"], response_model=DashboardSummaryResponse
        )
        self.add_api_route(
            "/series", self.series, methods=["GET"], response_model=DailySeriesResponse
        )

    async def summary(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> DashboardSummaryResponse:
        counts = await dashboard_service.summary_counts(session)
        return DashboardSummaryResponse(**counts)

    async def series(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> DailySeriesResponse:
        series = await dashboard_service.extraction_series(session)
        return DailySeriesResponse(**series)


router = DashboardRouter()
