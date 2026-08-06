#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: SQLAlchemy ORM table definitions — the whole Nebular schema in one module.
@ai-context: UserAccount (local + Authentik-provisioned identities) — Project (owner_id FK, the
  creator) — ProjectShare (composite PK project_id+user_id, ShareRole VIEWER/EDITOR, both FKs CASCADE
  — see nebular.projects for the can_view/can_edit/can_reveal permission matrix built on top of
  ownership + this table) — Environment (GLOBAL, not project-scoped — a shared taxonomy of
  environment names/descriptions any project's keys can be linked to, name unique case-insensitively
  app-wide via uq_environments_name_lower) — SecretKey (project-scoped, cleartext name, unique
  case-insensitively per project via uq_secret_keys_project_name_lower — the key/variable name a
  caller passes to api/v1/vault.py; carries its OWN `ciphertext` directly and a required
  `environment_id` — every key/value pair is linked to exactly one Environment, reassignable via
  nebular.secrets.update_key, never many-at-once — `ciphertext` is a Fernet token from
  nebular.crypto.encrypt_value, nullable only because a key can exist before its value is first set;
  NEVER store a plaintext value anywhere, this column and its ORM attribute are the only place a
  secret's actual content lives at rest) — ProjectAccessKey (a project-scoped API credential,
  `token_hash` SHA-256 hex + `token_prefix` for UI display — the raw token is returned to the caller
  exactly once at creation and never stored, same opaque-high-entropy-token reasoning as
  Singularity's M2MAccount) — AuditLogEntry (append-only action log — see nebular.audit) —
  VaultMeta (single-row table, one Fernet-encrypted canary value checked at startup — see
  nebular.crypto's module docstring and main.py's lifespan — to fail fast on a wrong
  NEBULAR_MASTER_KEY instead of a confusing per-request 500 later).
@ai-rules:
  - `SecretKey.ciphertext` must only ever be written via nebular.crypto.encrypt_value and read via
    nebular.crypto.decrypt_value — never assign/return it raw.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 2.0.0
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

from nebular.database import Base


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
    # bcrypt hash; an OIDC-provisioned user gets an unusable sentinel (see nebular.users) so they can
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
    # Every key/value pair is linked to exactly one Environment — reassignable (nebular.secrets.
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
    # A Fernet token (nebular.crypto.encrypt_value) — never a plaintext value. Nullable: a key can
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
    """Single-row table — a Fernet-encrypted canary checked at startup (see nebular.crypto)."""

    __tablename__ = "vault_meta"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    canary_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
