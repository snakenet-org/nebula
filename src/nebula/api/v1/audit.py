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
  2026-08-12 (later same day): all three routes now take `search` (free-text, OR'd across
  actor_label/action/object_label/project_label — see nebula.audit._search_condition) and
  `page`/`page_size` (page_size hard-capped at nebula.audit.MAX_PAGE_SIZE=300 via Query(le=...), the
  first line of defense before nebula.audit's own re-clamp) and return AuditLogPageResponse
  (`items`+`total`+`page`+`page_size`) instead of a bare list, so the frontend can render Prev/Next
  controls without ever pulling the whole log.
@version: 3.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import projects as projects_service
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.audit import AuditLogEntryResponse, AuditLogPageResponse
from nebula.models.tables import UserAccount

_SearchParam = Query(None, max_length=200)
_PageParam = Query(1, ge=1)
_PageSizeParam = Query(audit_service.MAX_PAGE_SIZE, ge=1, le=audit_service.MAX_PAGE_SIZE)


class AuditRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/activity", self.activity, methods=["GET"], response_model=AuditLogPageResponse
        )
        self.add_api_route(
            "/api-calls", self.api_calls, methods=["GET"], response_model=AuditLogPageResponse
        )
        self.add_api_route(
            "/failed-retrievals",
            self.failed_retrievals,
            methods=["GET"],
            response_model=AuditLogPageResponse,
        )

    @staticmethod
    async def _scope(session: AsyncSession, actor: UserAccount) -> list[uuid.UUID] | None:
        """None (unscoped) for an admin; the caller's owned+editor Project ids otherwise."""
        if actor.is_admin:
            return None
        return await projects_service.list_editable_project_ids(session, actor)

    @staticmethod
    def _page_response(
        rows_and_total: tuple[list, int], *, page: int, page_size: int
    ) -> AuditLogPageResponse:
        rows, total = rows_and_total
        return AuditLogPageResponse(
            items=[AuditLogEntryResponse.model_validate(row, from_attributes=True) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def activity(
        self,
        search: str | None = _SearchParam,
        page: int = _PageParam,
        page_size: int = _PageSizeParam,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> AuditLogPageResponse:
        project_ids = await self._scope(session, actor)
        result = await audit_service.list_activity(
            session, search=search, page=page, page_size=page_size, project_ids=project_ids
        )
        return self._page_response(result, page=page, page_size=page_size)

    async def api_calls(
        self,
        search: str | None = _SearchParam,
        page: int = _PageParam,
        page_size: int = _PageSizeParam,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> AuditLogPageResponse:
        project_ids = await self._scope(session, actor)
        result = await audit_service.list_api_calls(
            session, search=search, page=page, page_size=page_size, project_ids=project_ids
        )
        return self._page_response(result, page=page, page_size=page_size)

    async def failed_retrievals(
        self,
        search: str | None = _SearchParam,
        page: int = _PageParam,
        page_size: int = _PageSizeParam,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> AuditLogPageResponse:
        project_ids = await self._scope(session, actor)
        result = await audit_service.list_failed_retrievals(
            session, search=search, page=page, page_size=page_size, project_ids=project_ids
        )
        return self._page_response(result, page=page, page_size=page_size)


router = AuditRouter()
