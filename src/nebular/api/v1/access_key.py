#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: ProjectAccessKey CRUD — thin wrapper over nebular.access_keys.
@ai-context: Owner+admin only (can_manage_access_keys) for every route — an access key is a
  standing credential that can read every secret in the Project (see api/v1/vault.py), so managing
  it sits at the same trust tier as sharing/reveal/delete, not can_edit. AccessKeyCreateResponse.
  token is present ONLY on the create response — list/get never return it again.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import access_keys as access_keys_service
from nebular import projects as projects_service
from nebular.access_keys import AccessKeyNotFoundError
from nebular.api.endpoint import Endpoint, get_current_user
from nebular.database import get_session
from nebular.models.access_key import AccessKeyCreateRequest, AccessKeyCreateResponse, AccessKeyResponse
from nebular.models.tables import UserAccount
from nebular.projects import ProjectNotFoundError


class AccessKeyRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/{project_id}", self.list_keys, methods=["GET"], response_model=list[AccessKeyResponse]
        )
        self.add_api_route(
            "/{project_id}",
            self.create_key,
            methods=["POST"],
            response_model=AccessKeyCreateResponse,
            status_code=201,
        )
        self.add_api_route(
            "/{project_id}/{access_key_id}", self.revoke_key, methods=["DELETE"], status_code=204
        )

    async def _project_or_404(self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID):
        try:
            return await projects_service.get_visible_project(session, actor, project_id)
        except ProjectNotFoundError:
            raise HTTPException(status_code=404, detail="Project not found")

    async def list_keys(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AccessKeyResponse]:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_manage_access_keys(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's access keys")
        rows = await access_keys_service.list_access_keys(session, project_id)
        return [AccessKeyResponse.model_validate(row, from_attributes=True) for row in rows]

    async def create_key(
        self,
        project_id: uuid.UUID,
        payload: AccessKeyCreateRequest,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> AccessKeyCreateResponse:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_manage_access_keys(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's access keys")
        row, token = await access_keys_service.generate_access_key(
            session, project_id, name=payload.name, created_by=actor.id
        )
        return AccessKeyCreateResponse(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            token_prefix=row.token_prefix,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            revoked=row.revoked,
            token=token,
        )

    async def revoke_key(
        self,
        project_id: uuid.UUID,
        access_key_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_manage_access_keys(actor, project):
            raise HTTPException(status_code=403, detail="You cannot manage this project's access keys")
        try:
            row = await access_keys_service.get_access_key(session, project_id, access_key_id)
        except AccessKeyNotFoundError:
            raise HTTPException(status_code=404, detail="Access key not found")
        await access_keys_service.revoke_access_key(session, row)


router = AccessKeyRouter()
