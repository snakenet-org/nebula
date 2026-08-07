#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Dashboard summary — system-wide counts + the daily API-requests/extraction/failure time
  series.
@ai-context: Counts are system-wide (not scoped to the caller's visible Projects) — "how many
  environments/projects/variables/secrets exist" reads as a literal system total, and the daily
  series are inherently cross-project analytics anyway (nebula.audit.daily_counts already has no
  per-project scoping). "Variables" vs. "Secrets" split on SecretKey.variable_type
  (nebula.models.tables.VariableType) — the two categories introduced alongside GitHub sync (see
  the 2026-08-06 CLAUDE.md entry). Every authenticated user sees the same Dashboard — it is
  deliberately NOT admin-gated, unlike the Audit Logs page proper, even though the request/failure
  charts are built from the same audit_log_entries table; only per-row detail (who, when, from where)
  is admin-only, not the aggregate daily counts.
  `api_requests`/`failed_attempts` (renamed from `api_extractions`/`failed_retrievals` 2026-08-07)
  now count EVERY call to ANY api/v1/vault.py route (nebula.audit.VAULT_ACTIONS — /secret, /project,
  /status), not just /secret — `api_requests` is every call regardless of outcome (success=None),
  `failed_attempts` is the success=False subset (any non-200 response), matching what
  list_failed_retrievals() lists row-by-row on the Audit Logs page.
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-07
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.audit import VAULT_ACTIONS, daily_counts
from nebula.models.tables import ActorType, Environment, Project, SecretKey, VariableType


async def summary_counts(session: AsyncSession) -> dict[str, int]:
    environment_count = (
        await session.execute(select(func.count()).select_from(Environment))
    ).scalar_one()
    project_count = (await session.execute(select(func.count()).select_from(Project))).scalar_one()
    variable_count = (
        await session.execute(
            select(func.count())
            .select_from(SecretKey)
            .where(SecretKey.variable_type == VariableType.ENVIRONMENT)
        )
    ).scalar_one()
    secret_count = (
        await session.execute(
            select(func.count())
            .select_from(SecretKey)
            .where(SecretKey.variable_type == VariableType.SECRET)
        )
    ).scalar_one()
    return {
        "environment_count": environment_count,
        "project_count": project_count,
        "variable_count": variable_count,
        "secret_count": secret_count,
    }


async def extraction_series(session: AsyncSession, *, days: int = 14) -> dict[str, dict]:
    """Three daily time series, each {date: count} — the Dashboard's line charts."""
    api_requests = await daily_counts(
        session, action=VAULT_ACTIONS, actor_type=ActorType.ACCESS_KEY, success=None, days=days
    )
    frontend_extractions = await daily_counts(
        session, action="secret.reveal", actor_type=ActorType.USER, success=None, days=days
    )
    failed_attempts = await daily_counts(
        session, action=VAULT_ACTIONS, actor_type=ActorType.ACCESS_KEY, success=False, days=days
    )
    return {
        "api_requests": api_requests,
        "frontend_extractions": frontend_extractions,
        "failed_attempts": failed_attempts,
    }
