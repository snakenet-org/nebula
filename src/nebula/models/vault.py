#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response models for api/v1/vault.py — the external, project-access-key
  authenticated surface (GET /secret, GET /status, GET /project).
@ai-context: VaultSecretResponse is deliberately its own module/response shape rather than reusing
  models.secret.SecretRevealResponse, even though the fields are identical today, since the two
  endpoints have unrelated auth models and audiences (a human session vs. a machine holding a
  project access key) and evolving one should never accidentally change the other.
  VaultStatusResponse backs GET /status — a lightweight "is my access key still valid, what version
  is this instance, what time does it think it is" check for a machine caller, same reasoning for a
  standalone shape (not models.health.HealthResponse, which is a public/no-auth liveness check with a
  different audience). `server_time` is UTC, timezone-aware — Nebula has no display-timezone concept
  (unlike Gravity's GRAVITY_TZ), so there's no other zone to prefer.
  VaultProjectResponse backs GET /project — the Project the presented access key resolves to;
  `description` is nullable since `Project.description` itself is optional.
  VaultSecretSetRequest (2026-08-27) backs PUT /vault/secret — the one vault.py route that CHANGES a
  value rather than reading one. `value` is plain text for every variable_type alike (secret,
  variable, or the new certificate — a certificate is just an uploaded file's text content, stored
  the exact same way a plain secret's value already is, see nebula.models.tables.VariableType).
@version: 1.3.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-27
"""

from datetime import datetime

from pydantic import BaseModel


class VaultSecretResponse(BaseModel):
    key: str
    environment: str
    value: str


class VaultSecretSetRequest(BaseModel):
    value: str


class VaultStatusResponse(BaseModel):
    version: str
    server_time: datetime


class VaultProjectResponse(BaseModel):
    name: str
    description: str | None
