#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Read-only audit log endpoints.
@ai-context: Backs the frontend's Audit Logs page (three tabs: Activity, API calls, Failed
  retrievals — see nebula.audit for what partitions each). GitHub #4: any authenticated user may now
  reach this page (previously admin-only) — an admin still sees every row app-wide
  (project_ids=None), while a non-admin is scoped to `nebula.projects.list_editable_project_ids`
  (Projects they own or are an EDITOR share on — a plain Viewer share does not grant audit-log
  visibility). Scoping is enforced HERE at the router layer, resolved once per route from the actor,
  and passed down to nebula.audit's query helpers — never trusted to the caller.
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import projects as projects_service
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.audit import AuditLogEntryResponse
from nebula.models.tables import UserAccount


class AuditRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/activity", self.activity, methods=["GET"], response_model=list[AuditLogEntryResponse]
        )
        self.add_api_route(
            "/api-calls", self.api_calls, methods=["GET"], response_model=list[AuditLogEntryResponse]
        )
        self.add_api_route(
            "/failed-retrievals",
            self.failed_retrievals,
            methods=["GET"],
            response_model=list[AuditLogEntryResponse],
        )

    @staticmethod
    async def _scope(session: AsyncSession, actor: UserAccount) -> list[uuid.UUID] | None:
        """None (unscoped) for an admin; the caller's owned+editor Project ids otherwise."""
        if actor.is_admin:
            return None
        return await projects_service.list_editable_project_ids(session, actor)

    async def activity(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        project_ids = await self._scope(session, actor)
        rows = await audit_service.list_activity(session, project_ids=project_ids)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]

    async def api_calls(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        project_ids = await self._scope(session, actor)
        rows = await audit_service.list_api_calls(session, project_ids=project_ids)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]

    async def failed_retrievals(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        project_ids = await self._scope(session, actor)
        rows = await audit_service.list_failed_retrievals(session, project_ids=project_ids)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]


router = AuditRouter()
