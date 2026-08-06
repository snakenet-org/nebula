#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Environment CRUD — GLOBAL (not scoped to a Project), thin wrapper over
  nebular.environments.
@ai-context: List/create/update are available to any authenticated caller (an Environment is shared
  infra any project owner needs to be able to add to when creating a key) — delete is admin-only,
  since removing a global Environment can break every Project still linked to it
  (EnvironmentInUseError below surfaces as a 409 rather than letting an admin nuke it silently).
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import audit as audit_service
from nebular import environments as environments_service
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.environments import (
    DuplicateEnvironmentNameError,
    EnvironmentInUseError,
    EnvironmentNotFoundError,
)
from nebular.models.environment import (
    EnvironmentCreateRequest,
    EnvironmentResponse,
    EnvironmentUpdateRequest,
)
from nebular.models.tables import Environment, UserAccount


class EnvironmentRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/", self.list_environments, methods=["GET"], response_model=list[EnvironmentResponse]
        )
        self.add_api_route(
            "/",
            self.create_environment,
            methods=["POST"],
            response_model=EnvironmentResponse,
            status_code=201,
        )
        self.add_api_route(
            "/{environment_id}",
            self.update_environment,
            methods=["PATCH"],
            response_model=EnvironmentResponse,
        )
        self.add_api_route(
            "/{environment_id}", self.delete_environment, methods=["DELETE"], status_code=204
        )

    async def _to_response(self, session: AsyncSession, environment: Environment) -> EnvironmentResponse:
        count = await environments_service.count_keys_using(session, environment.id)
        return EnvironmentResponse(
            id=environment.id,
            name=environment.name,
            description=environment.description,
            created_at=environment.created_at,
            secret_key_count=count,
        )

    async def _environment_or_404(
        self, session: AsyncSession, environment_id: uuid.UUID
    ) -> Environment:
        try:
            return await environments_service.get_environment(session, environment_id)
        except EnvironmentNotFoundError:
            raise HTTPException(status_code=404, detail="Environment not found")

    async def list_environments(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[EnvironmentResponse]:
        rows = await environments_service.list_environments(session)
        return [await self._to_response(session, row) for row in rows]

    async def create_environment(
        self,
        payload: EnvironmentCreateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> EnvironmentResponse:
        try:
            row = await environments_service.create_environment(
                session, name=payload.name, description=payload.description
            )
        except DuplicateEnvironmentNameError:
            raise HTTPException(status_code=409, detail="An environment with this name already exists")
        await audit_service.record_user_action(
            session, actor, request,
            action="environment.create", object_type="environment", object_id=row.id,
            object_label=row.name,
        )
        return await self._to_response(session, row)

    async def update_environment(
        self,
        environment_id: uuid.UUID,
        payload: EnvironmentUpdateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> EnvironmentResponse:
        row = await self._environment_or_404(session, environment_id)
        try:
            row = await environments_service.update_environment(
                session, row, name=payload.name, description=payload.description
            )
        except DuplicateEnvironmentNameError:
            raise HTTPException(status_code=409, detail="An environment with this name already exists")
        await audit_service.record_user_action(
            session, actor, request,
            action="environment.update", object_type="environment", object_id=row.id,
            object_label=row.name,
        )
        return await self._to_response(session, row)

    async def delete_environment(
        self,
        environment_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        if not actor.is_admin:
            raise HTTPException(status_code=403, detail="Only an admin may delete an environment")
        row = await self._environment_or_404(session, environment_id)
        try:
            environment_id_copy, environment_name = row.id, row.name
            await environments_service.delete_environment(session, row)
        except EnvironmentInUseError:
            raise HTTPException(
                status_code=409,
                detail="This environment is still linked from at least one key and cannot be deleted",
            )
        await audit_service.record_user_action(
            session, actor, request,
            action="environment.delete", object_type="environment", object_id=environment_id_copy,
            object_label=environment_name,
        )


router = EnvironmentRouter()
