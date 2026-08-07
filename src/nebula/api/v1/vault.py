#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/vault/secret + GET /api/v1/vault/project (both project-access-key
  authenticated) + GET /api/v1/vault/status (X-Nebula-Token only) — the external,
  machine-to-machine surface.
@ai-context: /secret is a THIRD auth mode alongside human-JWT (project.py/secret.py/...) and the
  public no-credential routes (health/ping/config/auth) — a spawned container pulls its own secrets
  at deploy time by presenting a project access key, not a user session. Still requires
  X-Nebula-Token (every API call does, per spec) — added as an explicit router-level dependency
  since this router is constructed with public=True to skip Endpoint's normal JWT gate. The bearer
  credential is a ProjectAccessKey token (nebula.access_keys.resolve_access_key), not a JWT — no
  relation to get_current_user/get_jwt_claims at all.
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
  Every /secret call is audit-logged (nebula.audit.record_access_key_action, action="vault.retrieve")
  once the presented access key itself resolves — success and every 404 both get a row
  (success=False for the 404s), backing the Audit Logs page's "API calls"/"Failed retrievals" tabs
  and the Dashboard's daily extraction/failed-retrieval charts. A wholly invalid/revoked access key
  (get_access_key's own 401) is NOT logged here — an auth failure, not a retrieval attempt, with no
  resolved actor to attribute it to.
  GET /status deliberately takes NO project access key — access keys are strictly Project-scoped
  credentials, and a liveness/version/clock check isn't a Project-scoped operation, so gating it on
  one would be the wrong trust boundary. Auth is X-Nebula-Token alone (the router-level dependency
  every route here already has); status reveals nothing project-specific anyway, and is NOT
  audit-logged (mirrors health.py/ping.py's own unaudited liveness checks — this isn't a secret
  retrieval, and there'd be no resolved access key to attribute it to regardless).
  GET /project takes only the access key (+ X-Nebula-Token) — same shape as /secret minus the
  environment/key query params — and returns the resolved Project's name + description. No lookup
  miss is possible here (the access key already resolved to exactly one Project via
  get_access_key's own 401 gate), so unlike /secret there's only ever a single, success=True audit
  row (action="vault.project", object_type="project") — never a 404/failure branch to log.
@ai-rules:
  - Never log the resolved plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 4.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-07
"""

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
from nebula.api.endpoint import Endpoint, verify_nebula_token
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
    """Public router (no JWT gate) — auth is X-Nebula-Token + a project access key instead."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            public=True, dependencies=[Depends(verify_nebula_token)], *args, **kwargs
        )
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

        async def _audit(*, success: bool, detail: str | None = None) -> None:
            await audit_service.record_access_key_action(
                session,
                access_key_id=access_key.id,
                access_key_label=access_key.name,
                request=request,
                action="vault.retrieve",
                object_type="secret_key",
                object_label=f"{resolved_project.name}/{environment}/{key}",
                project_id=resolved_project.id,
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
            await _audit(success=False, detail="Environment mismatch")
            raise HTTPException(status_code=404, detail="Not found")

        try:
            value = await secrets_service.reveal_value(session, secret_key)
        except SecretValueNotFoundError:
            await _audit(success=False, detail="No value set")
            raise HTTPException(status_code=404, detail="Not found")

        await _audit(success=True)
        return VaultSecretResponse(key=secret_key.name, environment=env.name, value=value)

    async def get_status(self) -> VaultStatusResponse:
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
            success=True,
        )
        return VaultProjectResponse(
            name=resolved_project.name, description=resolved_project.description
        )


router = VaultRouter()
