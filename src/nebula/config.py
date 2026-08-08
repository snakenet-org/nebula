#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Central, typed configuration loaded once from the environment / .env.
@ai-context: Every other module reads settings from the `settings` singleton built here instead of
  calling os.getenv directly, mirroring Gravity/Satellite/Singularity's own config.py convention.
  Groups the server (incl. log_level), the X-Nebula-Token shared secret, the master encryption key
  (master_key — see nebula.crypto, REQUIRED, no default; `require_master_key()` raises a clear
  RuntimeError rather than letting a missing key surface later as a confusing decrypt failure), the
  locally minted HS256 session JWT (username/password login — the "optional admin login"), snakeNet
  ID (Authentik) OIDC parameters, and PostgreSQL. Derived values (the async asyncpg DB URL, the
  Authentik authorize/token/end-session endpoints) are exposed as computed properties so callers
  never re-assemble them. Loaded at import time; `load_dotenv()` runs first so a local .env wins.
@ai-rules:
  - Never log secret fields (nebula_token, master_key, jwt_secret, db password).
  - Read config ONLY through `settings`; do not scatter os.getenv across the codebase.
  - Maintain 100% type-hinting coverage.
@dependencies: python-dotenv
@version: 1.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-09
"""

import os
from dataclasses import dataclass, field
from functools import cached_property

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    """Interpret a NEBULA_* flag: 'yes'/'true'/'1'/'on' → True (case-insensitive)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"yes", "true", "1", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the process configuration."""

    # ── Server ──────────────────────────────────────────────────────────────
    host: str = field(default_factory=lambda: os.getenv("NEBULA_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("NEBULA_PORT", "8000")))
    dev: bool = field(default_factory=lambda: _bool("NEBULA_DEV", False))
    log_level: str = field(
        default_factory=lambda: (
            os.getenv("NEBULA_LOG_LEVEL", "").strip().upper()
            or ("DEBUG" if _bool("NEBULA_DEV", False) else "ERROR")
        )
    )

    # ── X-Nebula-Token (shared API service secret, required on every non-public route) ────
    nebula_token: str = field(default_factory=lambda: os.getenv("NEBULA_TOKEN", ""))

    # ── Master encryption key (see nebula.crypto) — REQUIRED, no safe default ──────────────
    master_key: str = field(default_factory=lambda: os.getenv("NEBULA_MASTER_KEY", ""))

    # ── Local username/password login (HS256 session tokens — the optional admin login) ────
    jwt_secret: str = field(default_factory=lambda: os.getenv("NEBULA_JWT_SECRET", ""))
    jwt_ttl: int = field(default_factory=lambda: int(os.getenv("NEBULA_JWT_TTL", "3600")))
    # How long past its own `exp` a local token may still be silently refreshed (POST
    # /api/v1/auth/refresh) instead of forcing a full re-login — covers a backgrounded/frozen tab
    # that missed its proactive refresh, mirroring the same class of gap Gravity's own idle-TTL
    # journal entry documents for the browser-timer-vs-frozen-tab case.
    jwt_refresh_grace: int = field(
        default_factory=lambda: int(os.getenv("NEBULA_JWT_REFRESH_GRACE", "900"))
    )
    admin_user: str = field(default_factory=lambda: os.getenv("NEBULA_ADMIN_USER", ""))
    admin_pass: str = field(default_factory=lambda: os.getenv("NEBULA_ADMIN_PASS", ""))
    admin_email: str = field(default_factory=lambda: os.getenv("NEBULA_ADMIN_EMAIL", ""))

    # ── snakeNet ID (Authentik OIDC) ────────────────────────────────────────
    oidc_authority: str = field(
        default_factory=lambda: os.getenv("NEBULA_OIDC_AUTHORITY", "https://id.snakenet.io")
    )
    oidc_application_slug: str = field(
        default_factory=lambda: os.getenv("NEBULA_OIDC_APPLICATION_SLUG", "nebula")
    )
    oidc_client_id: str = field(default_factory=lambda: os.getenv("NEBULA_OIDC_CLIENT_ID", ""))
    oidc_jwks_url: str = field(default_factory=lambda: os.getenv("NEBULA_OIDC_JWKS_URL", ""))
    oidc_issuer: str = field(default_factory=lambda: os.getenv("NEBULA_OIDC_ISSUER", ""))
    oidc_audience: str = field(default_factory=lambda: os.getenv("NEBULA_OIDC_AUDIENCE", ""))
    oidc_groups_claim: str = field(
        default_factory=lambda: os.getenv("NEBULA_OIDC_GROUPS_CLAIM", "groups")
    )
    basic_login_disabled: bool = field(
        default_factory=lambda: _bool("NEBULA_BASIC_LOGIN_DISABLED", False)
    )
    oidc_login_disabled: bool = field(
        default_factory=lambda: _bool("NEBULA_OIDC_LOGIN_DISABLED", True)
    )
    oidc_login_caption: str = field(
        default_factory=lambda: os.getenv("NEBULA_OIDC_LOGIN_CAPTION", "Sign in with snakeNet ID")
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    pg_host: str = field(default_factory=lambda: os.getenv("NEBULA_POSTGRES_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: int(os.getenv("NEBULA_POSTGRES_PORT", "5432")))
    pg_db: str = field(default_factory=lambda: os.getenv("NEBULA_POSTGRES_DB", "nebula"))
    pg_user: str = field(default_factory=lambda: os.getenv("NEBULA_POSTGRES_USER", "postgres"))
    pg_password: str = field(
        default_factory=lambda: os.getenv("NEBULA_POSTGRES_PASSWORD", "")
    )

    # ── Data folder (the embedded Postgres data directory lives under here) ─────────────────
    data_folder: str = field(
        default_factory=lambda: os.getenv("NEBULA_DATA_FOLDER", "") or "/data"
    )

    # ── Derived values ────────────────────────────────────────────────────────
    @cached_property
    def database_url(self) -> str:
        """Async SQLAlchemy URL (asyncpg driver) built from the NEBULA_POSTGRES_* vars."""
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def oidc_authorize_endpoint(self) -> str:
        return f"{self.oidc_authority}/application/o/authorize/"

    @property
    def oidc_token_endpoint(self) -> str:
        return f"{self.oidc_authority}/application/o/token/"

    @property
    def oidc_end_session_endpoint(self) -> str:
        return f"{self.oidc_authority}/application/o/{self.oidc_application_slug}/end-session/"

    def require_master_key(self) -> str:
        """Return NEBULA_MASTER_KEY or raise — the one setting with no safe default.

        Called by nebula.crypto on first use rather than at Settings construction time, so
        importing this module (e.g. for `alembic` autogenerate, which never encrypts anything)
        never fails just because the env var isn't set yet.
        """
        if not self.master_key:
            raise RuntimeError(
                "NEBULA_MASTER_KEY is not configured — Nebula Vault refuses to encrypt or "
                "decrypt secret values without it. Set it before starting the app."
            )
        return self.master_key


# Singleton read by the rest of the app.
settings = Settings()
