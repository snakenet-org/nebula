#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: System Settings — the four admin-only danger zones (reset all data, reset logs, export
  vault, import vault). Backs the frontend's SystemSettingsView.vue.
@ai-context: Every route here is admin-only (`if not actor.is_admin: raise HTTPException(403, ...)`,
  same pattern as api/v1/environment.py's delete_environment) on top of the router's own standard
  X-Nebula-Token + JWT gates (Endpoint's default, not `public=True`) — there is no separate
  "admin-only router" flag, so each handler checks itself. Every route is audit-logged AFTER its
  underlying action succeeds, same "router layer only, right after a mutation succeeds" rule as every
  other route in this codebase (nebula.audit's module docstring) — reset-data/reset-logs log
  specifically AFTER the wipe (nebula.system_admin returns pre-delete counts) so the one row
  recording the reset survives being written into the now-empty table, not before it.
  export doesn't mutate anything, but is still audit-logged (project/key counts only — never the
  export body itself, which may carry decrypted secret values, per this file's own "never put a
  plaintext value in `detail`" rule) since downloading a full-vault plaintext export is itself a
  security-relevant event worth a trail.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-13
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import system_admin
from nebula import vault_transfer
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.system import SystemResetSummary, VaultExport, VaultImportSummary
from nebula.models.tables import UserAccount


class SystemRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/reset-data", self.reset_data, methods=["POST"], response_model=SystemResetSummary
        )
        self.add_api_route(
            "/reset-logs", self.reset_logs, methods=["POST"], response_model=SystemResetSummary
        )
        self.add_api_route("/export", self.export_vault, methods=["GET"], response_model=VaultExport)
        self.add_api_route(
            "/import", self.import_vault, methods=["POST"], response_model=VaultImportSummary
        )

    @staticmethod
    def _require_admin(actor: UserAccount) -> None:
        if not actor.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")

    async def reset_data(
        self,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SystemResetSummary:
        self._require_admin(actor)
        counts = await system_admin.reset_all_data(session)
        await audit_service.record_user_action(
            session, actor, request,
            action="system.reset_data", object_type="system",
            detail=(
                f"projects={counts['projects_deleted']} "
                f"environments={counts['environments_deleted']} "
                f"audit_logs={counts['audit_logs_deleted']}"
            ),
        )
        return SystemResetSummary(**counts)

    async def reset_logs(
        self,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SystemResetSummary:
        self._require_admin(actor)
        audit_logs_deleted = await system_admin.reset_logs(session)
        await audit_service.record_user_action(
            session, actor, request,
            action="system.reset_logs", object_type="system",
            detail=f"audit_logs={audit_logs_deleted}",
        )
        return SystemResetSummary(audit_logs_deleted=audit_logs_deleted)

    async def export_vault(
        self,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> VaultExport:
        self._require_admin(actor)
        export = await vault_transfer.export_vault(session)
        await audit_service.record_user_action(
            session, actor, request,
            action="system.export_vault", object_type="system",
            detail=f"projects={len(export.projects)} environments={len(export.environments)}",
        )
        return export

    async def import_vault(
        self,
        payload: VaultExport,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> VaultImportSummary:
        self._require_admin(actor)
        summary = await vault_transfer.import_vault(session, actor, payload)
        await audit_service.record_user_action(
            session, actor, request,
            action="system.import_vault", object_type="system",
            detail=(
                f"projects={summary.projects_created} keys={summary.keys_created} "
                f"environments_created={summary.environments_created} "
                f"environments_reused={summary.environments_reused} "
                f"references_resolved={summary.references_resolved} "
                f"references_skipped={summary.references_skipped}"
            ),
        )
        return summary


router = SystemRouter()
