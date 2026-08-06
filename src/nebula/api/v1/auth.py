#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Public auth endpoints — local login (the optional admin login) + snakeNet ID exchange.
@ai-context: This router is PUBLIC (no gates); each handler validates credentials/tokens itself.
  POST /api/v1/auth/login — verify the local bootstrap-admin username/password, mint a Nebular
    HS256 token. Only meaningful when NEBULAR_BASIC_LOGIN_DISABLED is unset/no.
  POST /api/v1/auth/oidc — the frontend completes the Authentik Authorization-Code + PKCE flow
    against id.snakenet.io, then posts the resulting access token here; Nebular validates it against
    Authentik's JWKS and reuses it as the bearer (Nebular mints nothing for OIDC). Auto-provisions
    the user via nebular.users.provision_oidc_user on every call (idempotent, keeps is_admin fresh).
  Both return an AuthResponse carrying the bearer token + the X-Nebular-Token shared secret the
  frontend must echo on subsequent calls, plus the resolved identity/entitlements.
  POST /api/v1/auth/logout — JWT-gated (unlike the two routes above) purely so it can attribute a
  nebular.audit "auth.logout" row to the caller; Nebular mints stateless JWTs it never tracks
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

from nebular import audit as audit_service
from nebular import users
from nebular.api.endpoint import Endpoint, decode_oidc, get_current_user, verify_nebular_token
from nebular.config import settings
from nebular.database import get_session
from nebular.entitlements import entitlements_for_groups, is_admin
from nebular.models.auth import AuthResponse, LoginRequest, OidcExchangeRequest
from nebular.models.tables import ActorType, UserAccount
from nebular.security import create_access_token, verify_password


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
            summary="Exchange a snakeNet ID (Authentik) token for a Nebular session",
        )
        self.add_api_route(
            "/logout",
            self.logout,
            methods=["POST"],
            status_code=204,
            dependencies=[Depends(verify_nebular_token)],
            summary="Audit-log a logout (stateless JWTs — nothing server-side to invalidate)",
        )

    @staticmethod
    def _nebular_token() -> str:
        if not settings.nebular_token:
            raise HTTPException(status_code=500, detail="NEBULAR_TOKEN is not configured")
        return settings.nebular_token

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
        groups = ["nebular-admin"] if user.is_admin else ["nebular-user"]
        entitlements = entitlements_for_groups(groups)
        token = create_access_token(
            str(user.id), name=user.username, email=user.email, groups=groups
        )
        await audit_service.record_user_action(session, user, request, action="auth.login")
        return AuthResponse(
            message="Auth success",
            token=token,
            nebular_token=self._nebular_token(),
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
        """Validate the Authentik access token and build the Nebular session payload."""
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
            nebular_token=self._nebular_token(),
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
