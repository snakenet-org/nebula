#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey/SecretValue CRUD — the encrypted key-value store itself.
@ai-context: The one module (besides nebular.crypto) that ever touches plaintext secret values.
  list_keys_with_state returns PRESENCE ONLY (is_set booleans, see models.secret.SecretValueState) —
  it never decrypts anything, so it's safe to call for any caller who merely can_view the Project.
  set_value upserts the (secret_key_id, environment_id) row, encrypting via nebular.crypto.
  encrypt_value before it ever reaches the session — the plaintext argument is never persisted raw.
  apply_to_all_environments writes the same encrypted value to every Environment the Project
  currently has (the "ADMIN_EMAIL is the same everywhere" convenience from the spec) by looping
  set_value per environment — deliberately NOT a separate "global value" concept, so retrieval stays
  unambiguous (always exactly one ciphertext per key+environment, or none). reveal_value is the only
  function that calls nebular.crypto.decrypt_value — callers (api/v1/secret.py's reveal route,
  api/v1/vault.py's external retrieval route) must have already checked the caller may see plaintext
  (can_reveal for the human route, project-access-key possession for the machine route) before
  calling it; this module does not re-check that itself, since "may this actor see plaintext" is a
  Project-level question answered by nebular.projects, not a secret-value-level one.
@ai-rules:
  - Never log a plaintext value.
  - encrypt_value/decrypt_value only — never import `cryptography` directly here.
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

from nebular.crypto import decrypt_value, encrypt_value
from nebular.environments import list_environments
from nebular.models.tables import SecretKey, SecretValue


class DuplicateSecretKeyNameError(Exception):
    """Raised on a case-insensitive SecretKey name collision within a Project."""


class SecretKeyNotFoundError(Exception):
    """Raised when a SecretKey id doesn't exist (or belongs to a different Project)."""


class SecretValueNotFoundError(Exception):
    """Raised when reveal_value is asked for a (key, environment) pair with no value set."""


async def list_keys(session: AsyncSession, project_id: uuid.UUID) -> list[SecretKey]:
    result = await session.execute(
        select(SecretKey).where(SecretKey.project_id == project_id).order_by(SecretKey.name)
    )
    return list(result.scalars().all())


async def get_key(session: AsyncSession, project_id: uuid.UUID, key_id: uuid.UUID) -> SecretKey:
    key = await session.get(SecretKey, key_id)
    if key is None or key.project_id != project_id:
        raise SecretKeyNotFoundError(str(key_id))
    return key


async def get_key_by_name(
    session: AsyncSession, project_id: uuid.UUID, name: str
) -> SecretKey | None:
    result = await session.execute(
        select(SecretKey).where(
            SecretKey.project_id == project_id, SecretKey.name.ilike(name)
        )
    )
    return result.scalar_one_or_none()


async def create_key(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    created_by: uuid.UUID,
) -> SecretKey:
    key = SecretKey(project_id=project_id, name=name, description=description, created_by=created_by)
    session.add(key)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateSecretKeyNameError(name) from exc
    await session.refresh(key)
    return key


async def update_key(
    session: AsyncSession, key: SecretKey, *, name: str | None, description: str | None
) -> SecretKey:
    if name is not None:
        key.name = name
    if description is not None:
        key.description = description
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateSecretKeyNameError(name or key.name) from exc
    await session.refresh(key)
    return key


async def delete_key(session: AsyncSession, key: SecretKey) -> None:
    await session.delete(key)
    await session.commit()


async def _get_value_row(
    session: AsyncSession, secret_key_id: uuid.UUID, environment_id: uuid.UUID
) -> SecretValue | None:
    result = await session.execute(
        select(SecretValue).where(
            SecretValue.secret_key_id == secret_key_id,
            SecretValue.environment_id == environment_id,
        )
    )
    return result.scalar_one_or_none()


async def list_values_for_key(session: AsyncSession, secret_key_id: uuid.UUID) -> list[SecretValue]:
    result = await session.execute(
        select(SecretValue).where(SecretValue.secret_key_id == secret_key_id)
    )
    return list(result.scalars().all())


async def set_value(
    session: AsyncSession,
    *,
    secret_key_id: uuid.UUID,
    environment_id: uuid.UUID,
    plaintext: str,
    updated_by: uuid.UUID,
) -> SecretValue:
    """Upsert the encrypted value for one (key, environment) pair."""
    ciphertext = encrypt_value(plaintext)
    row = await _get_value_row(session, secret_key_id, environment_id)
    if row is None:
        row = SecretValue(
            secret_key_id=secret_key_id,
            environment_id=environment_id,
            ciphertext=ciphertext,
            updated_by=updated_by,
        )
        session.add(row)
    else:
        row.ciphertext = ciphertext
        row.updated_by = updated_by
    await session.commit()
    await session.refresh(row)
    return row


async def set_value_for_all_environments(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    secret_key_id: uuid.UUID,
    plaintext: str,
    updated_by: uuid.UUID,
) -> list[SecretValue]:
    """Write the same plaintext (re-encrypted per row) to every Environment the Project has."""
    environments = await list_environments(session, project_id)
    return [
        await set_value(
            session,
            secret_key_id=secret_key_id,
            environment_id=environment.id,
            plaintext=plaintext,
            updated_by=updated_by,
        )
        for environment in environments
    ]


async def reveal_value(
    session: AsyncSession, *, secret_key_id: uuid.UUID, environment_id: uuid.UUID
) -> str:
    """Decrypt and return the plaintext value for a (key, environment) pair.

    Callers MUST have already authorized the caller for plaintext access (nebular.projects.
    can_reveal, or a valid ProjectAccessKey) — this function performs no permission check itself.
    """
    row = await _get_value_row(session, secret_key_id, environment_id)
    if row is None:
        raise SecretValueNotFoundError(f"{secret_key_id}:{environment_id}")
    return decrypt_value(row.ciphertext)
