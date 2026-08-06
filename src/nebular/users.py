#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: User provisioning shared by both login paths (local + Authentik OIDC).
@ai-context: Mirrors Satellite's api/v1/auth.py provisioning helpers, centralized here instead of
  inlined in the router (matching Gravity's users.py convention of one shared provisioning module
  behind both surfaces). provision_oidc_user upserts by `sub` on every login (so a later Authentik
  group change is picked up immediately — is_admin is recomputed every call, never sticky from
  first login). New OIDC users get UNUSABLE_PASSWORD so they can never authenticate via the local
  login path. get_by_username/get_by_id are the lookups nebular.projects/secrets/access_keys use to
  resolve an actor.
@ai-rules:
  - Never return or log raw passwords.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nebular.models.tables import UserAccount

# Stored as the password of auto-provisioned OIDC users. Not a valid bcrypt hash, so
# security.verify_password can never match it — these users can only ever sign in via OIDC.
UNUSABLE_PASSWORD = "!"


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> UserAccount | None:
    return await session.get(UserAccount, user_id)


async def get_by_username(session: AsyncSession, username: str) -> UserAccount | None:
    result = await session.execute(
        select(UserAccount).where(UserAccount.username == username)
    )
    return result.scalar_one_or_none()


async def get_by_sub(session: AsyncSession, sub: str) -> UserAccount | None:
    result = await session.execute(select(UserAccount).where(UserAccount.sub == sub))
    return result.scalar_one_or_none()


async def provision_oidc_user(session: AsyncSession, claims: dict, is_admin: bool) -> UserAccount:
    """Upsert a UserAccount from validated Authentik claims (idempotent, keyed by `sub`).

    is_admin is recomputed and rewritten on every call so a group change in Authentik takes effect
    on the caller's next login rather than sticking at whatever was granted on first sign-in.
    """
    sub = claims.get("sub")
    if not sub:
        raise ValueError("OIDC claims missing 'sub'")

    username = claims.get("preferred_username") or claims.get("email") or sub
    email = claims.get("email")

    user = await get_by_sub(session, sub)
    if user is not None:
        user.is_admin = is_admin
        if email:
            user.email = email
        await session.commit()
        return user

    user = UserAccount(
        sub=sub,
        username=username,
        email=email,
        password=UNUSABLE_PASSWORD,
        is_admin=is_admin,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Lost a race with a concurrent first-login for the same sub/username.
        await session.rollback()
        user = await get_by_sub(session, sub)
        if user is None:
            raise
    return user
