#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Public auth endpoints — local login (the optional admin login) + snakeNet ID exchange.
@ai-context: This router is PUBLIC (no gates); each handler validates credentials/tokens itself.
  POST /api/v1/auth/login — verify the local bootstrap-admin username/password, mint a Nebula
    HS256 token. Only meaningful when NEBULA_BASIC_LOGIN_DISABLED is unset/no.
  POST /api/v1/auth/oidc — the frontend completes the Authentik Authorization-Code + PKCE flow
    against id.snakenet.io, then posts the resulting access token here; Nebula validates it against
    Authentik's JWKS and reuses it as the bearer (Nebula mints nothing for OIDC). Auto-provisions
    the user via nebula.users.provision_oidc_user on every call (idempotent, keeps is_admin fresh).
  Both return an AuthResponse carrying the bearer token + the X-Nebula-Token shared secret the
  frontend must echo on subsequent calls, plus the resolved identity/entitlements.
  POST /api/v1/auth/logout — JWT-gated (unlike the two routes above) purely so it can attribute a
  nebula.audit "auth.logout" row to the caller; Nebula mints stateless JWTs it never tracks
  server-side, so there is no session to actually invalidate here — the frontend still discards its
  locally-held token regardless of this call's outcome.
@ai-rules:
  - Never return raw passwords.
  - Maintain 100% type-hinting coverage.
@dependencies: fastapi, sqlalchemy[asyncio]
@version: 2.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import audit as audit_service
from nebula import users
from nebula.api.endpoint import Endpoint, decode_oidc, get_current_user, verify_nebula_token
from nebula.config import settings
from nebula.database import get_session
from nebula.entitlements import entitlements_for_groups, is_admin
from nebula.models.auth import AuthResponse, LoginRequest, OidcExchangeRequest
from nebula.models.tables import ActorType, UserAccount
from nebula.security import create_access_token, verify_password


class AuthRouter(Endpoint):
    """Public auth endpoints (no gates; validate credentials/tokens internally)."""

    def __init__(self, *args, **kwargs):
        super().__init__(public=True, *args, **kwargs)

        self.add_api_route(
            "/login",
            self.login,
            methods=["POST"],
            response_model=AuthResponse,
            summary="Local username/password login (the optional admin login)",
        )
        self.add_api_route(
            "/oidc",
            self.oidc,
            methods=["POST"],
            response_model=AuthResponse,
            summary="Exchange a snakeNet ID (Authentik) token for a Nebula session",
        )
        self.add_api_route(
            "/logout",
            self.logout,
            methods=["POST"],
            status_code=204,
            dependencies=[Depends(verify_nebula_token)],
            summary="Audit-log a logout (stateless JWTs — nothing server-side to invalidate)",
        )

    @staticmethod
    def _nebula_token() -> str:
        if not settings.nebula_token:
            raise HTTPException(status_code=500, detail="NEBULA_TOKEN is not configured")
        return settings.nebula_token

    async def login(
        self, payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)
    ) -> AuthResponse:
        """Validate the local bootstrap-admin's credentials and mint an HS256 access token."""
        user = await users.get_by_username(session, payload.username)
        if user is None or not verify_password(payload.password, user.password):
            await audit_service.record(
                session,
                actor_type=ActorType.USER,
                actor_id=None,
                actor_label=payload.username,
                action="auth.login",
                success=False,
                detail="Invalid username or password",
                ip_address=request.client.host if request.client else None,
            )
            # Same error for unknown user + bad password (no user enumeration).
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Local accounts carry a synthetic group so they share the OIDC authorisation surface.
        groups = ["nebula-admin"] if user.is_admin else ["nebula-user"]
        entitlements = entitlements_for_groups(groups)
        token = create_access_token(
            str(user.id), name=user.username, email=user.email, groups=groups
        )
        await audit_service.record_user_action(session, user, request, action="auth.login")
        return AuthResponse(
            message="Auth success",
            token=token,
            nebula_token=self._nebula_token(),
            id=str(user.id),
            name=user.username,
            email=user.email,
            groups=groups,
            entitlements=entitlements,
            is_admin=user.is_admin,
        )

    async def oidc(
        self,
        payload: OidcExchangeRequest,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ) -> AuthResponse:
        """Validate the Authentik access token and build the Nebula session payload."""
        claims = decode_oidc(payload.access_token)
        groups = claims.get(settings.oidc_groups_claim, []) or []
        entitlements = entitlements_for_groups(groups)
        admin = is_admin(entitlements)

        user = await users.provision_oidc_user(session, claims, is_admin=admin)
        await audit_service.record_user_action(session, user, request, action="auth.login")

        return AuthResponse(
            message="Auth success",
            # Return the Authentik access token verbatim — protected routes re-validate it.
            token=payload.access_token,
            nebula_token=self._nebula_token(),
            id=str(user.id),
            name=claims.get("name") or claims.get("preferred_username"),
            email=claims.get("email"),
            groups=sorted(groups),
            entitlements=entitlements,
            is_admin=admin,
        )

    async def logout(
        self,
        request: Request,
        actor: UserAccount = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        await audit_service.record_user_action(session, actor, request, action="auth.logout")


router = AuthRouter()
