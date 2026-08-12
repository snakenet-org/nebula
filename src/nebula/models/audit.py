#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response models for api/v1/audit.py.
@ai-context: 2026-08-12: AuditLogEntryResponse gained `project_label` (the resolved Project's name,
  captured at write time — see models.tables.AuditLogEntry.project_label), populated for
  ActorType.ACCESS_KEY rows and shown as the "API calls" tab's new Project column. Every list route
  now returns AuditLogPageResponse instead of a bare list — the log pages, 300 rows max per page
  (nebula.audit.MAX_PAGE_SIZE), so the frontend needs `total` to render pagination controls.
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from nebula.models.tables import ActorType


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_type: ActorType
    actor_label: str | None
    action: str
    object_type: str | None
    object_label: str | None
    project_id: uuid.UUID | None
    project_label: str | None
    success: bool
    detail: str | None
    ip_address: str | None


class AuditLogPageResponse(BaseModel):
    items: list[AuditLogEntryResponse]
    total: int
    page: int
    page_size: int
