#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Password hashing + local session-JWT minting/decoding for the optional admin login.
@ai-context: Nebular accepts two kinds of bearer JWT on protected routes (see api/endpoint.py): RS256
  tokens issued by Authentik (id.snakenet.io, validated against its JWKS) and HS256 tokens Nebular
  itself mints from local username/password login (POST /api/v1/auth/login — the "optional admin
  login" alongside Authentik). This module owns the local side: bcrypt password hashing/verification
  and HS256 access-token creation/validation, mirroring Satellite's security.py exactly.
@ai-rules:
  - Never return or log raw passwords or the signing secret.
  - Locally minted tokens always carry alg=HS256 so the verifier can tell them apart from Authentik's
    RS256 tokens purely from the JWT header.
  - Maintain 100% type-hinting coverage.
@dependencies: bcrypt, pyjwt
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import time

import bcrypt
import jwt

from nebular.config import settings

# `iss` stamped onto locally minted tokens (lets us distinguish them in logs / future audiences).
LOCAL_ISSUER = "nebular-local"


def hash_password(plain: str) -> str:
    """Return a bcrypt hash (utf-8 string) for a plaintext password."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check of a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy hash — treat as a non-match rather than erroring.
        return False


def create_access_token(subject: str, *, name: str, email: str | None, groups: list[str]) -> str:
    """Mint an HS256 access token for a locally authenticated user.

    `subject` is the Nebular user id. `groups` lets local users share the same group-based
    authorisation surface as Authentik users (see nebular.entitlements/api/endpoint.py).
    """
    if not settings.jwt_secret:
        raise RuntimeError("NEBULAR_JWT_SECRET is not configured")

    now = int(time.time())
    payload = {
        "sub": subject,
        "name": name,
        "email": email,
        "groups": groups,
        "iss": LOCAL_ISSUER,
        "iat": now,
        "exp": now + settings.jwt_ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_local_token(token: str) -> dict:
    """Validate a locally minted HS256 token and return its claims (raises jwt.PyJWTError)."""
    if not settings.jwt_secret:
        raise RuntimeError("NEBULAR_JWT_SECRET is not configured")
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=LOCAL_ISSUER)
