#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/vault/secret — the external, machine-to-machine secret-retrieval endpoint.
@ai-context: Deliberately a THIRD auth mode alongside human-JWT (project.py/secret.py/...) and the
  public no-credential routes (health/ping/config/auth) — a spawned container pulls its own secrets
  at deploy time by presenting a project access key, not a user session. Still requires
  X-Nebular-Token (every API call does, per spec) — added as an explicit router-level dependency
  since this router is constructed with public=True to skip Endpoint's normal JWT gate. The bearer
  credential is a ProjectAccessKey token (nebular.access_keys.resolve_access_key), not a JWT — no
  relation to get_current_user/get_jwt_claims at all. Key/environment are matched case-insensitively
  by name (nebular.secrets.get_key_by_name / nebular.environments.get_environment_by_name) since a
  machine caller only ever knows the human-readable names, never internal UUIDs. Any lookup miss
  (unknown key, unknown environment, or no value set for that pair) is a 404 — never distinguished
  from each other in the response, so a caller can't enumerate a project's key names by probing.
@ai-rules:
  - Never log the resolved plaintext value.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from nebular import access_keys as access_keys_service
from nebular import environments as environments_service
from nebular import secrets as secrets_service
from nebular.api.endpoint import Endpoint, verify_nebular_token
from nebular.database import get_session
from nebular.models.tables import Project, ProjectAccessKey
from nebular.models.vault import VaultSecretResponse
from nebular.secrets import SecretValueNotFoundError

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
    """Public router (no JWT gate) — auth is X-Nebular-Token + a project access key instead."""

    def __init__(self, *args, **kwargs):
        super().__init__(
            public=True, dependencies=[Depends(verify_nebular_token)], *args, **kwargs
        )
        self.add_api_route(
            "/secret",
            self.get_secret,
            methods=["GET"],
            response_model=VaultSecretResponse,
            summary="Retrieve one secret value by key + environment name",
        )

    async def get_secret(
        self,
        key: str,
        environment: str,
        resolved: tuple[Project, ProjectAccessKey] = Depends(get_access_key),
        session: AsyncSession = Depends(get_session),
    ) -> VaultSecretResponse:
        project, _access_key = resolved

        secret_key = await secrets_service.get_key_by_name(session, project.id, key)
        if secret_key is None:
            raise HTTPException(status_code=404, detail="Not found")

        # A key is now linked to exactly one Environment — the caller's requested environment name
        # must match it (case-insensitively), same anti-enumeration 404 as every other lookup miss.
        env = await environments_service.get_environment(session, secret_key.environment_id)
        if env.name.lower() != environment.lower():
            raise HTTPException(status_code=404, detail="Not found")

        try:
            value = await secrets_service.reveal_value(session, secret_key)
        except SecretValueNotFoundError:
            raise HTTPException(status_code=404, detail="Not found")

        return VaultSecretResponse(key=secret_key.name, environment=env.name, value=value)


router = VaultRouter()
