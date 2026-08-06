#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/project.py.
@ai-context: ProjectResponse.my_role tells the frontend which actions to show without it having to
  re-derive permissions client-side — "owner"/"admin" (full access), "editor" (can edit content, not
  sharing/access-keys/delete/reveal), "viewer" (read-only, masked values only) — see nebular.projects
  for the actual can_view/can_edit/can_reveal/... logic this is computed from.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from nebular.models.tables import ShareRole

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
