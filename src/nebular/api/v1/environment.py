#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Environment CRUD, scoped to a Project — thin wrapper over nebular.environments.
@ai-context: Every route resolves the Project via nebular.projects.get_visible_project first (404
  for not-visible), then checks can_view (list) or can_edit (create/delete) before delegating.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import environments as environments_service
from nebular import projects as projects_service
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.environments import DuplicateEnvironmentNameError, EnvironmentNotFoundError
from nebular.models.environment import EnvironmentCreateRequest, EnvironmentResponse
from nebular.models.tables import UserAccount
from nebular.projects import ProjectNotFoundError


class EnvironmentRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/{project_id}", self.list_environments, methods=["GET"], response_model=list[EnvironmentResponse]
        )
        self.add_api_route(
            "/{project_id}", self.create_environment, methods=["POST"], response_model=EnvironmentResponse, status_code=201
        )
        self.add_api_route(
            "/{project_id}/{environment_id}", self.delete_environment, methods=["DELETE"], status_code=204
        )

    async def _project_or_404(self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID):
        try:
            return await projects_service.get_visible_project(session, actor, project_id)
        except ProjectNotFoundError:
            raise HTTPException(status_code=404, detail="Project not found")

    async def list_environments(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[EnvironmentResponse]:
        await self._project_or_404(session, actor, project_id)
        rows = await environments_service.list_environments(session, project_id)
        return [EnvironmentResponse.model_validate(row, from_attributes=True) for row in rows]

    async def create_environment(
        self,
        project_id: uuid.UUID,
        payload: EnvironmentCreateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> EnvironmentResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        try:
            row = await environments_service.create_environment(session, project_id, name=payload.name)
        except DuplicateEnvironmentNameError:
            raise HTTPException(status_code=409, detail="An environment with this name already exists")
        return EnvironmentResponse.model_validate(row, from_attributes=True)

    async def delete_environment(
        self,
        project_id: uuid.UUID,
        environment_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        try:
            row = await environments_service.get_environment(session, project_id, environment_id)
        except EnvironmentNotFoundError:
            raise HTTPException(status_code=404, detail="Environment not found")
        await environments_service.delete_environment(session, row)


router = EnvironmentRouter()
