#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/environment.py.
@ai-context: Environment is global (not project-scoped) since the 2026-08-06 redesign —
  EnvironmentResponse.secret_key_count (across every Project) is what the UI shows as a
  delete-safety hint (nebula.environments.delete_environment 409s via EnvironmentInUseError when
  this is nonzero). `name` (Create/UpdateRequest) is restricted to nebula.naming's letters/digits/
  hyphen/underscore charset — see that module for why (an Environment name is one of the three
  identifiers api/v1/vault.py's external route addresses by name; that charset already has no room
  for a line break, so name needs no separate stripping here).
  2026-08-12 (GitHub #6): `description` now strips any `\\r`/`\\n` a caller sends (silently, not a
  422 — same "keep the field's actual value honest" reasoning Gravity's own pulsar-editing fix used
  for a pasted line break in a single-line field) so an Environment's description can never actually
  contain a line break, matching EnvironmentsView.vue's own frontend-side stripping on both the
  create form and the edit dialog (which also switched from a multi-line Textarea to a plain
  single-line Input for the same reason — description was the only field that previously allowed a
  REAL newline via Enter, not just a pasted one).
@version: 2.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from nebula.naming import validate_name


def _strip_line_breaks(value: str | None) -> str | None:
    return value if value is None else value.replace("\r", "").replace("\n", "")


class EnvironmentCreateRequest(BaseModel):
    name: str
    description: str | None = None

    _validate_name = field_validator("name")(validate_name)
    _strip_description = field_validator("description")(_strip_line_breaks)


class EnvironmentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return value if value is None else validate_name(value)

    _strip_description = field_validator("description")(_strip_line_breaks)


class EnvironmentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    secret_key_count: int
