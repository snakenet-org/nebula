#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/ping — public trivial connectivity check (no auth, matches every sibling
  app — distinct from /health, which also reports the running version).
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from nebular.api.endpoint import Endpoint
from nebular.models.ping import PingResponse


class PingRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(public=True, *args, **kwargs)
        self.add_api_route(
            "/", self.ping, methods=["GET"], response_model=PingResponse, summary="Connectivity check"
        )

    async def ping(self) -> PingResponse:
        return PingResponse(message="pong")


router = PingRouter()
