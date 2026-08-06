#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/secret.py.
@ai-context: SecretKeyResponse.values carries per-environment PRESENCE ONLY (is_set) — never
  ciphertext or plaintext, so a project's secret list is safe to send to any viewer regardless of
  can_reveal. Revealing one value is a separate call (SecretRevealResponse), gated by can_reveal,
  fetched on demand — see nebular.secrets.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SecretKeyCreateRequest(BaseModel):
    name: str
    description: str | None = None


class SecretKeyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SecretValueState(BaseModel):
    environment_id: uuid.UUID
    environment_name: str
    is_set: bool
    updated_at: datetime | None


class SecretKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    values: list[SecretValueState]


class SecretValueSetRequest(BaseModel):
    value: str
    # When true, this value is written to every environment the project currently has (a
    # convenience for a key like ADMIN_EMAIL that's genuinely the same across environments) —
    # `environment_id` is ignored in that case.
    apply_to_all_environments: bool = False
    environment_id: uuid.UUID | None = None


class SecretRevealResponse(BaseModel):
    key: str
    environment: str
    value: str
