#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Append-only audit log — every mutating action taken through Nebula, by a human or a
  Project access key.
@ai-context: record() is called from the ROUTER layer (api/v1/*.py), right after a mutation
  succeeds (or, for vault.py's external calls, after either outcome) — never from the thin
  service modules (nebula.projects/environments/secrets/access_keys), since only the router has
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
      with success=False here are failed attempts (any non-200 vault.py response, not just a
      lookup miss) — list_failed_retrievals() backs both the Audit Logs page's own "Failed
      retrievals" tab and the Dashboard's "Failed attempts / day" chart (see nebula.dashboard).
  VAULT_ACTIONS enumerates every api/v1/vault.py route's action string ("vault.retrieve" /secret,
  "vault.project" /project, "vault.status" /status) — every one of the three is now audit-logged on
  every call (added 2026-08-07; /status previously logged nothing at all), and list_api_calls/
  list_failed_retrievals/the Dashboard's api_requests+failed_attempts series all aggregate across
  the whole set rather than /secret alone, since "any call to any vault route" is the unit both the
  Audit Logs page and the Dashboard now count.
  EXTRACTION_ACTIONS (2026-08-09) is the narrower "this SecretKey's value actually left the vault"
  pair — "secret.reveal" (a human, api/v1/secret.py's reveal_value) and "vault.retrieve" (a Project
  access key, api/v1/vault.py's get_secret) — backing extraction_counts_by_project/
  extraction_count_for_key, the per-key "how many times has this been extracted" used by
  ProjectView.vue's key-row info/warning icon. Only success=True rows count — a failed reveal/
  retrieve (no value set, wrong environment, ...) never actually extracted anything. vault.py's
  get_secret now sets object_id=secret_key.id on every audit row where the key resolved (previously
  only object_label, a display string), same as secret.py's reveal_value already did — required for
  either action to be attributable to a specific key by id rather than by fragile name matching
  that would break silently across a rename.
@ai-rules:
  - Never put a plaintext secret value in `detail` or any other column.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-09
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.models.tables import ActorType, AuditLogEntry, UserAccount

# Every api/v1/vault.py route's action string — see the module docstring above.
VAULT_ACTIONS: tuple[str, ...] = ("vault.retrieve", "vault.project", "vault.status")

# The two actions that mean "a SecretKey's value actually left the vault" — see the module docstring.
EXTRACTION_ACTIONS: tuple[str, ...] = ("secret.reveal", "vault.retrieve")


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
    object_id: uuid.UUID | None = None,
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
        object_id=object_id,
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
    """Failed calls to any api/v1/vault.py route, newest first — the "Failed retrievals" tab."""
    result = await session.execute(
        select(AuditLogEntry)
        .where(AuditLogEntry.action.in_(VAULT_ACTIONS), AuditLogEntry.success.is_(False))
        .order_by(AuditLogEntry.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def daily_counts(
    session: AsyncSession,
    *,
    action: str | Sequence[str],
    actor_type: ActorType,
    success: bool | None,
    days: int,
) -> dict[date, int]:
    """Per-day counts of `action` (one action, or any of several) over the trailing `days` — backs
    nebula.dashboard's charts.

    Returns every day in the window (zero-filled), not just days with activity, so a chart never has
    to reconstruct missing dates itself.
    """
    since = datetime.utcnow() - timedelta(days=days - 1)
    day_expr = func.date_trunc("day", AuditLogEntry.occurred_at)
    action_condition = (
        AuditLogEntry.action.in_(action)
        if isinstance(action, (list, tuple, set))
        else AuditLogEntry.action == action
    )
    conditions = [
        action_condition,
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


async def extraction_counts_by_project(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Per-key successful-extraction counts for every SecretKey in `project_id`, one query — backs
    the Project view's per-key info/warning icon. A key with zero extractions is simply absent from
    the returned dict (callers should `.get(key_id, 0)`)."""
    result = await session.execute(
        select(AuditLogEntry.object_id, func.count())
        .where(
            AuditLogEntry.project_id == project_id,
            AuditLogEntry.object_type == "secret_key",
            AuditLogEntry.action.in_(EXTRACTION_ACTIONS),
            AuditLogEntry.success.is_(True),
        )
        .group_by(AuditLogEntry.object_id)
    )
    return {row[0]: row[1] for row in result.all() if row[0] is not None}


async def extraction_count_for_key(session: AsyncSession, key_id: uuid.UUID) -> int:
    """Successful-extraction count for a single key — see extraction_counts_by_project, used instead
    when only one key's response is being built (create/update/set_value), not a whole list."""
    result = await session.execute(
        select(func.count()).where(
            AuditLogEntry.object_id == key_id,
            AuditLogEntry.object_type == "secret_key",
            AuditLogEntry.action.in_(EXTRACTION_ACTIONS),
            AuditLogEntry.success.is_(True),
        )
    )
    return result.scalar_one()
