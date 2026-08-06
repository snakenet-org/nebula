#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey CRUD + value set/reveal — thin wrapper over nebula.secrets.
@ai-context: Since the 2026-08-06 global-environments redesign, a key carries exactly one
  Environment link; list_keys/get_key responses carry PRESENCE ONLY (is_set), never ciphertext.
  Setting a value or reassigning environment_id requires can_edit; revealing one requires can_reveal
  (owner/admin only — see nebula.projects' module docstring for why a shared EDITOR can change a
  value but never decrypt one back). bulk_create_keys backs the Project view's "Upload .env" button —
  same can_edit gate, always creates brand-new keys (409s naming every conflict rather than updating
  an existing key); one Environment applies to the whole batch, but `variable_type` is per-item
  (SecretBulkItem) so the review dialog can pick secret vs. environment variable per row.
@ai-rules:
  - Never include SecretKey.ciphertext or a decrypted value in any response except reveal_value's.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 3.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import environments as environments_service
from nebula import projects as projects_service
from nebula import secrets as secrets_service
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.secret import (
    SecretBulkCreateRequest,
    SecretKeyCreateRequest,
    SecretKeyResponse,
    SecretKeyUpdateRequest,
    SecretRevealResponse,
    SecretValueSetRequest,
)
from nebula.models.tables import SecretKey, UserAccount, VariableType
from nebula.projects import ProjectNotFoundError
from nebula.secrets import (
    BulkCreateConflictError,
    BulkDuplicateKeyNamesError,
    DuplicateSecretKeyNameError,
    SecretKeyNotFoundError,
    SecretValueNotFoundError,
)


async def _to_response(session: AsyncSession, key: SecretKey) -> SecretKeyResponse:
    environment = await environments_service.get_environment(session, key.environment_id)
    # An "environment" variable is deliberately not anonymized — its value goes straight into the
    # list response; a "secret" always stays null here, plaintext only via the reveal endpoint.
    value = None
    if key.variable_type == VariableType.ENVIRONMENT and key.ciphertext is not None:
        value = await secrets_service.reveal_value(session, key)
    return SecretKeyResponse(
        id=key.id,
        project_id=key.project_id,
        name=key.name,
        description=key.description,
        environment_id=key.environment_id,
        environment_name=environment.name,
        variable_type=key.variable_type,
        is_set=key.ciphertext is not None,
        value=value,
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
            "/{project_id}/bulk",
            self.bulk_create_keys,
            methods=["POST"],
            response_model=list[SecretKeyResponse],
            status_code=201,
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
        request: Request,
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
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.create", object_type="secret_key", object_id=row.id,
            object_label=row.name, project_id=project_id,
        )
        return await _to_response(session, row)

    async def bulk_create_keys(
        self,
        project_id: uuid.UUID,
        payload: SecretBulkCreateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[SecretKeyResponse]:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        await self._environment_or_404(session, payload.environment_id)
        if not payload.items:
            raise HTTPException(status_code=400, detail="No variables to add")
        try:
            rows = await secrets_service.create_keys_bulk(
                session,
                project_id,
                environment_id=payload.environment_id,
                items=[(item.name, item.value, item.variable_type) for item in payload.items],
                created_by=actor.id,
            )
        except BulkDuplicateKeyNamesError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "These key names already exist or appear more than once in the upload: "
                    + ", ".join(exc.names)
                ),
            )
        except BulkCreateConflictError:
            raise HTTPException(status_code=409, detail="A key name conflicted while saving — please retry")
        for row in rows:
            await audit_service.record_user_action(
                session, actor, request,
                action="secret.create", object_type="secret_key", object_id=row.id,
                object_label=row.name, project_id=project_id, detail="Bulk .env upload",
            )
        return [await _to_response(session, row) for row in rows]

    async def update_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretKeyUpdateRequest,
        request: Request,
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
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.update", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        return await _to_response(session, key)

    async def delete_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        key_id_copy, key_name = key.id, key.name
        await secrets_service.delete_key(session, key)
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.delete", object_type="secret_key", object_id=key_id_copy,
            object_label=key_name, project_id=project_id,
        )

    async def set_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretValueSetRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        key = await secrets_service.set_value(session, key, plaintext=payload.value, updated_by=actor.id)
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.value_set", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        return await _to_response(session, key)

    async def reveal_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretRevealResponse:
        project, _share = await self._project_or_404(session, actor, project_id)
        key = await self._key_or_404(session, project_id, key_id)
        # An "environment" variable is already visible to anyone who can view the Project (its
        # value ships straight in the list response) — only a "secret" needs the stricter
        # owner/admin-only can_reveal gate.
        if key.variable_type == VariableType.SECRET and not projects_service.can_reveal(actor, project):
            raise HTTPException(status_code=403, detail="Only the project owner or an admin may reveal values")
        environment = await environments_service.get_environment(session, key.environment_id)
        try:
            value = await secrets_service.reveal_value(session, key)
        except SecretValueNotFoundError:
            raise HTTPException(status_code=404, detail="No value set for this key")
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.reveal", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        return SecretRevealResponse(key=key.name, environment=environment.name, value=value)


router = SecretRouter()
