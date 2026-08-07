#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/environment.py.
@ai-context: Environment is global (not project-scoped) since the 2026-08-06 redesign —
  EnvironmentResponse.secret_key_count (across every Project) is what the UI shows as a
  delete-safety hint (nebula.environments.delete_environment 409s via EnvironmentInUseError when
  this is nonzero). `name` (Create/UpdateRequest) is restricted to nebula.naming's letters/digits/
  hyphen/underscore charset — see that module for why (an Environment name is one of the three
  identifiers api/v1/vault.py's external route addresses by name).
@version: 2.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-07
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from nebula.naming import validate_name


class EnvironmentCreateRequest(BaseModel):
    name: str
    description: str | None = None

    _validate_name = field_validator("name")(validate_name)


class EnvironmentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return value if value is None else validate_name(value)


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    secret_key_count: int
