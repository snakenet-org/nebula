#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey CRUD + value set/reveal — thin wrapper over nebular.secrets.
@ai-context: list_keys/get_key responses carry per-environment PRESENCE ONLY (SecretValueState.
  is_set) — built here by joining nebular.environments.list_environments against
  nebular.secrets.list_values_for_key, never returning ciphertext. Setting a value requires can_edit;
  revealing one requires can_reveal (owner/admin only — see nebular.projects' module docstring for
  why a shared EDITOR can change a value but never decrypt one back).
@ai-rules:
  - Never include SecretValue.ciphertext or a decrypted value in any response except reveal_value's.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import environments as environments_service
from nebular import projects as projects_service
from nebular import secrets as secrets_service
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.models.secret import (
    SecretKeyCreateRequest,
    SecretKeyResponse,
    SecretKeyUpdateRequest,
    SecretRevealResponse,
    SecretValueSetRequest,
    SecretValueState,
)
from nebular.models.tables import SecretKey, UserAccount
from nebular.projects import ProjectNotFoundError
from nebular.secrets import (
    DuplicateSecretKeyNameError,
    SecretKeyNotFoundError,
    SecretValueNotFoundError,
)


async def _to_response(session: AsyncSession, project_id: uuid.UUID, key: SecretKey) -> SecretKeyResponse:
    envs = await environments_service.list_environments(session, project_id)
    values = await secrets_service.list_values_for_key(session, key.id)
    by_env = {v.environment_id: v for v in values}
    states = [
        SecretValueState(
            environment_id=env.id,
            environment_name=env.name,
            is_set=env.id in by_env,
            updated_at=by_env[env.id].updated_at if env.id in by_env else None,
        )
        for env in envs
    ]
    return SecretKeyResponse(
        id=key.id,
        project_id=key.project_id,
        name=key.name,
        description=key.description,
        created_at=key.created_at,
        updated_at=key.updated_at,
        values=states,
    )


class SecretRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/{project_id}", self.list_keys, methods=["GET"], response_model=list[SecretKeyResponse]
        )
        self.add_api_route(
            "/{project_id}", self.create_key, methods=["POST"], response_model=SecretKeyResponse, status_code=201
        )
        self.add_api_route(
            "/{project_id}/{key_id}", self.update_key, methods=["PATCH"], response_model=SecretKeyResponse
        )
        self.add_api_route("/{project_id}/{key_id}", self.delete_key, methods=["DELETE"], status_code=204)
        self.add_api_route(
            "/{project_id}/{key_id}/value", self.set_value, methods=["PUT"], response_model=SecretKeyResponse
        )
        self.add_api_route(
            "/{project_id}/{key_id}/reveal",
            self.reveal_value,
            methods=["GET"],
            response_model=SecretRevealResponse,
        )

    async def _project_or_404(self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID):
        try:
            return await projects_service.get_visible_project(session, actor, project_id)
        except ProjectNotFoundError:
            raise HTTPException(status_code=404, detail="Project not found")

    async def _key_or_404(self, session: AsyncSession, project_id: uuid.UUID, key_id: uuid.UUID) -> SecretKey:
        try:
            return await secrets_service.get_key(session, project_id, key_id)
        except SecretKeyNotFoundError:
            raise HTTPException(status_code=404, detail="Secret key not found")

    async def list_keys(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[SecretKeyResponse]:
        await self._project_or_404(session, actor, project_id)
        rows = await secrets_service.list_keys(session, project_id)
        return [await _to_response(session, project_id, row) for row in rows]

    async def create_key(
        self,
        project_id: uuid.UUID,
        payload: SecretKeyCreateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        try:
            row = await secrets_service.create_key(
                session,
                project_id,
                name=payload.name,
                description=payload.description,
                created_by=actor.id,
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        return await _to_response(session, project_id, row)

    async def update_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretKeyUpdateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        try:
            key = await secrets_service.update_key(
                session, key, name=payload.name, description=payload.description
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        return await _to_response(session, project_id, key)

    async def delete_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        await secrets_service.delete_key(session, key)

    async def set_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretValueSetRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)

        if payload.apply_to_all_environments:
            await secrets_service.set_value_for_all_environments(
                session,
                project_id=project_id,
                secret_key_id=key.id,
                plaintext=payload.value,
                updated_by=actor.id,
            )
        else:
            if payload.environment_id is None:
                raise HTTPException(status_code=422, detail="environment_id is required")
            try:
                await environments_service.get_environment(session, project_id, payload.environment_id)
            except environments_service.EnvironmentNotFoundError:
                raise HTTPException(status_code=404, detail="Environment not found")
            await secrets_service.set_value(
                session,
                secret_key_id=key.id,
                environment_id=payload.environment_id,
                plaintext=payload.value,
                updated_by=actor.id,
            )
        return await _to_response(session, project_id, key)

    async def reveal_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        environment_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretRevealResponse:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_reveal(actor, project):
            raise HTTPException(status_code=403, detail="Only the project owner or an admin may reveal values")
        key = await self._key_or_404(session, project_id, key_id)
        try:
            environment = await environments_service.get_environment(session, project_id, environment_id)
        except environments_service.EnvironmentNotFoundError:
            raise HTTPException(status_code=404, detail="Environment not found")
        try:
            value = await secrets_service.reveal_value(
                session, secret_key_id=key.id, environment_id=environment_id
            )
        except SecretValueNotFoundError:
            raise HTTPException(status_code=404, detail="No value set for this environment")
        return SecretRevealResponse(key=key.name, environment=environment.name, value=value)


router = SecretRouter()
