#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/config — public, unauthenticated frontend bootstrap config.
@ai-context: The login screen needs to know which login methods to show (basic_login_disabled/
  oidc_login_disabled/oidc_login_caption) and the Authentik client_id/token_url BEFORE any
  credential exists to authenticate a call with — same reasoning as Satellite's own config.py. Also
  forwards `nebula.version` so the frontend footer can show the running build without duplicating it.
@version: 1.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

from nebula import version
from nebula.api.endpoint import Endpoint
from nebula.config import settings
from nebula.models.config import ConfigResponse


class ConfigRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(public=True, *args, **kwargs)
        self.add_api_route(
            "/",
            self.get_config,
            methods=["GET"],
            response_model=ConfigResponse,
            summary="Frontend bootstrap config",
        )

    async def get_config(self) -> ConfigResponse:
        return ConfigResponse(
            basic_login_disabled=settings.basic_login_disabled,
            oidc_login_disabled=settings.oidc_login_disabled,
            oidc_login_caption=settings.oidc_login_caption,
            client_id=settings.oidc_client_id,
            token_url=settings.oidc_token_endpoint,
            version=version,
        )


router = ConfigRouter()
