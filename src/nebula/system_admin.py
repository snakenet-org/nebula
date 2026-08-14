#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: The two destructive System Settings danger zones — reset all data, reset logs.
@ai-context: Both issue bulk Core `DELETE` statements (not an ORM `session.delete()` per row) since
  a full-vault wipe can touch an unbounded number of rows — a Core DELETE lets Postgres's own
  ON DELETE CASCADE (Project → SecretKey/ProjectShare/ProjectAccessKey/ProjectGithubSync, see
  models/tables.py) do the cascading at the DB layer instead of loading every row into the ORM
  session first. reset_all_data deletes Projects before Environments — Environment.
  secret_keys' FK is ON DELETE RESTRICT, so it would otherwise refuse to delete an Environment still
  linked from a key; deleting every Project first (cascading away every SecretKey with it) clears
  that block. AuditLogEntry.project_id is ON DELETE SET NULL, so deleting Projects never removes an
  audit row by itself — reset_all_data's own explicit AuditLogEntry delete is what actually clears
  the log, same call reset_logs makes on its own.
  Neither function writes the audit-log row for ITS OWN action — that's the router's job
  (api/v1/system.py), called AFTER these return, so the one row recording "an admin reset the vault"
  is written fresh into the now-empty table rather than being wiped by the very reset it's reporting.
@ai-rules:
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-13
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.models.tables import AuditLogEntry, Environment, Project


async def _count(session: AsyncSession, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def reset_all_data(session: AsyncSession) -> dict[str, int]:
    """Delete every Project (cascading its SecretKeys/shares/access keys/GitHub sync targets),
    every Environment, and every AuditLogEntry. Returns pre-delete counts for the caller's audit
    detail/response. UserAccount rows are never touched — this resets VAULT data, not who can log in.
    """
    projects = await _count(session, Project)
    environments = await _count(session, Environment)
    audit_logs = await _count(session, AuditLogEntry)

    await session.execute(delete(Project))
    await session.execute(delete(Environment))
    await session.execute(delete(AuditLogEntry))
    await session.commit()

    return {
        "projects_deleted": projects,
        "environments_deleted": environments,
        "audit_logs_deleted": audit_logs,
    }


async def reset_logs(session: AsyncSession) -> int:
    """Delete every AuditLogEntry. Returns the pre-delete row count."""
    audit_logs = await _count(session, AuditLogEntry)
    await session.execute(delete(AuditLogEntry))
    await session.commit()
    return audit_logs
