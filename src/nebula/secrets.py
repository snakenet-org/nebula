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
  of one type for the whole batch. create_key's `value` param (added 2026-08-07) is optional — the
  create form can set an initial value in the same call, encrypted the same way set_value does;
  omitting it leaves the key valueless exactly as before. get_key_by_id (2026-08-08) is the one
  project-agnostic lookup in this module — used by nebula.github_sync/api/v1/project.py to resolve a
  cross-project "use this key as our PAT" reference, and (2026-08-09) by api/v1/secret.py to resolve
  a "use this key as our value" reference the same way. delete_key now refuses
  (SecretKeyInUseAsPatSourceError / SecretKeyInUseAsReferenceSourceError) to delete a key that's
  still referenced by a ProjectGithubSync's pat_source_key_id, or by another SecretKey's
  source_key_id — same RESTRICT-and-surface-a-clean-409 shape as nebula.environments.
  delete_environment's EnvironmentInUseError. `sync_enabled` (2026-08-08) is a per-key on/off toggle
  for GitHub sync — defaults true (create_key) and is otherwise only ever changed via update_key's
  optional param; nebula.github_sync.sync_to_github is what actually skips a disabled key at push
  time, this module only stores the flag.
  Since 2026-08-09, a key's value can ALSO be a REFERENCE to another SecretKey (`source_key_id`,
  create_key-only — see the class docstring for why this can't be changed via update_key) instead of
  a ciphertext this row owns directly — generalizes the GitHub-sync PAT reference to ordinary
  secrets/variables. No chaining: create_key rejects a `source_key_id` that itself already has a
  `source_key_id` (SourceKeyIsReferenceError) — the API router is responsible for the actual
  cross-project permission check (nebula.projects.can_reveal on the SOURCE key's own Project,
  mirroring api/v1/project.py's `_resolve_pat_source`) before ever calling in here; this module only
  re-checks existence/shape as a defense-in-depth backstop. resolve_effective is the one place that
  follows a reference — returns the (variable_type, ciphertext) actually in force for a key, its own
  when it isn't a reference, or the SOURCE key's CURRENT pair when it is (never cached — re-resolved
  on every call, so a value rotated in the source project takes effect everywhere it's referenced
  with nothing to re-save). reveal_value and nebula.github_sync.sync_to_github both go through it,
  so a reference key reveals/syncs exactly like a normal key from every OTHER surface's point of
  view. update_key/set_value both refuse (SecretKeyIsReferenceError) to change a reference key's
  variable_type or value directly — "the value can only be changed in the source project" is
  enforced here, not just in the frontend; name/description/environment_id/sync_enabled stay freely
  editable on a reference key, since those are this row's own local metadata, not its value.
  Since 2026-08-12 (later same day), create_key/set_value also accept an optional
  `rotation_frequency`/`rotation_unit` automatic-rotation schedule (RotationNotSupportedError for a
  reference key or a non-SECRET type — see nebula.rotation, which owns the actual due-check/
  regeneration logic this module never performs itself) and stamp `last_rotated_at` whenever a value
  is actually (re)set — create_key iff an initial `value` was given, set_value unconditionally.
@ai-rules:
  - Never log a plaintext value.
  - encrypt_value/decrypt_value only — never import `cryptography` directly here.
  - Always resolve a key's variable_type/ciphertext via resolve_effective before reading either
    directly — a reference row's OWN columns (`variable_type`, `ciphertext`) must never be trusted.
  - Maintain 100% type-hinting coverage.
  2026-08-27: set_value's `updated_by` widened to `uuid.UUID | None` — see its own docstring — to
  support api/v1/vault.py's new PUT /secret route, a Project-access-key-authenticated caller with no
  UserAccount to attribute the write to. No other behavior changed; VariableType.CERTIFICATE (a
  whole uploaded file, nebula.models.tables) needs no code changes anywhere in this module — it's
  stored/encrypted through the exact same `ciphertext`/`value` path a plain secret already uses.
@dependencies: sqlalchemy[asyncio]
@version: 3.4.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-27
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.crypto import decrypt_value, encrypt_value
from nebula.models.tables import (
    ProjectGithubSync,
    RotationUnit,
    SecretKey,
    VariableType,
)


class DuplicateSecretKeyNameError(Exception):
    """Raised on a case-insensitive SecretKey name collision within a Project."""


class SecretKeyNotFoundError(Exception):
    """Raised when a SecretKey id doesn't exist (or belongs to a different Project)."""


class SecretKeyInUseAsPatSourceError(Exception):
    """Raised when deleting a SecretKey that at least one ProjectGithubSync still references as its
    PAT source (pat_source_key_id) — mirrors EnvironmentInUseError's RESTRICT-not-CASCADE shape."""


class SecretKeyInUseAsReferenceSourceError(Exception):
    """Raised when deleting a SecretKey that at least one OTHER SecretKey still references as its
    value source (source_key_id) — same RESTRICT-not-CASCADE shape as
    SecretKeyInUseAsPatSourceError, generalized from GitHub-sync PATs to ordinary values."""


class SourceKeyNotFoundError(Exception):
    """Raised when a `source_key_id` doesn't resolve to an existing SecretKey. The API router
    should normally have already caught this via a permission-checked lookup before calling in here
    — this is a defense-in-depth backstop, e.g. against a TOCTOU race where the key was deleted
    between that check and this call."""


class SourceKeyIsReferenceError(Exception):
    """Raised when a `source_key_id` points at a key that is ITSELF a reference — chaining
    references is not supported, so every reference must point at an "original" key."""


class SecretKeyIsReferenceError(Exception):
    """Raised by set_value/update_key when asked to change a reference key's value or type
    directly — those are only ever changed by editing the SOURCE key, in its own Project."""


class RotationNotSupportedError(Exception):
    """Raised by create_key/set_value when a rotation schedule is given for a key that can't carry
    one — a reference key (owns no value of its own to rotate) or a non-SECRET variable_type
    (rotation is a secret-only concept — see models/secret.py's request validators, which are the
    primary defense; this is a backstop against calling in here directly with an inconsistent
    combination)."""


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


async def get_key_by_id(session: AsyncSession, key_id: uuid.UUID) -> SecretKey | None:
    """Project-agnostic lookup — the caller doesn't yet know which Project the key belongs to (a
    cross-project PAT reference, see the module docstring). Returns None rather than raising, since
    every caller of this needs to distinguish "not found" from other failure modes anyway."""
    return await session.get(SecretKey, key_id)


async def count_pat_source_references(session: AsyncSession, key_id: uuid.UUID) -> int:
    """How many ProjectGithubSync targets (across every Project) currently reference this key as
    their PAT source — used by delete_key's RESTRICT check."""
    return (
        await session.execute(
            select(func.count())
            .select_from(ProjectGithubSync)
            .where(ProjectGithubSync.pat_source_key_id == key_id)
        )
    ).scalar_one()


async def count_reference_uses(session: AsyncSession, key_id: uuid.UUID) -> int:
    """How many OTHER SecretKeys (across every Project) currently reference this key as their value
    source — used by delete_key's RESTRICT check."""
    return (
        await session.execute(
            select(func.count()).select_from(SecretKey).where(SecretKey.source_key_id == key_id)
        )
    ).scalar_one()


async def resolve_effective(session: AsyncSession, key: SecretKey) -> tuple[VariableType, str | None]:
    """The (variable_type, ciphertext) actually in force for this key: its own, unless it's a
    reference (source_key_id set), in which case the SOURCE key's CURRENT pair — resolved fresh on
    every call, never cached, so a value/type rotated in the source project is picked up immediately
    everywhere it's referenced. No chaining is possible (enforced at create_key time), so this is at
    most one hop. Returns the key's own (stale-by-definition-null) ciphertext if the source has since
    vanished — shouldn't happen given ON DELETE RESTRICT, but this is a read path, not the place to
    raise over a data-integrity assumption."""
    if key.source_key_id is None:
        return key.variable_type, key.ciphertext
    source = await session.get(SecretKey, key.source_key_id)
    if source is None:
        return key.variable_type, None
    return source.variable_type, source.ciphertext


async def get_key_by_name(
    session: AsyncSession, project_id: uuid.UUID, environment_id: uuid.UUID, name: str
) -> SecretKey | None:
    """Case-insensitive lookup scoped to one (project, environment) pair — since 2026-09-18 a key
    name is unique per (project, environment), not per project alone
    (uq_secret_keys_project_env_name_lower), so the same name may exist more than once in a Project
    as long as each occurrence is in a different Environment. `environment_id` is required here so
    this never risks matching more than one row; use find_key_by_name_any_environment for a
    diagnostic-only, environment-agnostic lookup instead."""
    result = await session.execute(
        select(SecretKey).where(
            SecretKey.project_id == project_id,
            SecretKey.environment_id == environment_id,
            SecretKey.name.ilike(name),
        )
    )
    return result.scalar_one_or_none()


async def find_key_by_name_any_environment(
    session: AsyncSession, project_id: uuid.UUID, name: str
) -> SecretKey | None:
    """Case-insensitive lookup by name across every Environment of a Project — diagnostic-only (e.g.
    api/v1/vault.py or mcp_server.py reporting "this key exists, but in a different environment"),
    since more than one row can now match a bare name within a Project. Returns an arbitrary match
    when more than one exists; never used to resolve a value — get_key_by_name is the one lookup
    that's actually environment-scoped and safe for that."""
    result = await session.execute(
        select(SecretKey).where(SecretKey.project_id == project_id, SecretKey.name.ilike(name))
    )
    return result.scalars().first()


async def create_key(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    environment_id: uuid.UUID,
    variable_type: VariableType,
    created_by: uuid.UUID,
    value: str | None = None,
    sync_enabled: bool = True,
    source_key_id: uuid.UUID | None = None,
    rotation_frequency: int | None = None,
    rotation_unit: RotationUnit | str | None = None,
) -> SecretKey:
    """`source_key_id` makes this a REFERENCE key — see the module docstring. The caller
    (api/v1/secret.py) must have already permission-checked it (can_reveal on the source key's OWN
    Project); this only re-validates shape as a defense-in-depth backstop. When given, `value` is
    ignored (a reference's value always comes from the source) and `variable_type` is overridden to
    match the source's CURRENT type at creation time — cosmetic only, since every real read goes
    through resolve_effective instead of this row's own column.

    `rotation_frequency`/`rotation_unit` (see nebula.rotation) may only be given for a plain,
    directly-valued SECRET key — raises RotationNotSupportedError otherwise (a reference key or a
    non-SECRET variable_type). `last_rotated_at` is stamped now iff an initial value was actually
    given, same "the value just changed" trigger set_value uses.
    """
    if (rotation_frequency is not None or rotation_unit is not None) and (
        source_key_id is not None or variable_type != VariableType.SECRET
    ):
        raise RotationNotSupportedError(name)
    if source_key_id is not None:
        source = await session.get(SecretKey, source_key_id)
        if source is None:
            raise SourceKeyNotFoundError(str(source_key_id))
        if source.source_key_id is not None:
            raise SourceKeyIsReferenceError(str(source_key_id))
        variable_type = source.variable_type
        value = None
    key = SecretKey(
        project_id=project_id,
        name=name,
        description=description,
        environment_id=environment_id,
        variable_type=variable_type,
        created_by=created_by,
        ciphertext=encrypt_value(value) if value else None,
        updated_by=created_by if value else None,
        sync_enabled=sync_enabled,
        source_key_id=source_key_id,
        rotation_frequency=rotation_frequency,
        rotation_unit=rotation_unit,
        last_rotated_at=datetime.utcnow() if value else None,
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
    sync_enabled: bool | None = None,
) -> SecretKey:
    """A reference key's `variable_type` may never be changed here — it's inherited live from the
    source (resolve_effective), never something to reassign in the referencing Project. Every other
    field (name/description/environment_id/sync_enabled) stays freely editable regardless of
    reference mode — reassigning which key it references isn't supported yet (create a new reference
    instead)."""
    if variable_type is not None and key.source_key_id is not None:
        raise SecretKeyIsReferenceError(str(key.id))
    if name is not None:
        key.name = name
    if description is not None:
        key.description = description
    if environment_id is not None:
        key.environment_id = environment_id
    if variable_type is not None:
        key.variable_type = variable_type
    if sync_enabled is not None:
        key.sync_enabled = sync_enabled
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateSecretKeyNameError(name or key.name) from exc
    await session.refresh(key)
    return key


async def delete_key(session: AsyncSession, key: SecretKey) -> None:
    """Deleting a key that IS a reference (has its own source_key_id set) only ever removes this
    row — the source key it points at is never touched, since a plain FK delete never cascades
    upward to its own referenced row. Deleting a key that's referenced BY others is what's actually
    restricted, below."""
    if await count_pat_source_references(session, key.id):
        raise SecretKeyInUseAsPatSourceError(str(key.id))
    if await count_reference_uses(session, key.id):
        raise SecretKeyInUseAsReferenceSourceError(str(key.id))
    await session.delete(key)
    await session.commit()


async def set_value(
    session: AsyncSession,
    key: SecretKey,
    *,
    plaintext: str,
    updated_by: uuid.UUID | None,
    rotation_frequency: int | None = None,
    rotation_unit: RotationUnit | str | None = None,
) -> SecretKey:
    """Encrypt and store the value for this key's (single, linked) Environment, and stamp
    last_rotated_at (see nebula.rotation) since the value just changed.

    Refuses on a reference key (SecretKeyIsReferenceError) — its value can only ever be changed by
    editing the SOURCE key, in its own Project. `rotation_frequency`/`rotation_unit` fully REPLACE
    this key's rotation schedule (both None disables it) — unlike update_key's other fields, there's
    no "omitted means unchanged" here, since the Set Value form always submits the schedule's
    current on-screen state alongside the value. Raises RotationNotSupportedError for a non-SECRET
    key given a schedule (see create_key's docstring for the same rule).

    `updated_by=None` (2026-08-27) is for a caller with no attributable UserAccount — api/v1/
    vault.py's PUT /secret route, a Project access key rather than a human, passes None here for the
    same "no attributable actor" reasoning nebula.rotation.rotate_key's own updated_by=None already
    uses.
    """
    if key.source_key_id is not None:
        raise SecretKeyIsReferenceError(str(key.id))
    if (rotation_frequency is not None or rotation_unit is not None) and (
        key.variable_type != VariableType.SECRET
    ):
        raise RotationNotSupportedError(str(key.id))
    key.ciphertext = encrypt_value(plaintext)
    key.updated_by = updated_by
    key.rotation_frequency = rotation_frequency
    key.rotation_unit = rotation_unit
    key.last_rotated_at = datetime.utcnow()
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
    sync_enabled: bool = False,
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
    # Scoped to the batch's own target environment — a name already used in a DIFFERENT environment
    # of this Project is no longer a conflict (2026-09-18, uq_secret_keys_project_env_name_lower).
    existing_lower = {
        key.name.lower() for key in existing if key.environment_id == environment_id
    }
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
            sync_enabled=sync_enabled,
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
    """Decrypt and return this key's plaintext value — resolved via resolve_effective, so a
    reference key transparently reveals its SOURCE key's current value.

    Callers MUST have already authorized the caller for plaintext access (nebula.projects.
    can_reveal, or a valid ProjectAccessKey) — this function performs no permission check itself.
    """
    _variable_type, ciphertext = await resolve_effective(session, key)
    if ciphertext is None:
        raise SecretValueNotFoundError(str(key.id))
    return decrypt_value(ciphertext)
