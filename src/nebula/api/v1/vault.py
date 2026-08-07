#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/vault/secret + GET /api/v1/vault/status — the external, machine-to-machine
  surface authenticated by a project access key.
@ai-context: Deliberately a THIRD auth mode alongside human-JWT (project.py/secret.py/...) and the
  public no-credential routes (health/ping/config/auth) — a spawned container pulls its own secrets
  at deploy time by presenting a project access key, not a user session. Still requires
  X-Nebula-Token (every API call does, per spec) — added as an explicit router-level dependency
  since this router is constructed with public=True to skip Endpoint's normal JWT gate. The bearer
  credential is a ProjectAccessKey token (nebula.access_keys.resolve_access_key), not a JWT — no
  relation to get_current_user/get_jwt_claims at all.
  /secret now REQUIRES three query params — project, environment, key — not just the latter two: an
  access key alone already resolves to exactly one Project (nebula.access_keys.resolve_access_key),
  so `project` is a second factor the caller must also know and get right, not something the lookup
  needs — it's checked against the resolved Project's own name (case-insensitively) before anything
  else, and a mismatch is the same anti-enumeration 404 as every other lookup miss below. All three
  are also charset-constrained via `nebula.naming.NAME_PATTERN` (FastAPI `Query(pattern=...)`) —
  letters/digits/hyphen/underscore only, matching what a Project/Environment/SecretKey `name` is
  allowed to actually contain (see nebula.naming and models/{project,environment,secret}.py) — so a
  malformed query string 422s immediately instead of silently falling through to a 404 that looks
  identical to "wrong value." project/environment/key are matched case-insensitively by name
  (nebula.secrets.get_key_by_name / nebula.environments.get_environment) since a machine caller only
  ever knows the human-readable names, never internal UUIDs. Any lookup miss (wrong project, unknown
  key, wrong environment, or no value set for that pair) is a 404 — never distinguished from each
  other in the response, so a caller can't enumerate a project's key names (or its own project's
  name) by probing.
  Every /secret call is audit-logged (nebula.audit.record_access_key_action, action="vault.retrieve")
  once the presented access key itself resolves — success and every 404 both get a row
  (success=False for the 404s), backing the Audit Logs page's "API calls"/"Failed retrievals" tabs
  and the Dashboard's daily extraction/failed-retrieval charts. A wholly invalid/revoked access key
  (get_access_key's own 401) is NOT logged here — an auth failure, not a retrieval attempt, with no
  resolved actor to attribute it to.
  GET /status is a lightweight liveness/version/clock check for a machine caller holding an access
  key — same auth gate as /secret (X-Nebula-Token + a valid, non-revoked project access key, which
  bumps the key's own last_used_at via resolve_access_key) but reveals nothing project-specific, so
  it is NOT audit-logged (mirrors health.py/ping.py's own unaudited liveness checks — this isn't a
  secret retrieval).
@ai-rules:
  - Never log the resolved plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 3.0.0
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
from nebula.models.vault import VaultSecretResponse, VaultStatusResponse
from nebula.naming import NAME_PATTERN
from nebula.secrets import SecretValueNotFoundError

# Every /secret query param (project, environment, key) shares this charset — see nebula.naming.
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
            summary="Retrieve one secret value by project + environment + key name",
        )
        self.add_api_route(
            "/status",
            self.get_status,
            methods=["GET"],
            response_model=VaultStatusResponse,
            summary="Report the running Nebula version and current server time",
        )

    async def get_secret(
        self,
        project: _NameParam,
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
                object_label=f"{project}/{environment}/{key}",
                project_id=resolved_project.id,
                success=success,
                detail=detail,
            )

        # The access key alone already resolves to exactly one Project — `project` is a second
        # factor the caller must also know and get right, same anti-enumeration 404 as every other
        # lookup miss below (never distinguished from an unknown key/environment in the response).
        if resolved_project.name.lower() != project.lower():
            await _audit(success=False, detail="Project mismatch")
            raise HTTPException(status_code=404, detail="Not found")

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

    async def get_status(
        self,
        _resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
    ) -> VaultStatusResponse:
        return VaultStatusResponse(version=version, server_time=datetime.now(timezone.utc))


router = VaultRouter()
