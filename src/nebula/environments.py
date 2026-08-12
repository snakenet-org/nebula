#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Environment CRUD — GLOBAL, not scoped to any Project (see the 2026-08-06 redesign).
@ai-context: An Environment is a shared taxonomy (e.g. "production", "staging") any Project's
  SecretKeys can link into — exactly one Environment per key (nebula.secrets), reassignable but
  never unset. Permission checks (create/update = any authenticated user, delete = admin only) live
  at the router layer (api/v1/environment.py), mirroring how nebula.topics-shaped modules stay thin
  behind their own gate. DuplicateEnvironmentNameError surfaces the case-insensitive unique
  constraint (uq_environments_name_lower) as a clean 409; EnvironmentInUseError surfaces the
  RESTRICT foreign key (secret_keys.environment_id) as a clean 409 instead of a raw IntegrityError
  when deleting an Environment still linked from at least one SecretKey.
  2026-08-12 (GitHub #6): EnvironmentInUseError now carries `project_names` (the distinct, sorted
  names of every Project that still has a key linked to the Environment being deleted, resolved by
  list_projects_using — a plain join of secret_keys → projects filtered to this environment_id) so
  api/v1/environment.py can surface a clean, specific 409 detail ("still used by: X, Y") instead of
  the previous generic "still linked from at least one key" message — delete_environment still
  refuses via the exact same RESTRICT-backed count_keys_using check as before, this only makes the
  error message name names. Only after every referencing key (across every Project) is deleted or
  reassigned does count_keys_using return 0 and the delete proceed.
@ai-rules:
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 2.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.models.tables import Environment, Project, SecretKey


class DuplicateEnvironmentNameError(Exception):
    """Raised on a case-insensitive Environment name collision."""


class EnvironmentNotFoundError(Exception):
    """Raised when an Environment id doesn't exist."""


class EnvironmentInUseError(Exception):
    """Raised when deleting an Environment that at least one SecretKey still links to.

    `project_names` (distinct, sorted) names every Project that still has a key linked to this
    Environment — see list_projects_using — so a caller can build a specific, actionable error
    message instead of a generic "still in use".
    """

    def __init__(self, environment_id: str, *, project_names: list[str]) -> None:
        super().__init__(environment_id)
        self.project_names = project_names


async def list_environments(session: AsyncSession) -> list[Environment]:
    result = await session.execute(select(Environment).order_by(Environment.name))
    return list(result.scalars().all())


async def get_environment(session: AsyncSession, environment_id: uuid.UUID) -> Environment:
    environment = await session.get(Environment, environment_id)
    if environment is None:
        raise EnvironmentNotFoundError(str(environment_id))
    return environment


async def get_environment_by_name(session: AsyncSession, name: str) -> Environment | None:
    """Case-insensitive lookup — backs api/v1/vault.py's external, name-addressed retrieval."""
    result = await session.execute(select(Environment).where(Environment.name.ilike(name)))
    return result.scalar_one_or_none()


async def count_keys_using(session: AsyncSession, environment_id: uuid.UUID) -> int:
    """How many SecretKeys (across every Project) currently link to this Environment."""
    return (
        await session.execute(
            select(func.count())
            .select_from(SecretKey)
            .where(SecretKey.environment_id == environment_id)
        )
    ).scalar_one()


async def list_projects_using(session: AsyncSession, environment_id: uuid.UUID) -> list[str]:
    """Distinct, sorted names of every Project that currently has at least one SecretKey linked to
    this Environment — backs EnvironmentInUseError's project_names, so a blocked delete can name
    exactly which Project(s) still need to stop using it first."""
    result = await session.execute(
        select(Project.name)
        .distinct()
        .join(SecretKey, SecretKey.project_id == Project.id)
        .where(SecretKey.environment_id == environment_id)
        .order_by(Project.name)
    )
    return list(result.scalars().all())


async def create_environment(
    session: AsyncSession, *, name: str, description: str | None
) -> Environment:
    environment = Environment(name=name, description=description)
    session.add(environment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEnvironmentNameError(name) from exc
    await session.refresh(environment)
    return environment


async def update_environment(
    session: AsyncSession,
    environment: Environment,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Environment:
    if name is not None:
        environment.name = name
    if description is not None:
        environment.description = description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEnvironmentNameError(name or environment.name) from exc
    await session.refresh(environment)
    return environment


async def delete_environment(session: AsyncSession, environment: Environment) -> None:
    if await count_keys_using(session, environment.id):
        project_names = await list_projects_using(session, environment.id)
        raise EnvironmentInUseError(str(environment.id), project_names=project_names)
    await session.delete(environment)
    await session.commit()
