#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: GET /api/v1/health — public liveness check (no auth, matches every sibling app).
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from nebular import version
from nebular.api.endpoint import Endpoint
from nebular.models.health import HealthResponse


class HealthRouter(Endpoint):
    def __init__(self, *args, **kwargs):
        super().__init__(public=True, *args, **kwargs)
        self.add_api_route(
            "/",
            self.health,
            methods=["GET"],
            response_model=HealthResponse,
            summary="Liveness check",
        )

    async def health(self) -> HealthResponse:
        return HealthResponse(status="ok", version=version)


router = HealthRouter()
