#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/project.py.
@ai-context: ProjectResponse.my_role tells the frontend which actions to show without it having to
  re-derive permissions client-side — "owner"/"admin" (full access), "editor" (can edit content, not
  sharing/access-keys/delete/reveal), "viewer" (read-only, masked values only) — see nebula.projects
  for the actual can_view/can_edit/can_reveal/... logic this is computed from. Since the 2026-08-06
  multi-repo GitHub sync redesign, a Project's GitHub config is no longer embedded in ProjectResponse
  (it was a single repo_url/connected pair before) — it's now a separate list of
  ProjectGithubSyncResponse rows, fetched the same way shares/access-keys already are (see
  api/v1/project.py's /github/targets routes). The PAT itself never appears in any response, see
  ProjectGithubSyncCreateRequest/ProjectGithubSyncUpdateRequest.
@version: 3.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from nebula.models.tables import ShareRole

MyRole = Literal["owner", "admin", "editor", "viewer"]


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


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
    pat: str
    name: str | None = None


class ProjectGithubSyncTargetUpdateRequest(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    # Blank/omitted leaves the currently-stored PAT untouched — see
    # nebula.github_sync.update_sync_target.
    pat: str | None = None
    enabled: bool | None = None


class ProjectGithubSyncTargetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    repo_url: str
    enabled: bool
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
