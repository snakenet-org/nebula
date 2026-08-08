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
  encryption one. `name` (SecretKeyCreateRequest/SecretKeyUpdateRequest/SecretBulkItem) is restricted
  to nebula.naming's letters/digits/hyphen/underscore charset — see that module for why (a key is one
  of the three identifiers api/v1/vault.py's external route addresses by name).
  SecretKeyCreateRequest.value (added 2026-08-07) is optional — the create form can set an initial
  value in the same call instead of requiring a separate value-set round trip afterward; omitting it
  (or sending blank) creates the key with no value yet, exactly as before.
  `sync_enabled` (2026-08-08) is a per-key on/off toggle for GitHub sync — defaults true on create,
  optional on update (omitted means unchanged), always present on SecretKeyResponse.
  Since 2026-08-09, SecretKeyCreateRequest.source_key_id makes the new key a REFERENCE to another
  SecretKey's value instead of owning one directly — mutually exclusive with `value`
  (`_validate_reference_mode`, mirroring ProjectGithubSyncTargetCreateRequest's PAT-mode validator in
  models/project.py); api/v1/secret.py permission-checks it (can_reveal on the referenced key's OWN
  Project, and that it isn't itself a reference — no chaining) before ever calling into
  nebula.secrets.create_key. There is deliberately no `source_key_id` on SecretKeyUpdateRequest yet —
  switching an existing key's reference target isn't supported (create a new reference key instead).
  SecretKeyResponse's `variable_type`/`is_set`/`value` all reflect the RESOLVED value (the source
  key's, for a reference — nebula.secrets.resolve_effective), never this row's own possibly-stale/
  irrelevant columns; `source_key_id` is non-null only for a reference, and `source_project_id`/
  `source_label` are its resolved display info — populated only when the CURRENT viewer can actually
  see that other Project (nebula.projects.can_view), same display-vs-permission split as
  ProjectGithubSyncTargetResponse's `pat_source_label` in models/project.py.
@version: 4.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-09
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from nebula.models.tables import VariableType
from nebula.naming import validate_name


class SecretKeyCreateRequest(BaseModel):
    name: str
    description: str | None = None
    environment_id: uuid.UUID
    variable_type: VariableType = VariableType.SECRET
    value: str | None = None
    sync_enabled: bool = True
    # Makes this a reference to another SecretKey's value instead — see the module docstring.
    source_key_id: uuid.UUID | None = None

    _validate_name = field_validator("name")(validate_name)

    @model_validator(mode="after")
    def _validate_reference_mode(self) -> "SecretKeyCreateRequest":
        if self.source_key_id is not None and self.value:
            raise ValueError(
                "A referenced key's value comes from its source — do not set one directly."
            )
        return self


class SecretBulkItem(BaseModel):
    name: str
    value: str
    variable_type: VariableType = VariableType.SECRET

    _validate_name = field_validator("name")(validate_name)


class SecretBulkCreateRequest(BaseModel):
    """Backs the Project view's "Upload .env" flow — every item is a NEW key, none are updates.

    The frontend has already parsed/validated the uploaded file into name/value pairs before this
    ever gets sent — see frontend/src/lib/envFile.js. `environment_id` applies to every item in the
    batch (there's one confirmation dialog for the whole upload, not one per key) — `variable_type`
    is chosen per item instead (the review dialog's per-row Type Select), and a row the user toggled
    off in that dialog is simply never included here, so "skip on import" needs no field of its own.
    """

    environment_id: uuid.UUID
    items: list[SecretBulkItem]


class SecretKeyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    environment_id: uuid.UUID | None = None
    variable_type: VariableType | None = None
    sync_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return value if value is None else validate_name(value)


class SecretKeyResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    environment_id: uuid.UUID
    environment_name: str
    # Resolved (via nebula.secrets.resolve_effective) — for a reference key this is the SOURCE key's
    # CURRENT type, never this row's own possibly-stale column.
    variable_type: VariableType
    is_set: bool
    # Populated only for variable_type == ENVIRONMENT (see the module docstring) — always null for a
    # SECRET, which must go through the separate reveal endpoint instead.
    value: str | None = None
    # Per-key GitHub sync toggle (nebula.github_sync) — false means this key is skipped by every
    # sync target's push, automatic or manual.
    sync_enabled: bool
    # Non-null only when this key is a reference to another SecretKey's value (see the module
    # docstring) — its value/type are then locked to that source key, editable only there.
    source_key_id: uuid.UUID | None = None
    # Resolved display info for source_key_id, only populated when the current viewer can actually
    # see that other Project (nebula.projects.can_view) — both null otherwise, same
    # display-vs-permission split as ProjectGithubSyncTargetResponse.pat_source_label.
    source_project_id: uuid.UUID | None = None
    source_label: str | None = None
    created_at: datetime
    updated_at: datetime


class SecretValueSetRequest(BaseModel):
    value: str


class SecretRevealResponse(BaseModel):
    key: str
    environment: str
    value: str
