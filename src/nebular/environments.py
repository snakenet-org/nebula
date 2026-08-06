#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Environment CRUD, scoped to a single Project.
@ai-context: Thin — permission checks (can_edit) happen at the router layer using
  nebular.projects.can_edit before calling into here, matching how gravity.topics stays thin behind
  its own entitlement gate. DuplicateEnvironmentNameError surfaces the case-insensitive unique
  constraint (uq_environments_project_name_lower) as a clean 409 rather than a raw IntegrityError.
@ai-rules:
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nebular.models.tables import Environment


class DuplicateEnvironmentNameError(Exception):
    """Raised on a case-insensitive Environment name collision within a Project."""


class EnvironmentNotFoundError(Exception):
    """Raised when an Environment id doesn't exist (or belongs to a different Project)."""


async def list_environments(session: AsyncSession, project_id: uuid.UUID) -> list[Environment]:
    result = await session.execute(
        select(Environment).where(Environment.project_id == project_id).order_by(Environment.name)
    )
    return list(result.scalars().all())


async def get_environment(
    session: AsyncSession, project_id: uuid.UUID, environment_id: uuid.UUID
) -> Environment:
    environment = await session.get(Environment, environment_id)
    if environment is None or environment.project_id != project_id:
        raise EnvironmentNotFoundError(str(environment_id))
    return environment


async def get_environment_by_name(
    session: AsyncSession, project_id: uuid.UUID, name: str
) -> Environment | None:
    """Case-insensitive lookup — backs api/v1/vault.py's external, name-addressed retrieval."""
    result = await session.execute(
        select(Environment).where(Environment.project_id == project_id, Environment.name.ilike(name))
    )
    return result.scalar_one_or_none()


async def create_environment(
    session: AsyncSession, project_id: uuid.UUID, *, name: str
) -> Environment:
    environment = Environment(project_id=project_id, name=name)
    session.add(environment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEnvironmentNameError(name) from exc
    await session.refresh(environment)
    return environment


async def delete_environment(session: AsyncSession, environment: Environment) -> None:
    await session.delete(environment)
    await session.commit()
