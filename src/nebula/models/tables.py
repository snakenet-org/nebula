#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SQLAlchemy ORM table definitions — the whole Nebula schema in one module.
@ai-context: UserAccount (local + Authentik-provisioned identities) — Project (owner_id FK, the
  creator) — ProjectShare (composite PK project_id+user_id, ShareRole VIEWER/EDITOR, both FKs CASCADE
  — see nebula.projects for the can_view/can_edit/can_reveal permission matrix built on top of
  ownership + this table) — Environment (GLOBAL, not project-scoped — a shared taxonomy of
  environment names/descriptions any project's keys can be linked to, name unique case-insensitively
  app-wide via uq_environments_name_lower) — SecretKey (project-scoped, cleartext name, unique
  case-insensitively per project via uq_secret_keys_project_name_lower — the key/variable name a
  caller passes to api/v1/vault.py; carries its OWN `ciphertext` directly and a required
  `environment_id` — every key/value pair is linked to exactly one Environment, reassignable via
  nebula.secrets.update_key, never many-at-once — `ciphertext` is a Fernet token from
  nebula.crypto.encrypt_value, nullable only because a key can exist before its value is first set;
  NEVER store a plaintext value anywhere, this column and its ORM attribute are the only place a
  secret's actual content lives at rest) — ProjectAccessKey (a project-scoped API credential,
  `token_hash` SHA-256 hex + `token_prefix` for UI display — the raw token is returned to the caller
  exactly once at creation and never stored, same opaque-high-entropy-token reasoning as
  Singularity's M2MAccount) — AuditLogEntry (append-only action log — see nebula.audit) —
  VaultMeta (single-row table, one Fernet-encrypted canary value checked at startup — see
  nebula.crypto's module docstring and main.py's lifespan — to fail fast on a wrong
  NEBULA_MASTER_KEY instead of a confusing per-request 500 later).
@ai-rules:
  - `SecretKey.ciphertext` must only ever be written via nebula.crypto.encrypt_value and read via
    nebula.crypto.decrypt_value — never assign/return it raw.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 3.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nebula.database import Base


class ShareRole(str, enum.Enum):
    VIEWER = "viewer"
    EDITOR = "editor"


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Authentik `sub` — null for the local bootstrap admin (never assigned one).
    sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # bcrypt hash; an OIDC-provisioned user gets an unusable sentinel (see nebula.users) so they can
    # never authenticate via the local login path.
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # GitHub sync (see nebula.github_sync) — both optional, set together via
    # github_sync.update_github_config. github_pat_ciphertext is a Fernet token
    # (nebula.crypto.encrypt_value), same as SecretKey.ciphertext — a PAT is a credential like any
    # other secret and is NEVER returned in an API response, only a `github_connected` bool.
    github_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_pat_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    secret_keys: Mapped[list["SecretKey"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    shares: Mapped[list["ProjectShare"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    access_keys: Mapped[list["ProjectAccessKey"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectShare(Base):
    __tablename__ = "project_shares"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ShareRole] = mapped_column(
        String(10), default=ShareRole.VIEWER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VariableType(str, enum.Enum):
    ENVIRONMENT = "environment"
    SECRET = "secret"


class Environment(Base):
    """Global — NOT project-scoped. A shared taxonomy any project's SecretKeys link into."""

    __tablename__ = "environments"
    __table_args__ = (
        Index("uq_environments_name_lower", text("lower(name)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SecretKey(Base):
    __tablename__ = "secret_keys"
    __table_args__ = (
        Index(
            "uq_secret_keys_project_name_lower",
            "project_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # Every key/value pair is linked to exactly one Environment — reassignable (nebula.secrets.
    # update_key) but never unset or multi-valued. RESTRICT (not CASCADE) so deleting a still-in-use
    # global Environment fails loudly instead of silently wiping keys across every project.
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    variable_type: Mapped[VariableType] = mapped_column(
        String(11), default=VariableType.SECRET, nullable=False
    )
    # A Fernet token (nebula.crypto.encrypt_value) — never a plaintext value. Nullable: a key can
    # exist before its value is first set.
    ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ProjectAccessKey(Base):
    __tablename__ = "project_access_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class VaultMeta(Base):
    """Single-row table — a Fernet-encrypted canary checked at startup (see nebula.crypto)."""

    __tablename__ = "vault_meta"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    canary_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)


class ActorType(str, enum.Enum):
    USER = "user"
    ACCESS_KEY = "access_key"


class AuditLogEntry(Base):
    """Append-only action log — see nebula.audit. Never edited or deleted, only inserted."""

    __tablename__ = "audit_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actor_type: Mapped[ActorType] = mapped_column(String(11), nullable=False)
    # Loose reference (no FK) — an actor (UserAccount or ProjectAccessKey) may later be deleted, but
    # the audit trail must survive that. actor_label is captured at write time for the same reason.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    object_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SET NULL (not CASCADE) — deleting a Project must not erase its audit history, only detach the
    # live reference; object_label already preserves the project's name as text.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
