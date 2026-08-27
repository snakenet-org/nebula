#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Dashboard summary — counts + the daily API-requests/extraction/failure time series.
@ai-context: An admin sees system-wide counts/series (`project_ids=None` throughout). A non-admin is
  scoped to only the Projects they own or are an EDITOR share on
  (nebula.projects.list_editable_project_ids, resolved by api/v1/dashboard.py) — GitHub #4:
  "the dashboard charts and summary should reflect only data from projects that the user owns or is
  an editor of." `project_count`/`variable_count`/`secret_count` are counted directly against that
  scope. `environment_count` needs special handling since Environment is a GLOBAL taxonomy, not owned
  by any Project (see nebula.environments) — for a scoped caller it's redefined as "how many distinct
  Environments are actually in use by a key in one of my Projects" (DISTINCT SecretKey.environment_id
  within the scope) rather than the system-wide Environment row count, so the stat still means
  something meaningful to that caller instead of leaking the total across every Project in the vault.
  "Variables" vs. "Secrets" split on SecretKey.variable_type (nebula.models.tables.VariableType) —
  the two categories introduced alongside GitHub sync (see the 2026-08-06 CLAUDE.md entry). Every
  authenticated user sees the Dashboard (unlike the Audit Logs page, which is reachable from the
  sidebar for anyone but still per-row detail is what's being scoped, not gated behind a role check).
  `api_requests`/`failed_attempts` (renamed from `api_extractions`/`failed_retrievals` 2026-08-07)
  count EVERY call to ANY api/v1/vault.py route (nebula.audit.VAULT_ACTIONS — /secret, /project,
  /status), not just /secret — `api_requests` is every call regardless of outcome (success=None),
  `failed_attempts` is the success=False subset (any non-200 response), matching what
  list_failed_retrievals() lists row-by-row on the Audit Logs page.
  2026-08-27: added `certificate_count` (VariableType.CERTIFICATE, nebula.models.tables) alongside
  variable_count/secret_count — same scope rules, so the three now partition every SecretKey in
  scope instead of silently omitting certificates from the Dashboard.
@version: 3.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-27
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.audit import VAULT_ACTIONS, daily_counts
from nebula.models.tables import (
    ActorType,
    Environment,
    Project,
    SecretKey,
    VariableType,
)


async def summary_counts(
    session: AsyncSession, *, project_ids: Sequence[uuid.UUID] | None = None
) -> dict[str, int]:
    """`project_ids=None` (admin) counts system-wide. A scoped sequence (a non-admin's owned+editor
    Projects) restricts project/variable/secret counts to those Projects, and environment_count to
    the distinct Environments a key of theirs actually links to — see the module docstring."""
    if project_ids is None:
        environment_count = (
            await session.execute(select(func.count()).select_from(Environment))
        ).scalar_one()
        project_count = (
            await session.execute(select(func.count()).select_from(Project))
        ).scalar_one()
        variable_scope = [SecretKey.variable_type == VariableType.ENVIRONMENT]
        secret_scope = [SecretKey.variable_type == VariableType.SECRET]
        certificate_scope = [SecretKey.variable_type == VariableType.CERTIFICATE]
    else:
        environment_count = (
            await session.execute(
                select(func.count(func.distinct(SecretKey.environment_id))).where(
                    SecretKey.project_id.in_(project_ids)
                )
            )
        ).scalar_one()
        project_count = len(project_ids)
        variable_scope = [
            SecretKey.variable_type == VariableType.ENVIRONMENT,
            SecretKey.project_id.in_(project_ids),
        ]
        secret_scope = [
            SecretKey.variable_type == VariableType.SECRET,
            SecretKey.project_id.in_(project_ids),
        ]
        certificate_scope = [
            SecretKey.variable_type == VariableType.CERTIFICATE,
            SecretKey.project_id.in_(project_ids),
        ]

    variable_count = (
        await session.execute(select(func.count()).select_from(SecretKey).where(*variable_scope))
    ).scalar_one()
    secret_count = (
        await session.execute(select(func.count()).select_from(SecretKey).where(*secret_scope))
    ).scalar_one()
    certificate_count = (
        await session.execute(select(func.count()).select_from(SecretKey).where(*certificate_scope))
    ).scalar_one()
    return {
        "environment_count": environment_count,
        "project_count": project_count,
        "variable_count": variable_count,
        "secret_count": secret_count,
        "certificate_count": certificate_count,
    }


async def extraction_series(
    session: AsyncSession, *, days: int = 14, project_ids: Sequence[uuid.UUID] | None = None
) -> dict[str, dict]:
    """Three daily time series, each {date: count} — the Dashboard's line charts. See
    summary_counts/the module docstring for what `project_ids` means."""
    api_requests = await daily_counts(
        session,
        action=VAULT_ACTIONS,
        actor_type=ActorType.ACCESS_KEY,
        success=None,
        days=days,
        project_ids=project_ids,
    )
    frontend_extractions = await daily_counts(
        session,
        action="secret.reveal",
        actor_type=ActorType.USER,
        success=None,
        days=days,
        project_ids=project_ids,
    )
    failed_attempts = await daily_counts(
        session,
        action=VAULT_ACTIONS,
        actor_type=ActorType.ACCESS_KEY,
        success=False,
        days=days,
        project_ids=project_ids,
    )
    return {
        "api_requests": api_requests,
        "frontend_extractions": frontend_extractions,
        "failed_attempts": failed_attempts,
    }
