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
  secret's actual content lives at rest. Since 2026-08-09, a key's value can ALSO be a REFERENCE to
  another SecretKey elsewhere in the vault (`source_key_id`, FK ON DELETE RESTRICT — same shape as
  ProjectGithubSync.pat_source_key_id below, generalized from "a sync target's PAT" to "any key's
  value") — a reference row's own `ciphertext` is always NULL
  (`ck_secret_keys_reference_no_own_value`) and `variable_type`/value are resolved LIVE from the
  referenced key at every read (nebula.secrets.resolve_effective) rather than copied, so rotating the
  source anywhere in the vault is picked up immediately with nothing to re-save on this row. No
  chaining — a key already carrying a `source_key_id` can never itself be referenced (enforced at
  create time, nebula.secrets/api/v1/secret.py, not by the schema). `name`/`description`/
  `environment_id`/`sync_enabled` stay this row's OWN, independently editable metadata regardless of
  reference mode — only the value/type are locked to the source.) — ProjectGithubSync (a Project may
  have MANY simultaneous
  GitHub sync targets since the 2026-08-06 multi-repo redesign — see nebula.github_sync; each row is
  its own repo_url + enabled flag + last-run status, `project_id` FK CASCADE, plus its PAT config).
  Since 2026-08-08, a target's PAT is EITHER a `pat_ciphertext` it owns directly (the "custom" mode,
  unchanged from before) OR a `pat_source_key_id` pointing at a SecretKey elsewhere in the vault (the
  "reference" mode) — exactly one of the two is ever set (`ck_project_github_syncs_pat_xor`, a DB
  CHECK constraint, not just an app-level rule). A reference stores no ciphertext of its own at all;
  nebula.github_sync resolves the live PAT by decrypting the REFERENCED SecretKey's own ciphertext at
  sync time, so rotating that key's value anywhere in the vault automatically updates every sync
  target that references it — no copy to keep in sync. `pat_source_key_id` is `ON DELETE RESTRICT`
  (see nebula.secrets.delete_key's SecretKeyInUseAsPatSourceError) so a key can't be silently deleted
  out from under a sync target that depends on it — same RESTRICT-not-CASCADE reasoning as
  SecretKey.environment_id. —
  ProjectAccessKey (a project-scoped API credential, `token_hash` SHA-256 hex + `token_prefix` for UI
  display — the raw token is returned to the caller exactly once at creation and never stored, same
  opaque-high-entropy-token reasoning as Singularity's M2MAccount) — AuditLogEntry (append-only
  action log — see nebula.audit) — VaultMeta (single-row table, one Fernet-encrypted canary value
  checked at startup — see nebula.crypto's module docstring and main.py's lifespan — to fail fast on
  a wrong NEBULA_MASTER_KEY instead of a confusing per-request 500 later).
  Since 2026-08-12 (later same day), a SecretKey also carries an optional automatic-rotation
  schedule — `rotation_frequency` (a positive int) + `rotation_unit` (RotationUnit: week/month/year)
  — and `last_rotated_at` (when its current value was put in place). See nebula.rotation for the
  due-check/generation logic and scripts/rotate_secrets.py for the hourly process that acts on it.
@ai-rules:
  - `SecretKey.ciphertext`/`ProjectGithubSync.pat_ciphertext` must only ever be written via
    nebula.crypto.encrypt_value and read via nebula.crypto.decrypt_value — never assign/return raw.
  - Never let `pat_ciphertext` and `pat_source_key_id` both be set (or both be unset) on the same
    ProjectGithubSync row — the DB CHECK constraint is a backstop, but nebula.github_sync's own CRUD
    functions must keep them mutually exclusive too.
  - Never let `SecretKey.source_key_id` and `.ciphertext` both be set on the same row (backstopped
    by `ck_secret_keys_reference_no_own_value`, enforced app-side in nebula.secrets) — and never let
    a key that already has a `source_key_id` be picked as ANOTHER key's `source_key_id` (no
    chaining) or as its own (backstopped by `ck_secret_keys_reference_not_self`).
  - Never set `rotation_frequency`/`rotation_unit` on a reference key or a non-SECRET key — see
    nebula.secrets.RotationNotSupportedError.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 6.2.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    github_syncs: Mapped[list["ProjectGithubSync"]] = relationship(
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


class RotationUnit(str, enum.Enum):
    """The cadence unit for a SecretKey's automatic-rotation schedule — see nebula.rotation."""

    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


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
        # A reference row never owns a ciphertext of its own — see source_key_id below — and can
        # never reference itself. Mirrors ck_project_github_syncs_pat_xor's shape, one CHECK per
        # invariant instead of one combined expression for a clearer constraint-violation message.
        CheckConstraint(
            "source_key_id IS NULL OR ciphertext IS NULL",
            name="ck_secret_keys_reference_no_own_value",
        ),
        CheckConstraint(
            "source_key_id IS NULL OR source_key_id <> id",
            name="ck_secret_keys_reference_not_self",
        ),
        # Automatic-rotation schedule (see nebula.rotation) — rotation_frequency/rotation_unit are
        # either both set (rotation enabled) or both null (disabled), never just one.
        CheckConstraint(
            "(rotation_frequency IS NULL) = (rotation_unit IS NULL)",
            name="ck_secret_keys_rotation_pair",
        ),
        CheckConstraint(
            "rotation_frequency IS NULL OR rotation_frequency > 0",
            name="ck_secret_keys_rotation_frequency_positive",
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
    # exist before its value is first set, OR (since 2026-08-09) because it's a reference — see
    # source_key_id below, always NULL together with this column (ck_secret_keys_reference_no_own_value).
    ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "Reference" mode: this key's own value/type are resolved LIVE from the pointed-at SecretKey on
    # every read (nebula.secrets.resolve_effective) instead of stored here — rotating the source
    # anywhere in the vault takes effect immediately, nothing to re-save on this row. RESTRICT (not
    # CASCADE/SET NULL) so deleting a still-referenced key fails loudly rather than silently orphaning
    # every key that points at it. No chaining: a key that itself has source_key_id set may never be
    # picked as another key's source (enforced in nebula.secrets/api/v1/secret.py, not the schema).
    # `name`/`description`/`environment_id`/`sync_enabled` are unaffected — a reference key keeps its
    # own independently-editable identity in THIS project; only the value/type are locked to the
    # source project.
    source_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("secret_keys.id", ondelete="RESTRICT"), nullable=True
    )
    # Per-key on/off toggle for GitHub sync (nebula.github_sync) — a disabled key is skipped by every
    # sync target's push, both the automatic on-change hook and a manual "Sync now". Defaults true so
    # a key behaves exactly as before this column existed unless explicitly turned off.
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Automatic-rotation schedule, secret-only (see nebula.rotation/models/secret.py's validators) —
    # both null means rotation is disabled for this key. scripts/rotate_secrets.py is the hourly
    # process that actually acts on this: once rotation_frequency`d rotation_unit`s have passed since
    # last_rotated_at, it re-generates the value with a fresh random secret and bumps
    # last_rotated_at. Never set on a reference key (source_key_id) — it owns no value of its own to
    # rotate; the SOURCE key is what would carry a schedule instead, in its own Project.
    rotation_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotation_unit: Mapped[RotationUnit | None] = mapped_column(String(5), nullable=True)
    # When the current value was put in place — set at create_key (if a value was given) and at
    # every set_value/automatic rotation. Distinct from `updated_at`, which also moves on a plain
    # rename/description/environment/sync-toggle edit and would otherwise make "time since last
    # rotation" wrong for a key that was merely renamed.
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class ProjectGithubSync(Base):
    """One of possibly MANY simultaneous GitHub sync targets for a Project — see nebula.github_sync.

    Every enabled row for a Project is pushed to on every secret/variable value change (create,
    update, delete, value set, bulk upload), not just when a human clicks "Sync now" — see
    nebula.github_sync.sync_all_for_project, called from every mutating route in api/v1/secret.py.
    """

    __tablename__ = "project_github_syncs"
    __table_args__ = (
        # Exactly one of pat_ciphertext/pat_source_key_id — see nebula.github_sync's CRUD functions,
        # which are the app-level side of this same invariant.
        CheckConstraint(
            "(pat_ciphertext IS NOT NULL) <> (pat_source_key_id IS NOT NULL)",
            name="ck_project_github_syncs_pat_xor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Optional human label (e.g. "production", "staging") — purely cosmetic, never used to resolve
    # the target; falls back to the owner/repo parsed from repo_url when blank (see
    # nebula.github_sync.target_display_name).
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # A Fernet token (nebula.crypto.encrypt_value), same as SecretKey.ciphertext — a PAT is a
    # credential like any other secret and is NEVER returned in an API response. Nullable since
    # 2026-08-08: null whenever pat_source_key_id is set instead (see the class docstring above).
    pat_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "Reference" mode: the PAT is resolved fresh at sync time by decrypting THIS SecretKey's own
    # ciphertext, instead of a copy this row owns — see the class docstring above. RESTRICT (not
    # CASCADE/SET NULL) so deleting a still-referenced key fails loudly rather than silently
    # breaking a sync target's authentication.
    pat_source_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("secret_keys.id", ondelete="RESTRICT"), nullable=True
    )
    # A disabled target is skipped by both the automatic on-change sync and the "Sync all now"
    # button, but can still be triggered individually — lets an admin pause a flaky/retired
    # integration without losing its stored repo_url/PAT.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # gh CLI stderr / a summary count — never a plaintext secret value (see nebula.github_sync).
    last_sync_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # live reference; object_label/project_label already preserve the project's name as text.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # The resolved Project's name, captured at write time same as actor_label/object_label —
    # backs the "API calls" tab's Project column without a live join through project_id.
    project_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
