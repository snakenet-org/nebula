#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response model for GET /api/v1/config — public, unauthenticated frontend
  bootstrap config (login-screen feature flags + OIDC client id), mirrors Satellite's ConfigResponse.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from pydantic import BaseModel


class ConfigResponse(BaseModel):
    basic_login_disabled: bool
    oidc_login_disabled: bool
    oidc_login_caption: str
    client_id: str
    token_url: str
