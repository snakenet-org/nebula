#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey CRUD + value set/reveal — thin wrapper over nebular.secrets.
@ai-context: Since the 2026-08-06 global-environments redesign, a key carries exactly one
  Environment link; list_keys/get_key responses carry PRESENCE ONLY (is_set), never ciphertext.
  Setting a value or reassigning environment_id requires can_edit; revealing one requires can_reveal
  (owner/admin only — see nebular.projects' module docstring for why a shared EDITOR can change a
  value but never decrypt one back).
@ai-rules:
  - Never include SecretKey.ciphertext or a decrypted value in any response except reveal_value's.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
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
)
from nebular.models.tables import SecretKey, UserAccount
from nebular.projects import ProjectNotFoundError
from nebular.secrets import (
    DuplicateSecretKeyNameError,
    SecretKeyNotFoundError,
    SecretValueNotFoundError,
)


async def _to_response(session: AsyncSession, key: SecretKey) -> SecretKeyResponse:
    environment = await environments_service.get_environment(session, key.environment_id)
    return SecretKeyResponse(
        id=key.id,
        project_id=key.project_id,
        name=key.name,
        description=key.description,
        environment_id=key.environment_id,
        environment_name=environment.name,
        variable_type=key.variable_type,
        is_set=key.ciphertext is not None,
        created_at=key.created_at,
        updated_at=key.updated_at,
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

    async def _environment_or_404(self, session: AsyncSession, environment_id: uuid.UUID) -> None:
        try:
            await environments_service.get_environment(session, environment_id)
        except environments_service.EnvironmentNotFoundError:
            raise HTTPException(status_code=404, detail="Environment not found")

    async def list_keys(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[SecretKeyResponse]:
        await self._project_or_404(session, actor, project_id)
        rows = await secrets_service.list_keys(session, project_id)
        return [await _to_response(session, row) for row in rows]

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
        await self._environment_or_404(session, payload.environment_id)
        try:
            row = await secrets_service.create_key(
                session,
                project_id,
                name=payload.name,
                description=payload.description,
                environment_id=payload.environment_id,
                variable_type=payload.variable_type,
                created_by=actor.id,
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        return await _to_response(session, row)

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
        if payload.environment_id is not None:
            await self._environment_or_404(session, payload.environment_id)
        try:
            key = await secrets_service.update_key(
                session,
                key,
                name=payload.name,
                description=payload.description,
                environment_id=payload.environment_id,
                variable_type=payload.variable_type,
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        return await _to_response(session, key)

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
        key = await secrets_service.set_value(session, key, plaintext=payload.value, updated_by=actor.id)
        return await _to_response(session, key)

    async def reveal_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretRevealResponse:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_reveal(actor, project):
            raise HTTPException(status_code=403, detail="Only the project owner or an admin may reveal values")
        key = await self._key_or_404(session, project_id, key_id)
        environment = await environments_service.get_environment(session, key.environment_id)
        try:
            value = await secrets_service.reveal_value(session, key)
        except SecretValueNotFoundError:
            raise HTTPException(status_code=404, detail="No value set for this key")
        return SecretRevealResponse(key=key.name, environment=environment.name, value=value)


router = SecretRouter()
