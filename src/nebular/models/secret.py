#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/secret.py.
@ai-context: Since the 2026-08-06 global-environments redesign, a SecretKey carries exactly one
  Environment link and its own value directly — SecretKeyResponse.is_set is PRESENCE ONLY (never
  ciphertext or plaintext), so a project's key list is safe to send to any viewer regardless of
  can_reveal. Revealing the value is a separate call (SecretRevealResponse), gated by can_reveal,
  fetched on demand — see nebular.secrets. variable_type (environment/secret,
  nebular.models.tables.VariableType) drives the frontend's default masking: a "secret" is always
  masked until revealed, an "environment" variable renders in the clear (still encrypted at rest
  either way — see the 2026-08-06 CLAUDE.md entry).
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from nebular.models.tables import VariableType


class SecretKeyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    environment_id: uuid.UUID
    variable_type: VariableType = VariableType.SECRET


class SecretKeyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    environment_id: uuid.UUID | None = None
    variable_type: VariableType | None = None


class SecretKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    environment_id: uuid.UUID
    environment_name: str
    variable_type: VariableType
    is_set: bool
    created_at: datetime
    updated_at: datetime


class SecretValueSetRequest(BaseModel):
    value: str


class SecretRevealResponse(BaseModel):
    key: str
    environment: str
    value: str
