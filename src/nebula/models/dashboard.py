#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response models for api/v1/dashboard.py.
@ai-context: `api_requests`/`failed_attempts` renamed from `api_extractions`/`failed_retrievals`
  2026-08-07 — both now count every call to any api/v1/vault.py route (see
  nebula.dashboard.extraction_series), not just /secret. Internal API, no external consumers, so
  the field rename isn't a compat concern.
  2026-08-27: new `certificate_count` — VariableType.CERTIFICATE (nebula.models.tables) is a third
  variable_type alongside ENVIRONMENT/SECRET, counted the same way secret_count already is (see
  nebula.dashboard.summary_counts) so the three counts stay a true partition of every SecretKey in
  scope instead of silently dropping certificates from the Dashboard entirely.
@version: 1.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-27
"""

from datetime import date

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    environment_count: int
    project_count: int
    variable_count: int
    secret_count: int
    certificate_count: int


class DailySeriesResponse(BaseModel):
    api_requests: dict[date, int]
    frontend_extractions: dict[date, int]
    failed_attempts: dict[date, int]
