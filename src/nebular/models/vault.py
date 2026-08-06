#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response model for GET /api/v1/vault/secret — the external, project-access-key
  authenticated secret-retrieval endpoint (api/v1/vault.py). Deliberately its own module/response
  shape rather than reusing models.secret.SecretRevealResponse, even though the fields are identical
  today, since the two endpoints have unrelated auth models and audiences (a human session vs. a
  machine holding a project access key) and evolving one should never accidentally change the other.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from pydantic import BaseModel


class VaultSecretResponse(BaseModel):
    key: str
    environment: str
    value: str
