#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SecretKey CRUD + value set/reveal — thin wrapper over nebula.secrets.
@ai-context: Since the 2026-08-06 global-environments redesign, a key carries exactly one
  Environment link; list_keys/get_key responses carry PRESENCE ONLY (is_set), never ciphertext.
  Since 2026-08-09 (later same day), setting/changing what a value IS (set_value, an initial value
  or source_key_id at create_key time, every row of bulk_create_keys) requires can_edit_value
  (owner/admin only); reassigning environment_id/name/description/sync_enabled/deleting a key still
  only needs can_edit (owner/admin/shared EDITOR); revealing a value requires can_reveal (owner/
  admin/shared EDITOR — see nebula.projects' module docstring for the full split: a shared EDITOR
  can now read/copy a value but never write a new one). bulk_create_keys backs the Project view's
  "Upload .env" button — gated by can_edit_value (every row sets a value), always creates brand-new
  keys (409s naming every conflict rather than updating an existing key); one Environment applies to
  the whole batch, but `variable_type` is per-item (SecretBulkItem) so the review dialog can pick
  secret vs. environment variable per row.
  Since the same-day multi-repo GitHub sync redesign, every route that changes what a value actually
  IS (update_key, delete_key, set_value, bulk_create_keys, and create_key when a `value` was actually
  provided — see below) calls `_auto_sync_github` right after its own commit — this fans out to every
  enabled ProjectGithubSync target via nebula.github_sync.sync_all_for_project, so a linked repository
  never goes stale waiting for someone to remember to click "Sync now". This runs synchronously,
  in-request (there is no background task queue in this app), and is fully best-effort: a GitHub
  failure is recorded to the audit log per target but NEVER raised back into the route, so a value
  change always succeeds/responds on its own merits regardless of GitHub's availability.
  create_key's `payload.value` (added 2026-08-07) is optional — the create form can set an initial
  value in the same call instead of a separate PUT .../value round trip; `_auto_sync_github` only
  fires here when a value was actually included, matching every other route's "only sync when a
  value genuinely changed" rule.
  Since 2026-08-08, delete_key can 409 (SecretKeyInUseAsPatSourceError) when the key being deleted
  is still referenced as another ProjectGithubSync target's PAT source — see nebula.secrets and
  nebula.github_sync's "reference" PAT mode. Also since 2026-08-08, create_key/update_key thread a
  `sync_enabled` flag through to nebula.secrets — a key with sync_enabled=False is skipped entirely
  by github_sync.sync_to_github (never pushed, and never removed from an already-synced repo either,
  same push-only/no-deletion behavior a deleted key already has).
  Since 2026-08-09, create_key also accepts `payload.source_key_id`, making the new key a REFERENCE
  to another SecretKey's value instead of owning one directly (generalizes the GitHub-sync PAT
  reference — nebula.github_sync's `pat_source_key_id` — to ordinary secrets/variables; see
  nebula.secrets' module docstring for the resolution mechanics). `_resolve_source_key` is the one
  place that permission-checks it, mirroring api/v1/project.py's `_resolve_pat_source` almost
  exactly: the referenced key must exist, must belong to a DIFFERENT Project (the product ask is
  explicitly cross-project), must not itself be a reference (no chaining), and the ACTOR must have
  can_reveal (not just can_view) on the key's OWN Project — a plain Viewer of a foreign Project could
  otherwise wire up a reference that consumes a secret they can't even reveal themselves; a shared
  EDITOR of that foreign Project passes this bar too, same as they can now reveal it directly.
  create_key ALSO requires can_edit_value on THIS Project whenever payload.value or source_key_id is
  present — a shared EDITOR here can still create a bare key, just not one that already has (or
  points at) a value. delete_key can now ALSO 409 (SecretKeyInUseAsReferenceSourceError) when the key being
  deleted is still referenced by another SecretKey's source_key_id. update_key refuses
  (SecretKeyIsReferenceError → 409) to change a reference key's `variable_type`; set_value refuses
  the same way for its value — both are only ever changed by editing the SOURCE key, in ITS OWN
  Project ("referenced keys can only be changed in the source project"); name/description/
  environment_id/sync_enabled stay freely editable regardless of reference mode, since those are the
  referencing row's own local metadata. `_to_response` resolves `variable_type`/`is_set`/`value` via
  nebula.secrets.resolve_effective (the SOURCE key's CURRENT values for a reference, never this row's
  own possibly-irrelevant columns) and `source_project_id`/`source_label` via can_view on the source
  Project (display-only, silently omitted rather than 403ing if the current viewer can't see it —
  same shape as api/v1/project.py's `_to_target_response`). Deleting a reference key itself is an
  ordinary delete of just that row — it never touches (or even reveals visibility into) the source
  key it points at, since a FK delete only ever cascades/restricts downward, never upward to the row
  it references.
  Since 2026-08-09, `_to_response` also resolves `extraction_count` (nebula.audit.EXTRACTION_ACTIONS —
  see models/secret.py's docstring) — list_keys computes every key's count for the Project in one
  bulk query (nebula.audit.extraction_counts_by_project) and passes each key's value in explicitly
  to avoid an N+1 audit query per row; every other route builds a single-key response and lets
  `_to_response` look its own count up individually (extraction_count_for_key).
@ai-rules:
  - Never include SecretKey.ciphertext or a decrypted value in any response except reveal_value's.
  - A GitHub sync failure triggered by _auto_sync_github must never surface as an error response for
    the secret mutation that triggered it — catch broadly, audit-log, and move on.
  - A `source_key_id` must never be accepted without independently checking can_reveal on ITS OWN
    Project first — see _resolve_source_key. Never trust nebula.secrets' own defense-in-depth
    existence/no-chaining checks as a substitute for that permission check.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 5.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-09
"""

import uuid

from fastapi import Depends, HTTPException, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import environments as environments_service
from nebula import github_sync as github_sync_service
from nebula import projects as projects_service
from nebula import secrets as secrets_service
from nebula.api.endpoint import Endpoint, get_current_user
from nebula.database import get_session
from nebula.models.secret import (
    SecretBulkCreateRequest,
    SecretKeyCreateRequest,
    SecretKeyResponse,
    SecretKeyUpdateRequest,
    SecretRevealResponse,
    SecretValueSetRequest,
)
from nebula.models.tables import SecretKey, UserAccount, VariableType
from nebula.projects import ProjectNotFoundError
from nebula.secrets import (
    BulkCreateConflictError,
    BulkDuplicateKeyNamesError,
    DuplicateSecretKeyNameError,
    SecretKeyInUseAsPatSourceError,
    SecretKeyInUseAsReferenceSourceError,
    SecretKeyIsReferenceError,
    SecretKeyNotFoundError,
    SecretValueNotFoundError,
    SourceKeyIsReferenceError,
    SourceKeyNotFoundError,
)


async def _auto_sync_github(
    session: AsyncSession, actor: UserAccount, request: Request, project_id: uuid.UUID
) -> None:
    """Best-effort fan-out to every enabled GitHub sync target after a value-affecting mutation —
    see the module docstring. Never raises."""
    try:
        results = await github_sync_service.sync_all_for_project(session, project_id)
    except Exception:
        logger.exception("Auto GitHub sync crashed for project {}", project_id)
        return
    for result in results:
        detail = result["error"] or (
            f"{result['secrets_synced']} secret(s), {result['variables_synced']} variable(s) across "
            f"{result['environments_synced']} environment(s)"
            + (f"; {len(result['failures'])} failure(s)" if result["failures"] else "")
        )
        await audit_service.record_user_action(
            session, actor, request,
            action="github_sync_target.sync", object_type="project_github_sync",
            object_id=result["target_id"], object_label=result["name"], project_id=project_id,
            success=result["success"], detail=f"Auto-sync on value change: {detail}",
        )


async def _to_response(
    session: AsyncSession, actor: UserAccount, key: SecretKey, *, extraction_count: int | None = None
) -> SecretKeyResponse:
    # list_keys already computed the whole project's counts in one query and passes its value here;
    # every other caller (a single-key response) looks its own key up individually.
    if extraction_count is None:
        extraction_count = await audit_service.extraction_count_for_key(session, key.id)
    environment = await environments_service.get_environment(session, key.environment_id)
    # Resolved — for a reference key this is the SOURCE key's CURRENT type/value, never this row's
    # own possibly-irrelevant columns (nebula.secrets.resolve_effective).
    variable_type, ciphertext = await secrets_service.resolve_effective(session, key)
    # An "environment" variable is deliberately not anonymized — its value goes straight into the
    # list response; a "secret" always stays null here, plaintext only via the reveal endpoint.
    value = None
    if variable_type == VariableType.ENVIRONMENT and ciphertext is not None:
        value = await secrets_service.reveal_value(session, key)

    source_project_id: uuid.UUID | None = None
    source_label: str | None = None
    if key.source_key_id is not None:
        source_key = await secrets_service.get_key_by_id(session, key.source_key_id)
        if source_key is not None:
            # Display only — can_view (not can_reveal), silently omitted rather than 403ing if the
            # CURRENT viewer can't see that other Project — same shape as api/v1/project.py's
            # _to_target_response for pat_source_label.
            try:
                source_project, _share = await projects_service.get_visible_project(
                    session, actor, source_key.project_id
                )
                source_project_id = source_project.id
                source_label = f"{source_project.name} / {source_key.name}"
            except ProjectNotFoundError:
                pass

    return SecretKeyResponse(
        id=key.id,
        project_id=key.project_id,
        name=key.name,
        description=key.description,
        environment_id=key.environment_id,
        environment_name=environment.name,
        variable_type=variable_type,
        is_set=ciphertext is not None,
        value=value,
        sync_enabled=key.sync_enabled,
        source_key_id=key.source_key_id,
        source_project_id=source_project_id,
        source_label=source_label,
        extraction_count=extraction_count,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


class SecretRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_api_route(
            "/{project_id}", self.list_keys, methods=["GET"], response_model=list[SecretKeyResponse]
        )
        self.add_api_route(
            "/{project_id}", self.create_key, methods=["POST"], response_model=SecretKeyResponse, status_code=201
        )
        self.add_api_route(
            "/{project_id}/bulk",
            self.bulk_create_keys,
            methods=["POST"],
            response_model=list[SecretKeyResponse],
            status_code=201,
        )
        self.add_api_route(
            "/{project_id}/{key_id}", self.update_key, methods=["PATCH"], response_model=SecretKeyResponse
        )
        self.add_api_route("/{project_id}/{key_id}", self.delete_key, methods=["DELETE"], status_code=204)
        self.add_api_route(
            "/{project_id}/{key_id}/value", self.set_value, methods=["PUT"], response_model=SecretKeyResponse
        )
        self.add_api_route(
            "/{project_id}/{key_id}/reveal",
            self.reveal_value,
            methods=["GET"],
            response_model=SecretRevealResponse,
        )

    async def _project_or_404(self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID):
        try:
            return await projects_service.get_visible_project(session, actor, project_id)
        except ProjectNotFoundError:
            raise HTTPException(status_code=404, detail="Project not found")

    async def _key_or_404(self, session: AsyncSession, project_id: uuid.UUID, key_id: uuid.UUID) -> SecretKey:
        try:
            return await secrets_service.get_key(session, project_id, key_id)
        except SecretKeyNotFoundError:
            raise HTTPException(status_code=404, detail="Secret key not found")

    async def _environment_or_404(self, session: AsyncSession, environment_id: uuid.UUID) -> None:
        try:
            await environments_service.get_environment(session, environment_id)
        except environments_service.EnvironmentNotFoundError:
            raise HTTPException(status_code=404, detail="Environment not found")

    async def _resolve_source_key(
        self, session: AsyncSession, actor: UserAccount, project_id: uuid.UUID, key_id: uuid.UUID
    ) -> SecretKey:
        """Permission-checks a `source_key_id` before it's ever handed to nebula.secrets — the
        referenced key must exist, must belong to a DIFFERENT Project (referencing is explicitly
        cross-project — see the module docstring), must not itself already be a reference (no
        chaining), and the ACTOR must have can_reveal (not just can_view) on the key's OWN Project.
        Mirrors api/v1/project.py's `_resolve_pat_source` almost exactly."""
        key = await secrets_service.get_key_by_id(session, key_id)
        if key is None:
            raise HTTPException(status_code=422, detail="Referenced secret not found")
        if key.project_id == project_id:
            raise HTTPException(
                status_code=422, detail="Reference a key from a different project"
            )
        if key.source_key_id is not None:
            raise HTTPException(
                status_code=422, detail="Cannot reference a key that is itself a reference"
            )
        try:
            source_project, source_share = await projects_service.get_visible_project(
                session, actor, key.project_id
            )
        except ProjectNotFoundError:
            raise HTTPException(status_code=422, detail="Referenced secret not found")
        if not projects_service.can_reveal(actor, source_project, source_share):
            raise HTTPException(
                status_code=403,
                detail="You must be able to reveal values in the referenced secret's project",
            )
        return key

    async def list_keys(
        self,
        project_id: uuid.UUID,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[SecretKeyResponse]:
        await self._project_or_404(session, actor, project_id)
        rows = await secrets_service.list_keys(session, project_id)
        counts = await audit_service.extraction_counts_by_project(session, project_id)
        return [
            await _to_response(session, actor, row, extraction_count=counts.get(row.id, 0))
            for row in rows
        ]

    async def create_key(
        self,
        project_id: uuid.UUID,
        payload: SecretKeyCreateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        if (payload.value or payload.source_key_id is not None) and not projects_service.can_edit_value(
            actor, project
        ):
            raise HTTPException(status_code=403, detail="You cannot set a value in this project")
        await self._environment_or_404(session, payload.environment_id)
        source_key_id = None
        if payload.source_key_id is not None:
            source_key = await self._resolve_source_key(
                session, actor, project_id, payload.source_key_id
            )
            source_key_id = source_key.id
        try:
            row = await secrets_service.create_key(
                session,
                project_id,
                name=payload.name,
                description=payload.description,
                environment_id=payload.environment_id,
                variable_type=payload.variable_type,
                created_by=actor.id,
                value=payload.value,
                sync_enabled=payload.sync_enabled,
                source_key_id=source_key_id,
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        except SourceKeyNotFoundError:
            # Defense-in-depth only — _resolve_source_key should already have caught this via a
            # permission-checked lookup (e.g. a TOCTOU race where the key was deleted meanwhile).
            raise HTTPException(status_code=422, detail="Referenced secret not found")
        except SourceKeyIsReferenceError:
            raise HTTPException(
                status_code=422, detail="Cannot reference a key that is itself a reference"
            )
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.create", object_type="secret_key", object_id=row.id,
            object_label=row.name, project_id=project_id,
        )
        if payload.value or source_key_id is not None:
            await _auto_sync_github(session, actor, request, project_id)
        return await _to_response(session, actor, row)

    async def bulk_create_keys(
        self,
        project_id: uuid.UUID,
        payload: SecretBulkCreateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> list[SecretKeyResponse]:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit_value(actor, project):
            raise HTTPException(status_code=403, detail="You cannot set values in this project")
        await self._environment_or_404(session, payload.environment_id)
        if not payload.items:
            raise HTTPException(status_code=400, detail="No variables to add")
        try:
            rows = await secrets_service.create_keys_bulk(
                session,
                project_id,
                environment_id=payload.environment_id,
                items=[(item.name, item.value, item.variable_type) for item in payload.items],
                created_by=actor.id,
            )
        except BulkDuplicateKeyNamesError as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "These key names already exist or appear more than once in the upload: "
                    + ", ".join(exc.names)
                ),
            )
        except BulkCreateConflictError:
            raise HTTPException(status_code=409, detail="A key name conflicted while saving — please retry")
        for row in rows:
            await audit_service.record_user_action(
                session, actor, request,
                action="secret.create", object_type="secret_key", object_id=row.id,
                object_label=row.name, project_id=project_id, detail="Bulk .env upload",
            )
        await _auto_sync_github(session, actor, request, project_id)
        return [await _to_response(session, actor, row) for row in rows]

    async def update_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretKeyUpdateRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        if payload.environment_id is not None:
            await self._environment_or_404(session, payload.environment_id)
        try:
            key = await secrets_service.update_key(
                session,
                key,
                name=payload.name,
                description=payload.description,
                environment_id=payload.environment_id,
                variable_type=payload.variable_type,
                sync_enabled=payload.sync_enabled,
            )
        except DuplicateSecretKeyNameError:
            raise HTTPException(status_code=409, detail="A key with this name already exists")
        except SecretKeyIsReferenceError:
            raise HTTPException(
                status_code=409,
                detail="This key's type is inherited from its reference source — change it there instead.",
            )
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.update", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        await _auto_sync_github(session, actor, request, project_id)
        return await _to_response(session, actor, key)

    async def delete_key(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        project, share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit(actor, project, share):
            raise HTTPException(status_code=403, detail="You cannot edit this project")
        key = await self._key_or_404(session, project_id, key_id)
        key_id_copy, key_name = key.id, key.name
        try:
            await secrets_service.delete_key(session, key)
        except SecretKeyInUseAsPatSourceError:
            raise HTTPException(
                status_code=409,
                detail="This secret is used as the personal access token for a GitHub sync target "
                "— remove or reconfigure that sync target first.",
            )
        except SecretKeyInUseAsReferenceSourceError:
            raise HTTPException(
                status_code=409,
                detail="Another key still references this secret's value — remove that reference first.",
            )
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.delete", object_type="secret_key", object_id=key_id_copy,
            object_label=key_name, project_id=project_id,
        )
        await _auto_sync_github(session, actor, request, project_id)

    async def set_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        payload: SecretValueSetRequest,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretKeyResponse:
        project, _share = await self._project_or_404(session, actor, project_id)
        if not projects_service.can_edit_value(actor, project):
            raise HTTPException(status_code=403, detail="You cannot set values in this project")
        key = await self._key_or_404(session, project_id, key_id)
        try:
            key = await secrets_service.set_value(
                session, key, plaintext=payload.value, updated_by=actor.id
            )
        except SecretKeyIsReferenceError:
            raise HTTPException(
                status_code=409,
                detail="This key's value can only be changed in its source project.",
            )
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.value_set", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        await _auto_sync_github(session, actor, request, project_id)
        return await _to_response(session, actor, key)

    async def reveal_value(
        self,
        project_id: uuid.UUID,
        key_id: uuid.UUID,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> SecretRevealResponse:
        project, share = await self._project_or_404(session, actor, project_id)
        key = await self._key_or_404(session, project_id, key_id)
        # Resolved — a reference to an ENVIRONMENT-type source is exactly as visible as a normal
        # environment variable, regardless of this row's own (irrelevant) variable_type column.
        variable_type, _ciphertext = await secrets_service.resolve_effective(session, key)
        # An "environment" variable is already visible to anyone who can view the Project (its
        # value ships straight in the list response) — only a "secret" needs the stricter can_reveal
        # gate (owner/admin/shared EDITOR).
        if variable_type == VariableType.SECRET and not projects_service.can_reveal(actor, project, share):
            raise HTTPException(
                status_code=403, detail="You do not have permission to reveal values in this project"
            )
        environment = await environments_service.get_environment(session, key.environment_id)
        try:
            value = await secrets_service.reveal_value(session, key)
        except SecretValueNotFoundError:
            raise HTTPException(status_code=404, detail="No value set for this key")
        await audit_service.record_user_action(
            session, actor, request,
            action="secret.reveal", object_type="secret_key", object_id=key.id,
            object_label=key.name, project_id=project_id,
        )
        return SecretRevealResponse(key=key.name, environment=environment.name, value=value)


router = SecretRouter()
