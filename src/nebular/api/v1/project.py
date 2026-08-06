#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Project CRUD + sharing — thin wrapper over nebular.projects, mirrors how Gravity's
  api/v1/pulsar.py stays thin behind gravity.pulsars.
@ai-context: Every route resolves the actor via get_current_user, then the target Project via
  nebular.projects.get_visible_project (404s for both "doesn't exist" and "not visible to you", so a
  Project id's existence can't be probed). Mutating routes additionally check the relevant
  can_edit/can_manage_sharing/can_delete before calling into nebular.projects — a 403 (not 404) once
  the caller has already proven they can at least view the Project, so "you can see it but not edit
  it" reads as a distinct, honest error from "this doesn't exist." Share-list/manage routes are
  owner+admin only (can_manage_sharing) — a shared viewer/editor cannot see who else the Project is
  shared with, kept deliberately conservative pending an actual UX need to loosen that.
@ai-rules:
  - Never expose ProjectShare rows or Project existence to a caller who fails can_view.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import projects as projects_service
from nebular import users
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.models.project import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectShareCreateRequest,
    ProjectShareResponse,
    ProjectShareUpdateRequest,
    ProjectUpdateRequest,
)
from nebular.models.tables import Project, ProjectShare, ShareRole, UserAccount
from nebular.projects import (
    DuplicateProjectShareError,
    ProjectNotFoundError,
    UnknownShareTargetError,
)


async def _to_response(
    session: AsyncSession, actor: UserAccount, project: Project, share: ProjectShare | None
) -> ProjectResponse:
    owner = await users.get_by_id(session, project.owner_id)
    env_count, key_count = await projects_service.counts_for_project(session, project.id)

    if actor.is_admin:
        my_role = "admin"
    elif project.owner_id == actor.id:
        my_role = "owner"
    elif share is not None and share.role == ShareRole.EDITOR:
        my_role = "editor"
    else:
        my_role = "viewer"

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        owner_name=owner.username if owner else "unknown",
        created_at=project.created_at,
        updated_at=project.updated_at,
        my_role=my_role,
        environment_count=env_count,
        secret_key_count=key_count,
    )


class ProjectRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_api_route("/", self.list_projects, methods=["GET"], response_model=list[ProjectResponse])
        self.add_api_route("/", self.create_project, methods=["POST"], response_model=ProjectResponse, status_code=201)
        self.add_api_route("/{project_id}", self.get_project, methods=["GET"], response_model=ProjectResponse)
        self.add_api_route("/{project_id}", self.update_project, methods=["PATCH"], response_model=ProjectResponse)
        self.add_api_route("/{project_id}", self.delete_project, methods=["DELETE"], status_code=204)
        self.add_api_route(
            "/{project_id}/shares", self.list_shares, methods=["GET"], response_model=list[ProjectShareResponse]
        )
        self.add_api_route(
            "/{project_id}/shares", self.create_share, methods=["POST"], response_model=ProjectShareResponse, status_code=201
        )
        self.add_api_route(
            "/{project_id}/shares/{user_id}", self.update_share, methods=["PATCH"], response_model=ProjectShareResponse
        )
        self.add_api_route(
            "/{project_id}/shares/{user_id}", self.revoke_share, methods=["DELETE"], status_code=204
        )

    async def list_projects(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[ProjectResponse]:
        rows = await projects_service.list_projects(session, actor)
        out = []
        for project in rows:
            share = await projects_service.get_share(session, project.id, actor.id)
            out.append(await _to_response(session, actor, project, share))
        return out

    async def create_project(
        self,
        payload: ProjectCreateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project = await projects_service.create_project(
            session, actor, name=payload.name, description=payload.description
        )
        return await _to_response(session, actor, project, None)

    async def _get_or_404(
        self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID
    ) -> tuple[Project, ProjectShare | None]:
        try:
            return await projects_service.get_visible_project(session, actor, project_id)
        except ProjectNotFoundError:
            raise HTTPException(status_code=404, detail="Project not found")

    async def get_project(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project, share = await self._get_or_404(session, actor, project_id)
        return await _to_response(session, actor, project, share)

    async def update_project(
        self,
        project_id: uuid.UUID,
        payload: ProjectUpdateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project, share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        project = await projects_service.update_project(
            session, project, name=payload.name, description=payload.description
        )
        return await _to_response(session, actor, project, share)

    async def delete_project(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_delete(actor, project):
            raise HTTPException(status_code=403, detail="You cannot delete this project")
        await projects_service.delete_project(session, project)

    async def list_shares(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[ProjectShareResponse]:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_sharing(actor, project):
            raise HTTPException(status_code=403, detail="You cannot view this project's sharing")
        rows = await projects_service.list_shares(session, project_id)
        out = []
        for row in rows:
            user = await users.get_by_id(session, row.user_id)
            out.append(
                ProjectShareResponse(
                    user_id=row.user_id,
                    username=user.username if user else "unknown",
                    email=user.email if user else None,
                    role=row.role,
                    created_at=row.created_at,
                )
            )
        return out

    async def create_share(
        self,
        project_id: uuid.UUID,
        payload: ProjectShareCreateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectShareResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_sharing(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's sharing")
        try:
            share = await projects_service.share_project(
                session, project, username=payload.username, role=payload.role
            )
        except UnknownShareTargetError:
            raise HTTPException(status_code=404, detail="No such user")
        except DuplicateProjectShareError:
            raise HTTPException(status_code=409, detail="Already shared with this user")
        user = await users.get_by_id(session, share.user_id)
        return ProjectShareResponse(
            user_id=share.user_id,
            username=user.username if user else "unknown",
            email=user.email if user else None,
            role=share.role,
            created_at=share.created_at,
        )

    async def update_share(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ProjectShareUpdateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectShareResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_sharing(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's sharing")
        target_share = await projects_service.get_share(session, project_id, user_id)
        if target_share is None:
            raise HTTPException(status_code=404, detail="Not shared with this user")
        target_share = await projects_service.update_share_role(session, target_share, role=payload.role)
        user = await users.get_by_id(session, user_id)
        return ProjectShareResponse(
            user_id=user_id,
            username=user.username if user else "unknown",
            email=user.email if user else None,
            role=target_share.role,
            created_at=target_share.created_at,
        )

    async def revoke_share(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_sharing(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's sharing")
        target_share = await projects_service.get_share(session, project_id, user_id)
        if target_share is None:
            raise HTTPException(status_code=404, detail="Not shared with this user")
        await projects_service.revoke_share(session, target_share)


router = ProjectRouter()
