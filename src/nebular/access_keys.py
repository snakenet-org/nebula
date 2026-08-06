#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: ProjectAccessKey generate/revoke/list — the REST API credential api/v1/vault.py accepts.
@ai-context: Same "opaque high-entropy token, hash not encrypt" reasoning as Singularity's
  generate_m2m_token/hash_m2m_token: a `nbv_`-prefixed token already has 256 bits of entropy
  (secrets.token_urlsafe(32)), so a fast deterministic SHA-256 digest is the correct storage — it
  lets ProjectAccessKey.token_hash be looked up directly with an indexed equality query instead of
  bcrypt-comparing against every stored hash. generate_access_key returns the raw token exactly
  once (the caller must copy it immediately — it's never retrievable again, only token_prefix is
  kept for UI identification). resolve_access_key is what api/v1/vault.py's get_access_key
  dependency calls: hash the presented bearer token, look up a non-revoked row, bump
  last_used_at, return (project, access_key) or None.
@ai-rules:
  - Never log or return a full token after creation.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import hashlib
import secrets as stdlib_secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebular.models.tables import Project, ProjectAccessKey

# Prefix marking a bearer credential as a project access key (mirrors Singularity's `sgm_` M2M
# prefix) — lets a caller be told apart from a human JWT at a glance if ever needed.
ACCESS_KEY_PREFIX = "nbv_"


class AccessKeyNotFoundError(Exception):
    """Raised when an access key id doesn't exist (or belongs to a different Project)."""


def _generate_token() -> str:
    return f"{ACCESS_KEY_PREFIX}{stdlib_secrets.token_urlsafe(32)}"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def list_access_keys(session: AsyncSession, project_id: uuid.UUID) -> list[ProjectAccessKey]:
    result = await session.execute(
        select(ProjectAccessKey)
        .where(ProjectAccessKey.project_id == project_id)
        .order_by(ProjectAccessKey.created_at.desc())
    )
    return list(result.scalars().all())


async def get_access_key(
    session: AsyncSession, project_id: uuid.UUID, access_key_id: uuid.UUID
) -> ProjectAccessKey:
    key = await session.get(ProjectAccessKey, access_key_id)
    if key is None or key.project_id != project_id:
        raise AccessKeyNotFoundError(str(access_key_id))
    return key


async def generate_access_key(
    session: AsyncSession, project_id: uuid.UUID, *, name: str, created_by: uuid.UUID
) -> tuple[ProjectAccessKey, str]:
    """Create a new access key, returning (row, raw_token) — the raw token is shown exactly once."""
    token = _generate_token()
    key = ProjectAccessKey(
        project_id=project_id,
        name=name,
        token_hash=_hash_token(token),
        token_prefix=token[: len(ACCESS_KEY_PREFIX) + 8],
        created_by=created_by,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return key, token


async def revoke_access_key(session: AsyncSession, key: ProjectAccessKey) -> None:
    key.revoked = True
    await session.commit()


async def resolve_access_key(
    session: AsyncSession, token: str
) -> tuple[Project, ProjectAccessKey] | None:
    """Validate a presented bearer token and return its (Project, ProjectAccessKey), or None.

    Bumps last_used_at on every successful resolution. Returns None (never raises) for an unknown,
    malformed, or revoked token — the caller (api/v1/vault.py) turns that into a 401.
    """
    if not token.startswith(ACCESS_KEY_PREFIX):
        return None

    result = await session.execute(
        select(ProjectAccessKey).where(ProjectAccessKey.token_hash == _hash_token(token))
    )
    key = result.scalar_one_or_none()
    if key is None or key.revoked:
        return None

    project = await session.get(Project, key.project_id)
    if project is None:
        return None

    key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()
    return project, key
