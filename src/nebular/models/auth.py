#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/auth.py — local login + Authentik exchange.
@ai-context: AuthResponse is shared by both login paths (mirrors Satellite's own AuthResponse
  shape): the bearer token, the shared X-Nebular-Token the frontend must echo on every subsequent
  call, and the resolved identity/entitlements.
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class OidcExchangeRequest(BaseModel):
    access_token: str
    id_token: str | None = None


class AuthResponse(BaseModel):
    message: str
    token: str
    nebular_token: str
    id: str
    name: str | None
    email: str | None
    groups: list[str]
    entitlements: list[str]
    is_admin: bool
