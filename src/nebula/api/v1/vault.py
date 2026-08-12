#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/vault/secret + GET /api/v1/vault/project + GET /api/v1/vault/status — the
  external, machine-to-machine surface. ALL THREE are gated on a project access key alone, no
  X-Nebula-Token.
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
@ai-rules:
  - Never log the resolved plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 5.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import access_keys as access_keys_service
from nebula import audit as audit_service
from nebula import environments as environments_service
from nebula import secrets as secrets_service
from nebula import version
from nebula.api.endpoint import Endpoint
from nebula.database import get_session
from nebula.models.tables import Project, ProjectAccessKey
from nebula.models.vault import (
    VaultProjectResponse,
    VaultSecretResponse,
    VaultStatusResponse,
)
from nebula.naming import NAME_PATTERN
from nebula.secrets import SecretValueNotFoundError

# Every /secret query param (environment, key) shares this charset — see nebula.naming.
_NameParam = Annotated[str, Query(min_length=1, pattern=NAME_PATTERN)]

VAULT_BEARER = HTTPBearer(auto_error=True)


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

        secret_key = await secrets_service.get_key_by_name(session, resolved_project.id, key)
        if secret_key is None:
            await _audit(success=False, detail="Unknown key")
            raise HTTPException(status_code=404, detail="Not found")

        # A key is now linked to exactly one Environment — the caller's requested environment name
        # must match it (case-insensitively), same anti-enumeration 404 as every other lookup miss.
        env = await environments_service.get_environment(session, secret_key.environment_id)
        if env.name.lower() != environment.lower():
            await _audit(success=False, object_id=secret_key.id, detail="Environment mismatch")
            raise HTTPException(status_code=404, detail="Not found")

        try:
            value = await secrets_service.reveal_value(session, secret_key)
        except SecretValueNotFoundError:
            await _audit(success=False, object_id=secret_key.id, detail="No value set")
            raise HTTPException(status_code=404, detail="Not found")

        await _audit(success=True, object_id=secret_key.id)
        return VaultSecretResponse(key=secret_key.name, environment=env.name, value=value)

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
