#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Project CRUD + sharing — thin wrapper over nebula.projects, mirrors how Gravity's
  api/v1/pulsar.py stays thin behind gravity.pulsars.
@ai-context: Every route resolves the actor via get_current_user, then the target Project via
  nebula.projects.get_visible_project (404s for both "doesn't exist" and "not visible to you", so a
  Project id's existence can't be probed). Mutating routes additionally check the relevant
  can_edit/can_manage_sharing/can_delete before calling into nebula.projects — a 403 (not 404) once
  the caller has already proven they can at least view the Project, so "you can see it but not edit
  it" reads as a distinct, honest error from "this doesn't exist." Share-list/manage routes are
  owner+admin only (can_manage_sharing) — a shared viewer/editor cannot see who else the Project is
  shared with, kept deliberately conservative pending an actual UX need to loosen that.
@ai-rules:
  - Never expose ProjectShare rows or Project existence to a caller who fails can_view.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import github_sync as github_sync_service
from nebula import projects as projects_service
from nebula import users
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.github_sync import GitHubAuthError, GitHubNotConfiguredError, InvalidRepoUrlError
from nebula.models.project import (
    ProjectCreateRequest,
    ProjectGithubConfigRequest,
    ProjectGithubSyncResponse,
    ProjectResponse,
    ProjectShareCreateRequest,
    ProjectShareResponse,
    ProjectShareUpdateRequest,
    ProjectUpdateRequest,
)
from nebula.models.tables import Project, ProjectShare, ShareRole, UserAccount
from nebula.projects import (
    DuplicateProjectShareError,
    ProjectNotFoundError,
    UnknownShareTargetError,
)


async def _to_response(
    session: AsyncSession, actor: UserAccount, project: Project, share: ProjectShare | None
) -> ProjectResponse:
    owner = await users.get_by_id(session, project.owner_id)
    key_count = await projects_service.secret_key_count_for_project(session, project.id)

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
        secret_key_count=key_count,
        github_repo_url=project.github_repo_url,
        github_connected=github_sync_service.has_github_config(project),
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
        self.add_api_route(
            "/{project_id}/github", self.update_github, methods=["PATCH"], response_model=ProjectResponse
        )
        self.add_api_route("/{project_id}/github", self.disconnect_github, methods=["DELETE"], status_code=204)
        self.add_api_route(
            "/{project_id}/github/sync",
            self.sync_github,
            methods=["POST"],
            response_model=ProjectGithubSyncResponse,
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
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project = await projects_service.create_project(
            session, actor, name=payload.name, description=payload.description
        )
        await audit_service.record_user_action(
            session, actor, request,
            action="project.create", object_type="project", object_id=project.id,
            object_label=project.name, project_id=project.id,
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
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project, share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        project = await projects_service.update_project(
            session, project, name=payload.name, description=payload.description
        )
        await audit_service.record_user_action(
            session, actor, request,
            action="project.update", object_type="project", object_id=project.id,
            object_label=project.name, project_id=project.id,
        )
        return await _to_response(session, actor, project, share)

    async def delete_project(
        self,
        project_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_delete(actor, project):
            raise HTTPException(status_code=403, detail="You cannot delete this project")
        project_id_copy, project_name = project.id, project.name
        await projects_service.delete_project(session, project)
        await audit_service.record_user_action(
            session, actor, request,
            action="project.delete", object_type="project", object_id=project_id_copy,
            object_label=project_name, project_id=None,
        )

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
        request: Request,
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
        await audit_service.record_user_action(
            session, actor, request,
            action="share.create", object_type="project_share", object_id=project.id,
            object_label=f"{project.name} → {payload.username} ({share.role})", project_id=project.id,
        )
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
        request: Request,
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
        await audit_service.record_user_action(
            session, actor, request,
            action="share.update", object_type="project_share", object_id=project.id,
            object_label=f"{project.name} → {user.username if user else user_id} ({target_share.role})",
            project_id=project.id,
        )
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
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_sharing(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's sharing")
        target_share = await projects_service.get_share(session, project_id, user_id)
        if target_share is None:
            raise HTTPException(status_code=404, detail="Not shared with this user")
        user = await users.get_by_id(session, user_id)
        await projects_service.revoke_share(session, target_share)
        await audit_service.record_user_action(
            session, actor, request,
            action="share.revoke", object_type="project_share", object_id=project.id,
            object_label=f"{project.name} → {user.username if user else user_id}", project_id=project.id,
        )

    async def update_github(
        self,
        project_id: uuid.UUID,
        payload: ProjectGithubConfigRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectResponse:
        project, share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        try:
            project = await github_sync_service.update_github_config(
                session, project, repo_url=payload.repo_url, pat=payload.pat
            )
        except InvalidRepoUrlError:
            raise HTTPException(status_code=422, detail="Not a valid GitHub repository URL")
        await audit_service.record_user_action(
            session, actor, request,
            action="project.github_config_update", object_type="project", object_id=project.id,
            object_label=project.name, project_id=project.id,
        )
        return await _to_response(session, actor, project, share)

    async def disconnect_github(
        self,
        project_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        await github_sync_service.clear_github_config(session, project)
        await audit_service.record_user_action(
            session, actor, request,
            action="project.github_disconnect", object_type="project", object_id=project.id,
            object_label=project.name, project_id=project.id,
        )

    async def sync_github(
        self,
        project_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectGithubSyncResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        try:
            result = await github_sync_service.sync_to_github(session, project)
        except GitHubNotConfiguredError:
            raise HTTPException(status_code=409, detail="GitHub is not configured for this project")
        except InvalidRepoUrlError:
            raise HTTPException(status_code=422, detail="Not a valid GitHub repository URL")
        except GitHubAuthError as exc:
            await audit_service.record_user_action(
                session, actor, request,
                action="project.github_sync", object_type="project", object_id=project.id,
                object_label=project.name, project_id=project.id,
                success=False, detail=str(exc),
            )
            raise HTTPException(status_code=502, detail=f"GitHub authentication failed: {exc}")

        detail = (
            f"{result['secrets_synced']} secret(s), {result['variables_synced']} variable(s) across "
            f"{result['environments_synced']} environment(s)"
            + (f"; {len(result['failures'])} failure(s)" if result["failures"] else "")
        )
        await audit_service.record_user_action(
            session, actor, request,
            action="project.github_sync", object_type="project", object_id=project.id,
            object_label=project.name, project_id=project.id,
            success=not result["failures"], detail=detail,
        )
        return ProjectGithubSyncResponse(**result)


router = ProjectRouter()
