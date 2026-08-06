#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/secret.py.
@ai-context: Since the 2026-08-06 global-environments redesign, a SecretKey carries exactly one
  Environment link and its own value directly. variable_type (environment/secret,
  nebula.models.tables.VariableType) drives BOTH storage-independent masking rules: a "secret" key's
  SecretKeyResponse.value is always null (is_set is presence-only) — plaintext only ever reaches the
  frontend via the separate can_reveal-gated SecretRevealResponse, fetched on demand. An "environment"
  key's `value` IS included directly in SecretKeyResponse (decrypted server-side in api/v1/secret.py's
  `_to_response`) since it isn't meant to be anonymized — still encrypted at rest identically to a
  secret (see nebula.crypto), the distinction is purely a frontend display/reveal-gating rule, not an
  encryption one.
@version: 3.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from nebula.models.tables import VariableType


class SecretKeyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    environment_id: uuid.UUID
    variable_type: VariableType = VariableType.SECRET


class SecretBulkItem(BaseModel):
    name: str
    value: str


class SecretBulkCreateRequest(BaseModel):
    """Backs the Project view's "Upload .env" flow — every item is a NEW key, none are updates.

    The frontend has already parsed/validated the uploaded file into name/value pairs before this
    ever gets sent — see frontend/src/lib/envFile.js. `environment_id`/`variable_type` apply to
    every item in the batch (there's one confirmation dialog for the whole upload, not one per key).
    """

    environment_id: uuid.UUID
    variable_type: VariableType = VariableType.SECRET
    items: list[SecretBulkItem]


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
    # Populated only for variable_type == ENVIRONMENT (see the module docstring) — always null for a
    # SECRET, which must go through the separate reveal endpoint instead.
    value: str | None = None
    created_at: datetime
    updated_at: datetime


class SecretValueSetRequest(BaseModel):
    value: str


class SecretRevealResponse(BaseModel):
    key: str
    environment: str
    value: str
