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
  shared with, kept deliberately conservative pending an actual UX need to loosen that. GitHub sync
  target routes (/github/targets*) are the multi-repo redesign's CRUD surface — same can_manage_github
  (owner/admin) gate as before, now per-target instead of per-project singular config; /github/sync
  fans out to every enabled target (nebula.github_sync.sync_all_for_project) — the same fan-out
  api/v1/secret.py's mutating routes now call automatically after every value change.
@ai-rules:
  - Never expose ProjectShare rows, a sync target's PAT, or Project existence to a caller who fails
    can_view/can_manage_github respectively.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 3.0.0
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
from nebula.github_sync import GitHubAuthError, GitHubSyncTargetNotFoundError, InvalidRepoUrlError
from nebula.models.project import (
    ProjectCreateRequest,
    ProjectGithubSyncResultResponse,
    ProjectGithubSyncTargetCreateRequest,
    ProjectGithubSyncTargetResponse,
    ProjectGithubSyncTargetUpdateRequest,
    ProjectResponse,
    ProjectShareCreateRequest,
    ProjectShareResponse,
    ProjectShareUpdateRequest,
    ProjectUpdateRequest,
)
from nebula.models.tables import Project, ProjectGithubSync, ProjectShare, ShareRole, UserAccount
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
    )


def _to_target_response(target: ProjectGithubSync) -> ProjectGithubSyncTargetResponse:
    return ProjectGithubSyncTargetResponse(
        id=target.id,
        project_id=target.project_id,
        name=github_sync_service.target_display_name(target),
        repo_url=target.repo_url,
        enabled=target.enabled,
        last_synced_at=target.last_synced_at,
        last_sync_success=target.last_sync_success,
        last_sync_detail=target.last_sync_detail,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


def _to_result_response(result: github_sync_service.SyncResult) -> ProjectGithubSyncResultResponse:
    return ProjectGithubSyncResultResponse(**result)


def _summarize(result: github_sync_service.SyncResult) -> str:
    detail = (
        f"{result['secrets_synced']} secret(s), {result['variables_synced']} variable(s) across "
        f"{result['environments_synced']} environment(s)"
    )
    if result["failures"]:
        detail += f"; {len(result['failures'])} failure(s)"
    return detail


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
            "/{project_id}/github/targets",
            self.list_github_targets,
            methods=["GET"],
            response_model=list[ProjectGithubSyncTargetResponse],
        )
        self.add_api_route(
            "/{project_id}/github/targets",
            self.create_github_target,
            methods=["POST"],
            response_model=ProjectGithubSyncTargetResponse,
            status_code=201,
        )
        self.add_api_route(
            "/{project_id}/github/targets/{target_id}",
            self.update_github_target,
            methods=["PATCH"],
            response_model=ProjectGithubSyncTargetResponse,
        )
        self.add_api_route(
            "/{project_id}/github/targets/{target_id}",
            self.delete_github_target,
            methods=["DELETE"],
            status_code=204,
        )
        self.add_api_route(
            "/{project_id}/github/targets/{target_id}/sync",
            self.sync_github_target,
            methods=["POST"],
            response_model=ProjectGithubSyncResultResponse,
        )
        self.add_api_route(
            "/{project_id}/github/sync",
            self.sync_github_all,
            methods=["POST"],
            response_model=list[ProjectGithubSyncResultResponse],
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

    async def _github_target_or_404(
        self, session: AsyncSession, project_id: uuid.UUID, target_id: uuid.UUID
    ) -> ProjectGithubSync:
        try:
            return await github_sync_service.get_sync_target(session, project_id, target_id)
        except GitHubSyncTargetNotFoundError:
            raise HTTPException(status_code=404, detail="GitHub sync target not found")

    async def list_github_targets(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[ProjectGithubSyncTargetResponse]:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        targets = await github_sync_service.list_sync_targets(session, project_id)
        return [_to_target_response(t) for t in targets]

    async def create_github_target(
        self,
        project_id: uuid.UUID,
        payload: ProjectGithubSyncTargetCreateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectGithubSyncTargetResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        try:
            target = await github_sync_service.create_sync_target(
                session, project, repo_url=payload.repo_url, pat=payload.pat, name=payload.name
            )
        except InvalidRepoUrlError:
            raise HTTPException(status_code=422, detail="Not a valid GitHub repository URL")
        await audit_service.record_user_action(
            session, actor, request,
            action="github_sync_target.create", object_type="project_github_sync", object_id=target.id,
            object_label=github_sync_service.target_display_name(target), project_id=project.id,
        )
        return _to_target_response(target)

    async def update_github_target(
        self,
        project_id: uuid.UUID,
        target_id: uuid.UUID,
        payload: ProjectGithubSyncTargetUpdateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectGithubSyncTargetResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        target = await self._github_target_or_404(session, project_id, target_id)
        try:
            target = await github_sync_service.update_sync_target(
                session,
                target,
                name=payload.name,
                repo_url=payload.repo_url,
                pat=payload.pat,
                enabled=payload.enabled,
            )
        except InvalidRepoUrlError:
            raise HTTPException(status_code=422, detail="Not a valid GitHub repository URL")
        await audit_service.record_user_action(
            session, actor, request,
            action="github_sync_target.update", object_type="project_github_sync", object_id=target.id,
            object_label=github_sync_service.target_display_name(target), project_id=project.id,
        )
        return _to_target_response(target)

    async def delete_github_target(
        self,
        project_id: uuid.UUID,
        target_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        target = await self._github_target_or_404(session, project_id, target_id)
        target_id_copy, target_label = target.id, github_sync_service.target_display_name(target)
        await github_sync_service.delete_sync_target(session, target)
        await audit_service.record_user_action(
            session, actor, request,
            action="github_sync_target.delete", object_type="project_github_sync", object_id=target_id_copy,
            object_label=target_label, project_id=project.id,
        )

    async def sync_github_target(
        self,
        project_id: uuid.UUID,
        target_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectGithubSyncResultResponse:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        target = await self._github_target_or_404(session, project_id, target_id)
        try:
            outcome = await github_sync_service.sync_to_github(session, target)
            result: github_sync_service.SyncResult = {
                "target_id": target.id,
                "name": github_sync_service.target_display_name(target),
                "repo_url": target.repo_url,
                "success": not outcome["failures"],
                "error": None,
                **outcome,
            }
        except GitHubAuthError as exc:
            result = {
                "target_id": target.id,
                "name": github_sync_service.target_display_name(target),
                "repo_url": target.repo_url,
                "success": False,
                "error": str(exc),
                "environments_synced": 0,
                "secrets_synced": 0,
                "variables_synced": 0,
                "failures": [],
            }
        await audit_service.record_user_action(
            session, actor, request,
            action="github_sync_target.sync", object_type="project_github_sync", object_id=target.id,
            object_label=result["name"], project_id=project.id,
            success=result["success"], detail=result["error"] or _summarize(result),
        )
        return _to_result_response(result)

    async def sync_github_all(
        self,
        project_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[ProjectGithubSyncResultResponse]:
        project, _share = await self._get_or_404(session, actor, project_id)
        if not projects_service.can_manage_github(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's GitHub sync")
        results = await github_sync_service.sync_all_for_project(session, project_id)
        for result in results:
            await audit_service.record_user_action(
                session, actor, request,
                action="github_sync_target.sync", object_type="project_github_sync",
                object_id=result["target_id"], object_label=result["name"], project_id=project.id,
                success=result["success"], detail=result["error"] or _summarize(result),
            )
        return [_to_result_response(r) for r in results]


router = ProjectRouter()
