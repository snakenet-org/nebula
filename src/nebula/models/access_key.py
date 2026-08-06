#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/access_key.py.
@ai-context: AccessKeyCreateResponse.token is the raw `nbv_...` credential — present ONLY on the
  create response, never again afterward (mirrors Singularity's M2M token pattern). Every other
  response/list model exposes token_prefix only, for UI identification.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AccessKeyCreateRequest(BaseModel):
    name: str


class AccessKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class AccessKeyCreateResponse(AccessKeyResponse):
    token: str
