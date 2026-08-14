#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Pydantic request/response models for api/v1/system.py — the admin-only System Settings
  danger zones (reset all data, reset logs, export vault, import vault).
@ai-context: VaultExport is the one shape shared by BOTH directions — GET /system/export returns it,
  POST /system/import accepts the exact same shape as its request body, so a downloaded export file
  can be re-uploaded verbatim. `format` is a required Literal (not a defaulted field) specifically so
  a caller who POSTs some unrelated JSON file gets a clean 422 from Pydantic itself rather than
  import_vault silently misinterpreting it.
  Deliberately OUT OF SCOPE for export/import (see nebula.vault_transfer's module docstring for the
  full reasoning): ProjectShare (ownership is reassigned to the importer anyway — see below),
  ProjectAccessKey (only a token HASH is ever stored, the raw token can't be recovered to export),
  ProjectGithubSync (external-repo PATs tied to a specific outside system, not vault content).
  VaultExportKey mirrors nebula.secrets' shape closely: `value` is the DECRYPTED plaintext (null for
  an unset key OR a reference key — see `is_reference`), `environment_name` (not an id, which
  wouldn't survive a round-trip to a different Nebula instance) resolves against VaultExport.
  environments by case-insensitive name on import. A reference key (SecretKey.source_key_id) is
  exported as a pointer INTO THIS SAME EXPORT FILE — `reference_project_index` (0-based, into
  VaultExport.projects) + `reference_key_name` — since the referenced key's real id won't survive the
  round-trip either; nebula.vault_transfer.import_vault resolves it in a second pass after every
  plain key has already been (re)created with a fresh id.
  Import always creates BRAND NEW Projects (never merges into an existing one, and Project.name
  carries no uniqueness constraint at all — see models/tables.py — so a same-named Project can
  coexist) owned by the importing admin, per explicit product spec ("assign ownership of them all to
  the user that does the import").
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-13
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from nebula.models.tables import RotationUnit, VariableType

VAULT_EXPORT_FORMAT: Literal["nebula-vault-export"] = "nebula-vault-export"


class VaultExportEnvironment(BaseModel):
    name: str
    description: str | None = None


class VaultExportKey(BaseModel):
    name: str
    description: str | None = None
    environment_name: str
    variable_type: VariableType
    sync_enabled: bool = True
    # Decrypted plaintext — null for an unset key or a reference key (is_reference below).
    value: str | None = None
    is_reference: bool = False
    # Only set when is_reference is True — see the module docstring for how this resolves.
    reference_project_index: int | None = None
    reference_key_name: str | None = None
    rotation_frequency: int | None = None
    rotation_unit: RotationUnit | None = None


class VaultExportProject(BaseModel):
    name: str
    description: str | None = None
    keys: list[VaultExportKey] = []


class VaultExport(BaseModel):
    format: Literal["nebula-vault-export"]
    version: int = 1
    exported_at: datetime
    environments: list[VaultExportEnvironment] = []
    projects: list[VaultExportProject] = []


class VaultImportSummary(BaseModel):
    environments_created: int
    environments_reused: int
    projects_created: int
    keys_created: int
    references_resolved: int
    references_skipped: int


class SystemResetSummary(BaseModel):
    """Backs both POST /system/reset-data (full counts) and POST /system/reset-logs
    (audit_logs only, the other two counts always 0) — one shape for both so the frontend has a
    single response type to render regardless of which danger zone was triggered."""

    projects_deleted: int = 0
    environments_deleted: int = 0
    audit_logs_deleted: int = 0
