#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response models for api/v1/audit.py.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from nebular.models.tables import ActorType


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_type: ActorType
    actor_label: str | None
    action: str
    object_type: str | None
    object_label: str | None
    project_id: uuid.UUID | None
    success: bool
    detail: str | None
    ip_address: str | None
