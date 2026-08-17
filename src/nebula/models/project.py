#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/project.py.
@ai-context: ProjectResponse.my_role tells the frontend which actions to show without it having to
  re-derive permissions client-side — "owner"/"admin" (full access, including delete/transfer),
  "editor" (since 2026-08-17: everything a viewer can do, PLUS can rename/delete/reassign-
  environment/toggle-sync a key, set/change a key's value, and manage project settings — sharing,
  API access keys, GitHub sync config — but still cannot delete or transfer the Project itself),
  "viewer" (since 2026-08-17: can view the project and reveal+copy a secret/variable's value, but
  cannot edit anything or see/change project settings) — see nebula.projects for the actual
  can_view/can_edit/can_reveal/can_edit_value/can_manage_sharing/can_manage_access_keys/
  can_manage_github/... logic this is computed from. Since the 2026-08-06
  multi-repo GitHub sync redesign, a Project's GitHub config is no longer embedded in ProjectResponse
  (it was a single repo_url/connected pair before) — it's now a separate list of
  ProjectGithubSyncResponse rows, fetched the same way shares/access-keys already are (see
  api/v1/project.py's /github/targets routes). The PAT itself never appears in any response, see
  ProjectGithubSyncCreateRequest/ProjectGithubSyncUpdateRequest. `name` (Create/UpdateRequest) is
  restricted to nebula.naming's letters/digits/hyphen/underscore charset — see that module for why
  (a Project name is one of the three identifiers api/v1/vault.py's external route addresses by
  name).
  Since 2026-08-08, a sync target's PAT is EITHER `pat` (a custom token, unchanged) OR
  `pat_source_key_id` (a reference to another SecretKey elsewhere in the vault — see
  nebula.github_sync's module docstring). CreateRequest requires EXACTLY one of the two
  (`_validate_pat_mode`); UpdateRequest allows AT MOST one (both omitted = leave the current PAT
  config, whichever mode it's in, untouched — the same "blank pat = unchanged" convention this
  already had, just extended to cover the new field too). ProjectGithubSyncTargetResponse exposes
  `pat_source_key_id` plus a resolved, display-only `pat_source_project_id`/`pat_source_label` —
  populated by api/v1/project.py only when the CURRENT viewer can actually see that other Project
  (nebula.projects.can_view), so this response never leaks the existence/name of a Project or key
  the viewer has no visibility into, even though the reference itself may have been configured by a
  different admin who could see it.
  Since 2026-08-09, ProjectTransferRequest backs the danger-zone "transfer ownership" action
  (api/v1/project.py's POST /{project_id}/transfer) — just the target username, mirroring
  ProjectShareCreateRequest's shape.
  2026-08-17: MyRole's doc comment above rewritten for the permission-matrix rework (see
  nebula.projects' module docstring) — the Literal values themselves are unchanged.
@version: 4.3.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-17
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from nebula.models.tables import ShareRole
from nebula.naming import validate_name

MyRole = Literal["owner", "admin", "editor", "viewer"]


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None

    _validate_name = field_validator("name")(validate_name)


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        return value if value is None else validate_name(value)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    owner_name: str
    created_at: datetime
    updated_at: datetime
    my_role: MyRole
    secret_key_count: int


class ProjectGithubSyncTargetCreateRequest(BaseModel):
    repo_url: str
    name: str | None = None
    # Exactly one of these two — see _validate_pat_mode below.
    pat: str | None = None
    pat_source_key_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _validate_pat_mode(self) -> "ProjectGithubSyncTargetCreateRequest":
        if bool(self.pat) == bool(self.pat_source_key_id):
            raise ValueError(
                "Provide exactly one of `pat` (a custom token) or `pat_source_key_id` "
                "(a reference to another secret)."
            )
        return self


class ProjectGithubSyncTargetUpdateRequest(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    # Blank/omitted `pat` AND omitted `pat_source_key_id` leaves the currently-stored PAT config
    # (whichever mode it's in) untouched — see nebula.github_sync.update_sync_target.
    pat: str | None = None
    pat_source_key_id: uuid.UUID | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _validate_pat_mode(self) -> "ProjectGithubSyncTargetUpdateRequest":
        if self.pat and self.pat_source_key_id is not None:
            raise ValueError(
                "Provide at most one of `pat` (a custom token) or `pat_source_key_id` "
                "(a reference to another secret)."
            )
        return self


class ProjectGithubSyncTargetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    repo_url: str
    enabled: bool
    # "reference" mode when set, "custom" mode when null — see the module docstring above.
    pat_source_key_id: uuid.UUID | None
    # Resolved display info for `pat_source_key_id`, only populated when the current viewer can
    # actually see that other Project — both null in "custom" mode too.
    pat_source_project_id: uuid.UUID | None
    pat_source_label: str | None
    last_synced_at: datetime | None
    last_sync_success: bool | None
    last_sync_detail: str | None
    created_at: datetime
    updated_at: datetime


class ProjectGithubSyncResultResponse(BaseModel):
    target_id: uuid.UUID
    name: str
    repo_url: str
    success: bool
    error: str | None
    environments_synced: int
    secrets_synced: int
    variables_synced: int
    failures: list[str]


class ProjectTransferRequest(BaseModel):
    username: str


class ProjectShareCreateRequest(BaseModel):
    username: str
    role: ShareRole = ShareRole.VIEWER


class ProjectShareUpdateRequest(BaseModel):
    role: ShareRole


class ProjectShareResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str | None
    role: ShareRole
    created_at: datetime
