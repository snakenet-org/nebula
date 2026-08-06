#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey CRUD + value set/reveal — the encrypted key-value store itself.
@ai-context: The one module (besides nebula.crypto) that ever touches plaintext secret values.
  Since the 2026-08-06 global-environments redesign, a SecretKey carries its OWN `ciphertext` and
  `environment_id` directly — every key/value pair is linked to exactly one Environment, reassigned
  via update_key's `environment_id` param (never unset, never multi-valued — the old per-environment
  SecretValue join table and its "apply to all environments" convenience are both gone). set_value
  encrypts via nebula.crypto.encrypt_value before it ever reaches the session — the plaintext
  argument is never persisted raw. reveal_value is the only function that calls
  nebula.crypto.decrypt_value — callers (api/v1/secret.py's reveal route, api/v1/vault.py's
  external retrieval route) must have already checked the caller may see plaintext (can_reveal for
  the human route, project-access-key possession for the machine route) before calling it; this
  module does not re-check that itself, since "may this actor see plaintext" is a Project-level
  question answered by nebula.projects, not a secret-key-level one. create_keys_bulk backs the
  Project view's "Upload .env" flow — always creates brand-new keys (never updates an existing key's
  value), all-or-nothing in one commit; `variable_type` is per-item (a (name, value, variable_type)
  triple), letting the frontend's review dialog pick secret vs. environment variable per row instead
  of one type for the whole batch.
@ai-rules:
  - Never log a plaintext value.
  - encrypt_value/decrypt_value only — never import `cryptography` directly here.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 2.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.crypto import decrypt_value, encrypt_value
from nebula.models.tables import SecretKey, VariableType


class DuplicateSecretKeyNameError(Exception):
    """Raised on a case-insensitive SecretKey name collision within a Project."""


class SecretKeyNotFoundError(Exception):
    """Raised when a SecretKey id doesn't exist (or belongs to a different Project)."""


class SecretValueNotFoundError(Exception):
    """Raised when reveal_value is asked for a key that has no value set yet."""


class BulkDuplicateKeyNamesError(Exception):
    """Raised when a bulk-upload batch has a name colliding with another item in the same batch, or
    with a key that already exists in this Project — names every conflict so the caller can show a
    precise list rather than a generic "something conflicted"."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(", ".join(names))


class BulkCreateConflictError(Exception):
    """Raised only when the commit itself still fails after create_keys_bulk's own pre-checks pass —
    a concurrent write raced this one between the pre-check and the commit."""


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
    environment_id: uuid.UUID,
    variable_type: VariableType,
    created_by: uuid.UUID,
) -> SecretKey:
    key = SecretKey(
        project_id=project_id,
        name=name,
        description=description,
        environment_id=environment_id,
        variable_type=variable_type,
        created_by=created_by,
    )
    session.add(key)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateSecretKeyNameError(name) from exc
    await session.refresh(key)
    return key


async def update_key(
    session: AsyncSession,
    key: SecretKey,
    *,
    name: str | None = None,
    description: str | None = None,
    environment_id: uuid.UUID | None = None,
    variable_type: VariableType | None = None,
) -> SecretKey:
    if name is not None:
        key.name = name
    if description is not None:
        key.description = description
    if environment_id is not None:
        key.environment_id = environment_id
    if variable_type is not None:
        key.variable_type = variable_type
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


async def set_value(
    session: AsyncSession, key: SecretKey, *, plaintext: str, updated_by: uuid.UUID
) -> SecretKey:
    """Encrypt and store the value for this key's (single, linked) Environment."""
    key.ciphertext = encrypt_value(plaintext)
    key.updated_by = updated_by
    await session.commit()
    await session.refresh(key)
    return key


async def create_keys_bulk(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    environment_id: uuid.UUID,
    items: list[tuple[str, str, VariableType]],
    created_by: uuid.UUID,
) -> list[SecretKey]:
    """Create every (name, value, variable_type) triple in `items` as a brand-new key, one commit.

    All-or-nothing, per the "Upload .env" feature's spec: raises BulkDuplicateKeyNamesError (naming
    every conflicting key) and writes nothing at all if any name collides with another item in the
    same batch or with a key that already exists in this Project — a bulk upload never partially
    applies, and it never updates an existing key's value (that's what the per-row value editor is
    for). `variable_type` is per-item (the frontend's review dialog lets the caller pick secret vs.
    environment variable per row, and skip a row entirely by simply not including it here).
    """
    seen: dict[str, str] = {}
    within_batch_conflicts: list[str] = []
    for name, _value, _variable_type in items:
        lowered = name.lower()
        if lowered in seen:
            within_batch_conflicts.append(name)
        else:
            seen[lowered] = name
    if within_batch_conflicts:
        raise BulkDuplicateKeyNamesError(within_batch_conflicts)

    existing = await list_keys(session, project_id)
    existing_lower = {key.name.lower() for key in existing}
    against_existing_conflicts = [
        name for name, _value, _variable_type in items if name.lower() in existing_lower
    ]
    if against_existing_conflicts:
        raise BulkDuplicateKeyNamesError(against_existing_conflicts)

    created = [
        SecretKey(
            project_id=project_id,
            name=name,
            description=None,
            environment_id=environment_id,
            variable_type=variable_type,
            ciphertext=encrypt_value(value),
            created_by=created_by,
            updated_by=created_by,
        )
        for name, value, variable_type in items
    ]
    session.add_all(created)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise BulkCreateConflictError() from exc
    for key in created:
        await session.refresh(key)
    return created


async def reveal_value(session: AsyncSession, key: SecretKey) -> str:
    """Decrypt and return this key's plaintext value.

    Callers MUST have already authorized the caller for plaintext access (nebula.projects.
    can_reveal, or a valid ProjectAccessKey) — this function performs no permission check itself.
    """
    if key.ciphertext is None:
        raise SecretValueNotFoundError(str(key.id))
    return decrypt_value(key.ciphertext)
