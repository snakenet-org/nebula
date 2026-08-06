#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Append-only audit log — every mutating action taken through Nebular, by a human or a
  Project access key.
@ai-context: record() is called from the ROUTER layer (api/v1/*.py), right after a mutation
  succeeds (or, for vault.py's external retrieval, after either outcome) — never from the thin
  service modules (nebular.projects/environments/secrets/access_keys), since only the router has
  both the resolved `actor` and the live `Request` (for ip_address). RULE FOR EVERY FUTURE FEATURE:
  any new mutating route must call record() too — this is not optional, per explicit product
  direction ("for all future features, always add an audit log").
  actor_label/object_label are captured as plain text AT WRITE TIME (never re-joined later) so the
  log stays readable after the underlying user/project/key is renamed or deleted — actor_id/
  object_id/project_id are kept as loose (non-FK, or SET NULL) references for optional filtering
  only, never required for the row to render.
  Two actor kinds partition the log into the two tabs the Audit Logs page shows:
    - ActorType.USER   — a logged-in human (local admin or OIDC) — list_activity().
    - ActorType.ACCESS_KEY — a Project access key hitting api/v1/vault.py — list_api_calls(). Rows
      with success=False here are failed retrieval attempts — list_failed_retrievals() backs both
      the Audit Logs page's own "Failed retrievals" tab and the Dashboard's failed-retrieval chart
      (see nebular.dashboard).
@ai-rules:
  - Never put a plaintext secret value in `detail` or any other column.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid
from datetime import date, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebular.models.tables import ActorType, AuditLogEntry, UserAccount


def _client_ip(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


async def record(
    session: AsyncSession,
    *,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    actor_label: str | None,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    success: bool = True,
    detail: str | None = None,
    ip_address: str | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=project_id,
        success=success,
        detail=detail,
        ip_address=ip_address,
    )
    session.add(entry)
    await session.commit()
    return entry


async def record_user_action(
    session: AsyncSession,
    actor: UserAccount,
    request: Request | None,
    *,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    success: bool = True,
    detail: str | None = None,
) -> AuditLogEntry:
    """Convenience wrapper for the common case — a logged-in human performed `action`."""
    return await record(
        session,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.username,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=project_id,
        success=success,
        detail=detail,
        ip_address=_client_ip(request),
    )


async def record_access_key_action(
    session: AsyncSession,
    *,
    access_key_id: uuid.UUID | None,
    access_key_label: str,
    request: Request | None,
    action: str,
    object_type: str | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    success: bool,
    detail: str | None = None,
) -> AuditLogEntry:
    """Convenience wrapper for the machine-caller case — a Project access key performed `action`."""
    return await record(
        session,
        actor_type=ActorType.ACCESS_KEY,
        actor_id=access_key_id,
        actor_label=access_key_label,
        action=action,
        object_type=object_type,
        object_label=object_label,
        project_id=project_id,
        success=success,
        detail=detail,
        ip_address=_client_ip(request),
    )


async def list_activity(session: AsyncSession, *, limit: int = 200) -> list[AuditLogEntry]:
    """Human (ActorType.USER) actions, newest first — the Audit Logs page's "Activity" tab."""
    result = await session.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.actor_type == ActorType.USER)
        .order_by(AuditLogEntry.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_api_calls(session: AsyncSession, *, limit: int = 200) -> list[AuditLogEntry]:
    """Access-key (ActorType.ACCESS_KEY) calls, newest first — the "API calls" tab."""
    result = await session.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.actor_type == ActorType.ACCESS_KEY)
        .order_by(AuditLogEntry.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_failed_retrievals(session: AsyncSession, *, limit: int = 200) -> list[AuditLogEntry]:
    """Failed api/v1/vault.py lookups, newest first — the "Failed retrievals" tab."""
    result = await session.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.action == "vault.retrieve", AuditLogEntry.success.is_(False))
        .order_by(AuditLogEntry.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def daily_counts(
    session: AsyncSession, *, action: str, actor_type: ActorType, success: bool | None, days: int
) -> dict[date, int]:
    """Per-day counts of `action` over the trailing `days` — backs nebular.dashboard's charts.

    Returns every day in the window (zero-filled), not just days with activity, so a chart never has
    to reconstruct missing dates itself.
    """
    since = datetime.utcnow() - timedelta(days=days - 1)
    day_expr = func.date_trunc("day", AuditLogEntry.occurred_at)
    conditions = [
        AuditLogEntry.action == action,
        AuditLogEntry.actor_type == actor_type,
        AuditLogEntry.occurred_at >= since,
    ]
    if success is not None:
        conditions.append(AuditLogEntry.success.is_(success))

    result = await session.execute(
        select(day_expr, func.count()).where(*conditions).group_by(day_expr)
    )
    counts = {row[0].date(): row[1] for row in result.all()}

    today = datetime.utcnow().date()
    return {
        today - timedelta(days=offset): counts.get(today - timedelta(days=offset), 0)
        for offset in range(days - 1, -1, -1)
    }
