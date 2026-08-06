#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Read-only audit log endpoints — admin only.
@ai-context: Backs the frontend's admin-only Audit Logs page (three tabs: Activity, API calls,
  Failed retrievals — see nebula.audit for what partitions each). Every route requires
  actor.is_admin; a non-admin (even a Project owner) gets 403 — the audit trail is intentionally not
  scoped per-project or per-user, so nothing short of full admin should see it.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
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
    def _require_admin(actor: UserAccount) -> None:
        if not actor.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")

    async def activity(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        self._require_admin(actor)
        rows = await audit_service.list_activity(session)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]

    async def api_calls(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        self._require_admin(actor)
        rows = await audit_service.list_api_calls(session)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]

    async def failed_retrievals(
        self,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[AuditLogEntryResponse]:
        self._require_admin(actor)
        rows = await audit_service.list_failed_retrievals(session)
        return [AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows]


router = AuditRouter()
