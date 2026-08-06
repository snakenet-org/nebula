#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic response model for GET /api/v1/ping.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from pydantic import BaseModel


class PingResponse(BaseModel):
    message: str
