#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Abstract base router class + shared auth gates every Nebula API endpoint uses.
@ai-context: Endpoint(APIRouter) is the parent of every v1 router. Nebula protects its API with two
  cooperating gates (mirrors Satellite's api/endpoint.py exactly):
    1. verify_nebula_token — header `X-Nebula-Token` must equal env NEBULA_TOKEN (a coarse shared
       service secret carried on EVERY request, including auth and the public config/health routes).
    2. verify_jwt_token — `Authorization: Bearer <token>`. Accepts BOTH a locally minted HS256 token
       (from POST /auth/login, the optional admin login) AND an Authentik RS256 access token
       (validated against the provider JWKS). The JWT header's `alg` selects the path.
  Router construction flags:
    - public=True → no gates at all (auth/health/ping/config validate/need nothing themselves).
  get_jwt_claims is a handler-level dependency returning the validated claims. get_current_user goes
  one step further and resolves the actual UserAccount row (auto-provisioning an OIDC identity on
  the fly if somehow not yet provisioned, though the normal path is POST /auth/oidc doing that once
  at login) — used by every route that needs to check ownership/sharing, not just "is logged in".
  api/v1/vault.py is the one router that does NOT use verify_jwt_token/get_current_user at all — it
  authenticates via a ProjectAccessKey bearer token instead (nebula.access_keys.resolve_access_key),
  a third, deliberately separate credential kind for machine callers.
@ai-rules:
  - All API routers must extend Endpoint, not APIRouter directly.
  - Never return raw passwords, tokens, or secrets in API responses or logs.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, pyjwt, sqlalchemy[asyncio], loguru
@version: 1.1.1
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-10-15
"""

import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import users
from nebula.config import settings
from nebula.database import get_session
from nebula.entitlements import entitlements_for_groups, has_access, is_admin
from nebula.models.tables import UserAccount
from nebula.security import LOCAL_ISSUER, decode_local_token

# ── Bearer JWT scheme ───────────────────────────────────────────────────────
NEBULA_JWT_TOKEN = HTTPBearer(auto_error=True)

# Lazily-built, cached JWKS client (fetches + caches Authentik's signing keys).
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    """Return the cached PyJWKClient, creating it on first use."""
    global _jwks_client
    if _jwks_client is None:
        if not settings.oidc_jwks_url:
            raise HTTPException(
                status_code=500, detail="OIDC not configured (NEBULA_OIDC_JWKS_URL)"
            )
        _jwks_client = jwt.PyJWKClient(settings.oidc_jwks_url)
    return _jwks_client


def decode_oidc(token: str) -> dict:
    """Validate an Authentik OIDC access token (RS256) against the provider JWKS and return claims.
    Audience and issuer are enforced only when configured."""
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience or None,
            issuer=settings.oidc_issuer or None,
            options={
                "verify_aud": bool(settings.oidc_audience),
                "verify_iss": bool(settings.oidc_issuer),
            },
        )
    except jwt.PyJWTError as exc:
        logger.debug(f"OIDC token rejected: {exc}")
        raise HTTPException(status_code=401, detail="Invalid token")


def decode_any_token(token: str) -> dict:
    """Validate either a local HS256 token or an Authentik RS256 token and return its claims."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        logger.debug(f"Malformed JWT header: {exc}")
        raise HTTPException(status_code=401, detail="Invalid token")

    alg = header.get("alg")
    if alg == "HS256":
        try:
            return decode_local_token(token)
        except jwt.PyJWTError as exc:
            logger.debug(f"Local token rejected: {exc}")
            raise HTTPException(status_code=401, detail="Invalid token")
        except RuntimeError as exc:
            # decode_local_token raises a bare RuntimeError (not a jwt.PyJWTError) when
            # NEBULA_JWT_SECRET isn't configured — an unset local-login secret, not a bad token.
            # Must be caught here too, or any HS256-looking bearer token (e.g. a stale one left in
            # a browser's localStorage) escapes as an unhandled 500 instead of a clean error.
            logger.error(f"Local token validation unavailable: {exc}")
            raise HTTPException(status_code=500, detail="Local login not configured (NEBULA_JWT_SECRET)")
    if alg == "RS256":
        return decode_oidc(token)

    raise HTTPException(status_code=401, detail="Unsupported token algorithm")


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(NEBULA_JWT_TOKEN),
) -> str:
    """Gate: require a valid bearer JWT (local HS256 or Authentik RS256). Returns the raw token."""
    decode_any_token(credentials.credentials)
    return credentials.credentials


def get_jwt_claims(
    credentials: HTTPAuthorizationCredentials = Depends(NEBULA_JWT_TOKEN),
) -> dict:
    """Handler-level dependency: decode and return the caller's validated claims (`sub`, `groups`…)."""
    return decode_any_token(credentials.credentials)


async def get_current_user(
    claims: dict = Depends(get_jwt_claims),
    session: AsyncSession = Depends(get_session),
) -> UserAccount:
    """Resolve the caller's UserAccount row, enforcing the coarse "has any entitlement" check.

    A local-login token's `sub` is the Nebula user id itself (security.create_access_token mints it
    that way); an Authentik token's `sub` is Authentik's own external subject id, distinguished here
    via the `iss` claim (LOCAL_ISSUER vs. anything else). The normal path for an OIDC identity is
    already provisioned once at POST /auth/oidc — the on-the-fly provision_oidc_user call below is a
    defensive fallback, not the primary path.
    """
    entitlements = entitlements_for_groups(claims.get(settings.oidc_groups_claim, []) or [])
    if not has_access(entitlements):
        raise HTTPException(status_code=403, detail="No entitlements")

    if claims.get("iss") == LOCAL_ISSUER:
        user = await users.get_by_id(session, uuid.UUID(claims["sub"]))
    else:
        user = await users.get_by_sub(session, claims["sub"])
        if user is None:
            user = await users.provision_oidc_user(
                session, claims, is_admin=is_admin(entitlements)
            )

    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def client_ip(request: Request) -> str | None:
    """Best-effort caller IP — used only as an nebula.audit AuditLogEntry.ip_address hint."""
    return request.client.host if request.client else None


# ── X-Nebula-Token (shared service secret) ──────────────────────────────────
X_NEBULA_TOKEN_SCHEME = APIKeyHeader(name="X-Nebula-Token", auto_error=False)


def verify_nebula_token(token: str = Depends(X_NEBULA_TOKEN_SCHEME)) -> str:
    """Gate: validate the presence and value of the X-Nebula-Token header."""
    expected = settings.nebula_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Nebula-Token"
        )
    if not expected or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid X-Nebula-Token"
        )
    return token


class Endpoint(APIRouter):
    """Base router. By default injects the X-Nebula-Token + JWT gates on every route.

    Pass ``public=True`` to drop both gates (auth/health/ping/config, and api/v1/vault.py — which
    adds its own X-Nebula-Token + project-access-key gates manually instead).
    """

    def __init__(self, public: bool = False, *args, **kwargs):
        router_dependencies = kwargs.pop("dependencies", [])
        if not public:
            router_dependencies.append(Depends(verify_nebula_token))
            router_dependencies.append(Depends(verify_jwt_token))
        super().__init__(*args, dependencies=router_dependencies, **kwargs)
