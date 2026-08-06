#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/environment.py.
@ai-context: Environment is global (not project-scoped) since the 2026-08-06 redesign —
  EnvironmentResponse.secret_key_count (across every Project) is what the UI shows as a
  delete-safety hint (nebular.environments.delete_environment 409s via EnvironmentInUseError when
  this is nonzero).
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class EnvironmentCreateRequest(BaseModel):
    name: str
    description: str | None = None


class EnvironmentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    secret_key_count: int
