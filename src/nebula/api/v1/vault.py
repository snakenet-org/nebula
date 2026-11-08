#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/vault/secret + PUT /api/v1/vault/secret + GET /api/v1/vault/environment +
  GET /api/v1/vault/project + GET /api/v1/vault/status — the external, machine-to-machine surface.
  The four GET routes are
  gated on a project access key ALONE, no X-Nebula-Token; PUT /secret (2026-08-27, changes a value)
  is the one exception and requires BOTH.
@ai-context: This whole router is a THIRD auth mode alongside human-JWT (project.py/secret.py/...)
  and the public no-credential routes (health/ping/config/auth) — a spawned container pulls its own
  secrets at deploy time by presenting a project access key, not a user session or the shared
  X-Nebula-Token service secret. Constructed with public=True (skips Endpoint's normal
  X-Nebula-Token + JWT gates) and deliberately adds NEITHER back — every route here gates on
  `get_access_key` alone (a ProjectAccessKey bearer token, nebula.access_keys.resolve_access_key,
  no relation to get_current_user/get_jwt_claims at all). X-Nebula-Token used to be required on top
  of that for /secret and /project, and was the ONLY gate on /status — both dropped per explicit
  product direction: a caller presenting a valid project access key has already proven it holds a
  real, live credential for this instance, so the extra shared secret added no real boundary here,
  only friction for machine callers. Every other router in this API (project/environment/secret/
  access_key/audit/dashboard/auth) is UNCHANGED — X-Nebula-Token is still required there.
  /secret takes only `environment` + `key` as query params — the Project itself is never a query
  param, since the presented access key already resolves to exactly one Project
  (nebula.access_keys.resolve_access_key); a caller has no separate "which project" value to pass
  or get wrong. Both remaining params are charset-constrained via `nebula.naming.NAME_PATTERN`
  (FastAPI `Query(pattern=...)`) — letters/digits/hyphen/underscore only, matching what an
  Environment/SecretKey `name` is allowed to actually contain (see nebula.naming and
  models/{environment,secret}.py) — so a malformed query string 422s immediately instead of silently
  falling through to a 404 that looks identical to "wrong value." Both are matched
  case-insensitively by name (nebula.secrets.get_key_by_name / nebula.environments.get_environment)
  since a machine caller only ever knows the human-readable names, never internal UUIDs. Any lookup
  miss (unknown key, wrong environment, or no value set for that pair) is a 404 — never
  distinguished from each other in the response, so a caller can't enumerate a project's key names
  by probing.
  EVERY call to EVERY route in this router is now audit-logged (nebula.audit.record_access_key_action,
  actions "vault.retrieve"/"vault.project"/"vault.status", see nebula.audit.VAULT_ACTIONS) once the
  presented access key itself resolves — success and every non-200 response both get a row
  (success=False for the latter), backing the Audit Logs page's "API calls"/"Failed retrievals" tabs
  and the Dashboard's "API requests / day" / "Failed attempts / day" charts (nebula.dashboard —
  counts across ALL THREE actions, not just vault.retrieve). Every one of these audit rows also now
  carries `project_label=resolved_project.name` (2026-08-12) — the resolved Project's name captured
  at write time, backing the "API calls" tab's Project column alongside `actor_label` (already the
  access key's own name), so a row is attributable to "which key, from which Project" without
  parsing `object_label`'s combined "project/environment/key" string. A wholly invalid/revoked
  access key (get_access_key's own 401) is NOT logged here — an auth failure, not a request against
  a resolved Project, with no resolved actor to attribute it to.
  GET /status now REQUIRES a project access key too (previously the one route with no access-key
  gate at all — X-Nebula-Token alone was enough). It still returns nothing project-specific
  (`{version, server_time}`) and ignores which Project the key resolves to beyond validating it —
  the access key here is purely a credential check, not a scoping mechanism — but every call is
  still logged (action="vault.status") like the other two routes.
  GET /project takes only the access key — same shape as /secret minus the environment/key query
  params — and returns the resolved Project's name + description. No lookup miss is possible here
  (the access key already resolved to exactly one Project via get_access_key's own 401 gate), so
  unlike /secret there's only ever a single, success=True audit row (action="vault.project",
  object_type="project") — never a 404/failure branch to log.
  get_secret's audit rows now also carry object_id=secret_key.id whenever the key resolved (added
  2026-08-09) — previously only object_label (a display string), which made this route's
  "vault.retrieve" rows impossible to reliably attribute to one SecretKey by id (a renamed key would
  silently orphan its older rows). This is what lets nebula.audit.extraction_counts_by_project count
  machine (access-key) extractions per key, alongside secret.py's "secret.reveal", for
  ProjectView.vue's per-key extraction icon.
  2026-08-27: new `PUT /secret` — changes an EXISTING key's value (never creates one; same 404-on-
  any-lookup-miss shape as GET /secret) for any variable_type: secret, environment variable, or the
  new certificate (nebula.models.tables.VariableType.CERTIFICATE — a whole uploaded file, stored the
  same encrypted way a plain secret's value already is). This is the one route on this router that
  ALSO requires `X-Nebula-Token` (`dependencies=[Depends(verify_nebula_token)]` on this route only,
  not the router) on top of the project access key — a deliberate, narrower exception to this
  router's own "no X-Nebula-Token anywhere" rule (see the module purpose line above and
  api/endpoint.py's docstring), since this is the one vault.py call that WRITES rather than reads: an
  extra shared-secret gate on top of a possibly-leaked-in-a-log access key is a real second barrier
  for a mutating call in a way it wasn't for a read. Audit-logged as "vault.update" (nebula.audit.
  VAULT_ACTIONS) — deliberately NOT added to EXTRACTION_ACTIONS, since writing a value never reveals
  one. Refuses a reference key (SecretKeyIsReferenceError → 409, same as the human PUT
  /secret/{project}/{key}/value route) and fans out to every enabled GitHub sync target afterward,
  best-effort, exactly like every other value-changing route in this app (this module's own
  `_auto_sync_github`, attributed to the access key via record_access_key_action rather than a human
  UserAccount).
  2026-11-08: new `GET /environment?environment=<name>` — every key/value pair the access key's
  Project holds in that one Environment, as a flat `{name: value}` map (same auth as GET /secret:
  the access key alone, no X-Nebula-Token). Every variable_type is included (secret, environment
  variable, certificate), a reference key resolves to its SOURCE's current value (reveal_value), and
  a key with no value set is simply omitted rather than failing the whole call. An unknown
  Environment is a 404 (audited success=False); a known Environment with zero keys in this Project
  is a 200 with an empty map — environments are global, so "exists but empty here" isn't leaking
  anything a caller couldn't already learn. Audited as one "vault.environment" summary row per
  request plus one "vault.environment.key" row per returned key (object_id=key.id) so per-key
  extraction counts stay accurate — see nebula.audit's 2026-11-08 docstring entry.
@ai-rules:
  - Never log the resolved plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 6.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-11-08
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import access_keys as access_keys_service
from nebula import audit as audit_service
from nebula import environments as environments_service
from nebula import github_sync as github_sync_service
from nebula import secrets as secrets_service
from nebula import version
from nebula.api.endpoint import Endpoint, verify_nebula_token
from nebula.database import get_session
from nebula.models.tables import Project, ProjectAccessKey, SecretKey
from nebula.models.vault import (
    VaultEnvironmentResponse,
    VaultProjectResponse,
    VaultSecretResponse,
    VaultSecretSetRequest,
    VaultStatusResponse,
)
from nebula.naming import NAME_PATTERN
from nebula.secrets import SecretKeyIsReferenceError, SecretValueNotFoundError

# Every /secret query param (environment, key) shares this charset — see nebula.naming.
_NameParam = Annotated[str, Query(min_length=1, pattern=NAME_PATTERN)]

VAULT_BEARER = HTTPBearer(auto_error=True)


async def _auto_sync_github(
    session: AsyncSession, access_key: ProjectAccessKey, request: Request, project_id: uuid.UUID
) -> None:
    """Best-effort fan-out to every enabled GitHub sync target after PUT /secret changes a value —
    same shape/reasoning as api/v1/secret.py's own `_auto_sync_github`, just attributed to the
    Project access key that made the change (record_access_key_action) instead of a human UserAccount.
    Never raises — a GitHub outage must never fail the value change that triggered it."""
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
        await audit_service.record_access_key_action(
            session,
            access_key_id=access_key.id,
            access_key_label=access_key.name,
            request=request,
            action="github_sync_target.sync",
            object_type="project_github_sync",
            object_id=result["target_id"],
            object_label=result["name"],
            project_id=project_id,
            project_label=None,
            success=result["success"],
            detail=f"Auto-sync on value change (via vault API): {detail}",
        )


async def get_access_key(
    credentials: HTTPAuthorizationCredentials = Depends(VAULT_BEARER),
    session: AsyncSession = Depends(get_session),
) -> tuple[Project, ProjectAccessKey]:
    """Gate: resolve the presented bearer token to (Project, ProjectAccessKey), or 401."""
    resolved = await access_keys_service.resolve_access_key(session, credentials.credentials)
    if resolved is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked access key")
    return resolved


class VaultRouter(Endpoint):
    """Public router (no X-Nebula-Token, no JWT gate) — auth is a project access key alone."""

    def __init__(self, *args, **kwargs):
        super().__init__(public=True, *args, **kwargs)
        self.add_api_route(
            "/secret",
            self.get_secret,
            methods=["GET"],
            response_model=VaultSecretResponse,
            summary="Retrieve one secret value by environment + key name",
        )
        self.add_api_route(
            "/secret",
            self.set_secret,
            methods=["PUT"],
            response_model=VaultSecretResponse,
            summary="Change the value of an existing secret, variable, or certificate key",
            # Unlike every other route on this router, writing a value also requires X-Nebula-Token
            # on top of the project access key — see the module docstring for why.
            dependencies=[Depends(verify_nebula_token)],
        )
        self.add_api_route(
            "/environment",
            self.get_environment,
            methods=["GET"],
            response_model=VaultEnvironmentResponse,
            summary="Retrieve every key/value pair of the access key's Project in one environment",
        )
        self.add_api_route(
            "/status",
            self.get_status,
            methods=["GET"],
            response_model=VaultStatusResponse,
            summary="Report the running Nebula version and current server time",
        )
        self.add_api_route(
            "/project",
            self.get_project,
            methods=["GET"],
            response_model=VaultProjectResponse,
            summary="Retrieve the name and description of the access key's Project",
        )

    async def get_secret(
        self,
        environment: _NameParam,
        key: _NameParam,
        request: Request,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultSecretResponse:
        resolved_project, access_key = resolved

        async def _audit(
            *, success: bool, object_id: uuid.UUID | None = None, detail: str | None = None
        ) -> None:
            await audit_service.record_access_key_action(
                session,
                access_key_id=access_key.id,
                access_key_label=access_key.name,
                request=request,
                action="vault.retrieve",
                object_type="secret_key",
                object_id=object_id,
                object_label=f"{resolved_project.name}/{environment}/{key}",
                project_id=resolved_project.id,
                project_label=resolved_project.name,
                success=success,
                detail=detail,
            )

        # A key name is unique per (project, environment), not per project alone (2026-09-18) — the
        # requested environment must resolve first so the key lookup below can be scoped to it.
        env = await environments_service.get_environment_by_name(session, environment)
        if env is None:
            await _audit(success=False, detail="Unknown environment")
            raise HTTPException(status_code=404, detail="Not found")

        secret_key = await secrets_service.get_key_by_name(session, resolved_project.id, env.id, key)
        if secret_key is None:
            await _audit(success=False, detail="Unknown key")
            raise HTTPException(status_code=404, detail="Not found")

        try:
            value = await secrets_service.reveal_value(session, secret_key)
        except SecretValueNotFoundError:
            await _audit(success=False, object_id=secret_key.id, detail="No value set")
            raise HTTPException(status_code=404, detail="Not found")

        await _audit(success=True, object_id=secret_key.id)
        return VaultSecretResponse(key=secret_key.name, environment=env.name, value=value)

    async def set_secret(
        self,
        environment: _NameParam,
        key: _NameParam,
        payload: VaultSecretSetRequest,
        request: Request,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultSecretResponse:
        """Change an EXISTING key's value — never creates one (same lookup-miss-is-404 shape as
        get_secret, so a caller can't distinguish "wrong key name" from "wrong environment name"
        from "you're not allowed"). Works identically for every variable_type (secret, environment
        variable, or the new certificate — see nebula.models.tables.VariableType) since all three
        store their value through the exact same encrypted `ciphertext` column; a certificate is
        just its file's text content. Refuses on a reference key (SecretKeyIsReferenceError → 409),
        same as the human PUT /secret/{project}/{key}/value route — its value can only be changed by
        editing the SOURCE key, in its own Project.
        """
        resolved_project, access_key = resolved

        async def _audit(
            *, success: bool, object_id: uuid.UUID | None = None, detail: str | None = None
        ) -> None:
            await audit_service.record_access_key_action(
                session,
                access_key_id=access_key.id,
                access_key_label=access_key.name,
                request=request,
                action="vault.update",
                object_type="secret_key",
                object_id=object_id,
                object_label=f"{resolved_project.name}/{environment}/{key}",
                project_id=resolved_project.id,
                project_label=resolved_project.name,
                success=success,
                detail=detail,
            )

        # A key name is unique per (project, environment), not per project alone (2026-09-18) — the
        # requested environment must resolve first so the key lookup below can be scoped to it.
        env = await environments_service.get_environment_by_name(session, environment)
        if env is None:
            await _audit(success=False, detail="Unknown environment")
            raise HTTPException(status_code=404, detail="Not found")

        secret_key = await secrets_service.get_key_by_name(session, resolved_project.id, env.id, key)
        if secret_key is None:
            await _audit(success=False, detail="Unknown key")
            raise HTTPException(status_code=404, detail="Not found")

        try:
            # updated_by=None: no UserAccount performed this — see nebula.secrets.set_value's
            # docstring. rotation_frequency/rotation_unit are passed through UNCHANGED (the key's
            # own current schedule, not cleared) — set_value's contract otherwise fully REPLACES the
            # schedule on every call, and this machine route has no concept of rotation to offer, so
            # blindly wiping an active one here would silently disable it out from under a caller
            # that only meant to update a value.
            await secrets_service.set_value(
                session,
                secret_key,
                plaintext=payload.value,
                updated_by=None,
                rotation_frequency=secret_key.rotation_frequency,
                rotation_unit=secret_key.rotation_unit,
            )
        except SecretKeyIsReferenceError:
            await _audit(success=False, object_id=secret_key.id, detail="Key is a reference")
            raise HTTPException(
                status_code=409,
                detail="This key's value can only be changed in its source project.",
            )

        await _audit(success=True, object_id=secret_key.id)
        await _auto_sync_github(session, access_key, request, resolved_project.id)
        return VaultSecretResponse(key=secret_key.name, environment=env.name, value=payload.value)

    async def get_environment(
        self,
        environment: _NameParam,
        request: Request,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultEnvironmentResponse:
        """Every key/value pair the resolved Project holds in `environment` — see the module
        docstring's 2026-11-08 entry. Keys without a value are omitted, not an error."""
        resolved_project, access_key = resolved

        env = await environments_service.get_environment_by_name(session, environment)
        if env is None:
            await audit_service.record_access_key_action(
                session,
                access_key_id=access_key.id,
                access_key_label=access_key.name,
                request=request,
                action="vault.environment",
                object_type="environment",
                object_label=f"{resolved_project.name}/{environment}",
                project_id=resolved_project.id,
                project_label=resolved_project.name,
                success=False,
                detail="Unknown environment",
            )
            raise HTTPException(status_code=404, detail="Not found")

        keys = [
            k
            for k in await secrets_service.list_keys(session, resolved_project.id)
            if k.environment_id == env.id
        ]
        values: dict[str, str] = {}
        returned_keys: list[SecretKey] = []
        for secret_key in keys:
            try:
                values[secret_key.name] = await secrets_service.reveal_value(session, secret_key)
            except SecretValueNotFoundError:
                continue
            returned_keys.append(secret_key)

        # Per-key extraction rows first (EXTRACTION_ACTIONS only), then the one summary row
        # (VAULT_ACTIONS) — see nebula.audit's 2026-11-08 docstring entry.
        for secret_key in returned_keys:
            await audit_service.record_access_key_action(
                session,
                access_key_id=access_key.id,
                access_key_label=access_key.name,
                request=request,
                action="vault.environment.key",
                object_type="secret_key",
                object_id=secret_key.id,
                object_label=f"{resolved_project.name}/{env.name}/{secret_key.name}",
                project_id=resolved_project.id,
                project_label=resolved_project.name,
                success=True,
            )
        skipped = len(keys) - len(returned_keys)
        await audit_service.record_access_key_action(
            session,
            access_key_id=access_key.id,
            access_key_label=access_key.name,
            request=request,
            action="vault.environment",
            object_type="environment",
            object_id=env.id,
            object_label=f"{resolved_project.name}/{env.name}",
            project_id=resolved_project.id,
            project_label=resolved_project.name,
            success=True,
            detail=f"{len(returned_keys)} key(s) returned"
            + (f", {skipped} without a value skipped" if skipped else ""),
        )
        return VaultEnvironmentResponse(
            project=resolved_project.name, environment=env.name, values=values
        )

    async def get_status(
        self,
        request: Request,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultStatusResponse:
        resolved_project, access_key = resolved

        await audit_service.record_access_key_action(
            session,
            access_key_id=access_key.id,
            access_key_label=access_key.name,
            request=request,
            action="vault.status",
            object_type="project",
            object_label=resolved_project.name,
            project_id=resolved_project.id,
            project_label=resolved_project.name,
            success=True,
        )
        return VaultStatusResponse(version=version, server_time=datetime.now(timezone.utc))

    async def get_project(
        self,
        request: Request,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultProjectResponse:
        resolved_project, access_key = resolved

        await audit_service.record_access_key_action(
            session,
            access_key_id=access_key.id,
            access_key_label=access_key.name,
            request=request,
            action="vault.project",
            object_type="project",
            object_label=resolved_project.name,
            project_id=resolved_project.id,
            project_label=resolved_project.name,
            success=True,
        )
        return VaultProjectResponse(
            name=resolved_project.name, description=resolved_project.description
        )


router = VaultRouter()
