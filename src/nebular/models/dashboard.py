#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response models for api/v1/dashboard.py.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

from datetime import date

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    environment_count: int
    project_count: int
    variable_count: int
    secret_count: int


class DailySeriesResponse(BaseModel):
    api_extractions: dict[date, int]
    frontend_extractions: dict[date, int]
    failed_retrievals: dict[date, int]
