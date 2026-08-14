#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Full-vault export/import — the "Import Vault"/"Export Vault" System Settings danger
  zones. Backs GET /api/v1/system/export and POST /api/v1/system/import.
@ai-context: export_vault walks every Environment and every Project/SecretKey app-wide (there is no
  visibility scoping here — this is an admin-only, whole-database operation, unlike every other
  listing function in this codebase) and returns a nebula.models.system.VaultExport. A plain key's
  value is DECRYPTED to plaintext in the export (nebula.crypto.decrypt_value) — the export file is
  the actual backup/portability artifact, so it must carry real, restorable secret material; a
  reference key (SecretKey.source_key_id) instead carries a pointer INTO THE SAME EXPORT
  (`reference_project_index` + `reference_key_name`, since neither the source key's nor the
  referencing key's real id survives a round-trip to a fresh Project on import).
  Deliberately excluded from both directions — this is a vault-CONTENT backup, not a full system
  dump:
    - ProjectShare: import always creates brand-new Projects owned by the importing admin (see
      import_vault below), so a stale Viewer/Editor row from the source instance wouldn't resolve to
      anyone meaningful there anyway.
    - ProjectAccessKey: only a token HASH is ever stored (nebula.access_keys) — the raw token can't
      be recovered to export, and a "recreate the key row with a new, different token" wouldn't be a
      faithful restore of anything a caller could actually use.
    - ProjectGithubSync: PATs and repo URLs are tied to a specific EXTERNAL system (a GitHub repo),
      not vault content — blindly recreating sync targets across instances/environments risks pushing
      a dev import's secrets at a production repo. An admin who needs GitHub sync after an import
      reconfigures it explicitly, same one-time setup as any new Project.
  import_vault ALWAYS creates brand-new Projects (never merges into an existing same-named one —
  Project.name carries no uniqueness constraint at all, see models/tables.py) and assigns every one
  of them to the importing `actor`, per explicit product spec ("assign ownership of them all to the
  user that does the import"). Environments are the one thing reused-by-name when possible (matching
  nebula.environments' own case-insensitive uniqueness) rather than duplicated, since they're global,
  shared taxonomy — re-importing the same export twice should not spawn a second "production"
  Environment.
  Runs in two passes over payload.projects: pass 1 creates every Project and every NON-reference key
  (recording each new key's id, keyed by (original project index, lowercased key name), since a
  reference elsewhere in the same file points at exactly that pair); pass 2 creates every reference
  key, resolving its `source_key_id` through that map. A reference whose target can't be resolved
  (e.g. a hand-edited or truncated export file) degrades to a plain, valueless key rather than
  aborting the whole import — counted in `references_skipped` so the caller can see it happened.
  NOT wrapped in one all-or-nothing transaction — nebula.projects.create_project/nebula.secrets.
  create_key each commit their own row (same as every other caller of these functions elsewhere in
  the codebase) — a failure partway through an import (e.g. a malformed row deep in a large file)
  can leave a partial import behind. Acceptable for an admin-only, self-produced-export-file
  operation; a future session could wrap this in an explicit transaction if that turns out to matter.
@ai-rules:
  - Never log a plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-13
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import environments as environments_service
from nebula import projects as projects_service
from nebula import secrets as secrets_service
from nebula.crypto import decrypt_value
from nebula.models.system import (
    VAULT_EXPORT_FORMAT,
    VaultExport,
    VaultExportEnvironment,
    VaultExportKey,
    VaultExportProject,
    VaultImportSummary,
)
from nebula.models.tables import Project, UserAccount


async def export_vault(session: AsyncSession) -> VaultExport:
    """Whole-vault, unscoped export — every Environment and every Project/SecretKey app-wide."""
    environments = await environments_service.list_environments(session)
    environment_name_by_id = {e.id: e.name for e in environments}

    result = await session.execute(select(Project).order_by(Project.name, Project.id))
    projects = list(result.scalars().all())
    project_index_by_id = {p.id: i for i, p in enumerate(projects)}

    export_projects: list[VaultExportProject] = []
    for project in projects:
        keys = await secrets_service.list_keys(session, project.id)
        export_keys: list[VaultExportKey] = []
        for key in keys:
            is_reference = key.source_key_id is not None
            reference_project_index: int | None = None
            reference_key_name: str | None = None
            value: str | None = None
            if is_reference:
                source = await secrets_service.get_key_by_id(session, key.source_key_id)
                if source is not None and source.project_id in project_index_by_id:
                    reference_project_index = project_index_by_id[source.project_id]
                    reference_key_name = source.name
                else:
                    # Source vanished (shouldn't happen — ON DELETE RESTRICT — but this is a read
                    # path, not the place to raise over a data-integrity assumption) — export as a
                    # plain, valueless key instead of dropping it or a stale/dangling pointer.
                    is_reference = False
            elif key.ciphertext is not None:
                value = decrypt_value(key.ciphertext)
            export_keys.append(
                VaultExportKey(
                    name=key.name,
                    description=key.description,
                    environment_name=environment_name_by_id.get(key.environment_id, ""),
                    variable_type=key.variable_type,
                    sync_enabled=key.sync_enabled,
                    value=value,
                    is_reference=is_reference,
                    reference_project_index=reference_project_index,
                    reference_key_name=reference_key_name,
                    rotation_frequency=key.rotation_frequency,
                    rotation_unit=key.rotation_unit,
                )
            )
        export_projects.append(
            VaultExportProject(
                name=project.name, description=project.description, keys=export_keys
            )
        )

    return VaultExport(
        format=VAULT_EXPORT_FORMAT,
        version=1,
        exported_at=datetime.utcnow(),
        environments=[
            VaultExportEnvironment(name=e.name, description=e.description) for e in environments
        ],
        projects=export_projects,
    )


async def import_vault(
    session: AsyncSession, actor: UserAccount, payload: VaultExport
) -> VaultImportSummary:
    """Import `payload` — every Project becomes a brand-new Project owned by `actor` (see the module
    docstring for why this never merges into an existing Project). Environments are reused by
    case-insensitive name when they already exist, created otherwise."""
    environment_id_by_name: dict[str, uuid.UUID] = {}
    environments_created = 0
    environments_reused = 0

    async def _resolve_environment(name: str, description: str | None) -> uuid.UUID:
        nonlocal environments_created, environments_reused
        cache_key = name.lower()
        if cache_key in environment_id_by_name:
            return environment_id_by_name[cache_key]
        existing = await environments_service.get_environment_by_name(session, name)
        if existing is not None:
            environment_id_by_name[cache_key] = existing.id
            environments_reused += 1
            return existing.id
        try:
            created = await environments_service.create_environment(
                session, name=name, description=description
            )
        except environments_service.DuplicateEnvironmentNameError:
            # Race — created by someone else between the lookup above and here.
            created = await environments_service.get_environment_by_name(session, name)
        environment_id_by_name[cache_key] = created.id
        environments_created += 1
        return created.id

    for env in payload.environments:
        await _resolve_environment(env.name, env.description)

    # Pass 1: every Project + every non-reference key. Records each new key's id keyed by (original
    # project index, lowercased name) so pass 2 can resolve reference pointers into it.
    new_key_id_by_ref: dict[tuple[int, str], uuid.UUID] = {}
    pending_references: list[tuple[uuid.UUID, VaultExportKey]] = []
    projects_created = 0
    keys_created = 0

    for project_index, project_payload in enumerate(payload.projects):
        project = await projects_service.create_project(
            session, actor, name=project_payload.name, description=project_payload.description
        )
        projects_created += 1
        for key_payload in project_payload.keys:
            if key_payload.is_reference:
                pending_references.append((project.id, key_payload))
                continue
            environment_id = await _resolve_environment(key_payload.environment_name, None)
            created_key = await secrets_service.create_key(
                session,
                project.id,
                name=key_payload.name,
                description=key_payload.description,
                environment_id=environment_id,
                variable_type=key_payload.variable_type,
                created_by=actor.id,
                value=key_payload.value,
                sync_enabled=key_payload.sync_enabled,
                rotation_frequency=key_payload.rotation_frequency,
                rotation_unit=key_payload.rotation_unit,
            )
            keys_created += 1
            new_key_id_by_ref[(project_index, key_payload.name.lower())] = created_key.id

    # Pass 2: reference keys — resolve `source_key_id` through the map built above.
    references_resolved = 0
    references_skipped = 0
    for new_project_id, key_payload in pending_references:
        environment_id = await _resolve_environment(key_payload.environment_name, None)
        source_key_id: uuid.UUID | None = None
        if key_payload.reference_project_index is not None and key_payload.reference_key_name:
            source_key_id = new_key_id_by_ref.get(
                (key_payload.reference_project_index, key_payload.reference_key_name.lower())
            )
        if source_key_id is None:
            references_skipped += 1
        else:
            references_resolved += 1
        await secrets_service.create_key(
            session,
            new_project_id,
            name=key_payload.name,
            description=key_payload.description,
            environment_id=environment_id,
            variable_type=key_payload.variable_type,
            created_by=actor.id,
            sync_enabled=key_payload.sync_enabled,
            source_key_id=source_key_id,
        )
        keys_created += 1

    return VaultImportSummary(
        environments_created=environments_created,
        environments_reused=environments_reused,
        projects_created=projects_created,
        keys_created=keys_created,
        references_resolved=references_resolved,
        references_skipped=references_skipped,
    )
