#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Built-in MCP (Model Context Protocol) server exposing the vault to LLM clients —
  mounted at GET/POST /mcp by main.py.
@ai-context: A FastMCP server (streamable-HTTP transport) giving an MCP-speaking model the ability
  to read, find, and change secrets/environment variables/certificates — the same data
  api/v1/vault.py already exposes over plain REST for machine callers, just on a second transport.

  **Auth**: the presented bearer token is one or more `nbv_...` Project access keys
  (nebula.access_keys — the exact same credential api/v1/vault.py accepts), comma-separated when
  there's more than one ("nbv_aaa...,nbv_bbb..."). This is the one deliberate departure from
  vault.py's own auth shape: a ProjectAccessKey has always resolved to exactly one Project, so
  letting a single MCP connection carry SEVERAL of them is what makes "one MCP server, access to
  several specific Projects" possible without a separate server entry (and a separate bearer token)
  per Project. ProjectAccessKeyTokenVerifier resolves every comma-separated segment and rejects the
  WHOLE token (fail-closed) unless every single one resolves to a live, non-revoked key — a caller
  must never be left believing it was granted N Projects' worth of access when only M<N keys
  actually resolved. Does NOT also gate on X-Nebula-Token — same reasoning api/v1/vault.py's own
  module docstring already gives for its three GET routes: a caller presenting a valid project
  access key has already proven it holds a real credential for this instance, and most MCP clients
  have no first-class way to attach a second static header alongside a bearer token anyway.

  AccessToken.claims["grants"] carries one {project_id, project_name, access_key_id,
  access_key_label} dict per resolved key. Every tool below takes a `project` argument (a Project
  NAME, matched case-insensitively — never a raw UUID; the same "a machine caller only ever knows
  human-readable names" convention api/v1/vault.py already follows) and resolves it against ONLY
  this session's own grants via `_resolve_grant` — never a bare id/name pulled from anywhere else —
  then attributes its own audit-log row to that Project's specific access key, exactly like a plain
  vault.py call would if that key were used there directly instead.

  **Tools**: `list_projects`/`list_environments` are pure discovery (no audit row — nothing
  project-specific happened) so a caller/model can learn valid `project`/`environment` names before
  calling anything else. `find_secrets` is the "finding a secret/variable/certificate" tool — lists
  a Project's keys (optionally filtered by a name/description substring, variable_type, or
  Environment) and NEVER returns a secret or certificate's plaintext, only metadata; an environment
  variable's value IS included unmasked, exactly like Nebula's own UI (nebula.secrets/api/v1/
  secret.py's `_to_response` — "environment" values are never anonymized). `read_secret` is the
  "reading" tool — resolves (Project, Environment, key) and reveals its plaintext, transparently
  following a reference key to its source's current value via resolve_effective, exactly like
  nebula.secrets.reveal_value's every other caller. `set_secret_value` is the "changing" tool — the
  MCP-surface twin of api/v1/vault.py's `PUT /secret`: changes an EXISTING key's value only (never
  creates one), refuses a reference key (its value can only change in its source Project), passes
  its rotation schedule through UNCHANGED (this tool has no concept of a schedule to offer — see
  nebula.secrets.set_value's own docstring for why that's a full-replace everywhere else), and fans
  out to every enabled GitHub sync target afterward, best-effort, via the same
  nebula.github_sync.sync_all_for_project every other value-changing surface in this app already
  calls.

  **Audit logging**: `find_secrets`/`read_secret`/`set_secret_value` each write one
  nebula.audit.record_access_key_action row per call ("mcp.search"/"mcp.read"/"mcp.update"),
  success or failure — same standing "every mutating action is audited" rule this app's CLAUDE.md
  has followed since 2026-08-06, extended here (like api/v1/vault.py before it) to reads too, since
  this is the same machine-credential surface. These rows show up in the Audit Logs page's existing
  "API calls" tab for free (list_api_calls filters only on ActorType.ACCESS_KEY, no action
  allowlist) — but are deliberately NOT added to nebula.audit.VAULT_ACTIONS, since that tuple is
  documented as enumerating api/v1/vault.py's OWN route actions specifically (consumed by
  list_failed_retrievals and the Dashboard's vault-specific "API requests/day"/"Failed attempts/day"
  charts) — conflating a second transport into it would make that name a lie. "mcp.read" IS added to
  EXTRACTION_ACTIONS (a value genuinely left the vault), so it counts toward a key's
  extraction_count exactly like "secret.reveal"/"vault.retrieve" already do.
@ai-rules:
  - Every tool must open (and let __aexit__ close) its own AsyncSession — never share one across
    calls, same rule Satellite/Singularity's own mcp_server.py already follow.
  - Never log or return a plaintext access key; verify_token only ever echoes back the token it was
    given (required by the AccessToken shape), not a new one.
  - A `project` argument must always be resolved through _resolve_grant — never trust a Project
    name/id the caller wasn't already granted via the presented access key(s).
  - Never return a secret/certificate's plaintext from find_secrets — only read_secret may.
  - Maintain 100% type-hinting coverage.
@dependencies: fastmcp, sqlalchemy[asyncio], loguru
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-28
"""

import uuid

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token, get_http_request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import access_keys as access_keys_service
from nebula import audit as audit_service
from nebula import environments as environments_service
from nebula import github_sync as github_sync_service
from nebula import secrets as secrets_service
from nebula.database import async_session_factory
from nebula.models.tables import Project, SecretKey, VariableType


class ProjectAccessKeyTokenVerifier(TokenVerifier):
    """Authenticates MCP bearer credentials against one or more Nebula project access keys — see
    the module docstring for the comma-separated, fail-closed multi-key shape."""

    async def verify_token(self, token: str) -> AccessToken | None:
        raw_tokens = [segment.strip() for segment in token.split(",") if segment.strip()]
        if not raw_tokens:
            return None

        grants: list[dict[str, str]] = []
        async with async_session_factory() as session:
            for raw_token in raw_tokens:
                resolved = await access_keys_service.resolve_access_key(session, raw_token)
                if resolved is None:
                    return None
                project, access_key = resolved
                grants.append(
                    {
                        "project_id": str(project.id),
                        "project_name": project.name,
                        "access_key_id": str(access_key.id),
                        "access_key_label": access_key.name,
                    }
                )

        return AccessToken(
            token=token,
            client_id=",".join(grant["access_key_id"] for grant in grants),
            scopes=["vault"],
            claims={"grants": grants},
        )


mcp: FastMCP = FastMCP(
    name="Nebula Vault",
    instructions=(
        "Tools for reading, finding, and changing secrets, environment variables, and certificates "
        "stored in Nebula Vault, scoped to whichever Project(s) the presented access key(s) grant "
        "access to. Call list_projects first if you don't already know which Project name to pass, "
        "and list_environments if you don't already know which Environment name to pass. "
        "find_secrets never returns a secret or certificate's plaintext (only its metadata, plus an "
        "environment variable's value which is never masked) — call read_secret for that. "
        "set_secret_value changes an EXISTING key's value only; it never creates a new key."
    ),
    auth=ProjectAccessKeyTokenVerifier(),
)


def _current_grants() -> list[dict[str, str]]:
    access_token = get_access_token()
    if access_token is None:
        raise ToolError("Not authenticated")
    return access_token.claims["grants"]


def _current_request():
    """Best-effort Starlette Request for the audit trail's ip_address column — see
    nebula.audit.record. None outside of a real HTTP request, which in practice never happens here
    (ProjectAccessKeyTokenVerifier already rejects anything unauthenticated before a tool runs)."""
    try:
        return get_http_request()
    except RuntimeError:
        return None


async def _resolve_grant(project: str) -> dict[str, str]:
    """Resolve `project` (a Project name, case-insensitive) against THIS session's own grants —
    never a raw id/name the caller wasn't already handed. Raises ToolError naming every Project
    actually accessible if `project` doesn't match one of them."""
    grants = _current_grants()
    needle = project.strip().lower()
    for grant in grants:
        if grant["project_name"].lower() == needle:
            return grant
    accessible = ", ".join(sorted(grant["project_name"] for grant in grants)) or "(none)"
    raise ToolError(
        f"Project '{project}' is not accessible via the presented access key(s). "
        f"Accessible projects: {accessible}"
    )


async def _resolve_project_row(session: AsyncSession, grant: dict[str, str]) -> Project:
    project = await session.get(Project, uuid.UUID(grant["project_id"]))
    if project is None:
        raise ToolError(f"Project '{grant['project_name']}' no longer exists")
    return project


async def _audit(
    session: AsyncSession,
    grant: dict[str, str],
    *,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    success: bool,
    detail: str | None = None,
) -> None:
    await audit_service.record_access_key_action(
        session,
        access_key_id=uuid.UUID(grant["access_key_id"]),
        access_key_label=grant["access_key_label"],
        request=_current_request(),
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=uuid.UUID(grant["project_id"]),
        project_label=grant["project_name"],
        success=success,
        detail=detail,
    )


async def _auto_sync_github(
    session: AsyncSession, grant: dict[str, str], project_id: uuid.UUID
) -> None:
    """Best-effort fan-out to every enabled GitHub sync target after set_secret_value changes a
    value — identical shape/reasoning to api/v1/vault.py's own _auto_sync_github, attributed to
    whichever access key granted this MCP session access to the Project. Never raises."""
    try:
        results = await github_sync_service.sync_all_for_project(session, project_id)
    except Exception:
        logger.exception("Auto GitHub sync crashed for project {}", project_id)
        return
    for result in results:
        detail = result["error"] or (
            f"{result['secrets_synced']} secret(s), {result['variables_synced']} variable(s) across "
            f"{result['environments_synced']} environment(s)"
            + (f"; {len(result['failures'])} failure(s)" if result["failures"] else "")
        )
        await _audit(
            session,
            grant,
            action="github_sync_target.sync",
            object_type="project_github_sync",
            object_id=result["target_id"],
            object_label=result["name"],
            success=result["success"],
            detail=f"Auto-sync on value change (via MCP): {detail}",
        )


async def _key_summary(session: AsyncSession, project_name: str, key: SecretKey) -> dict:
    """find_secrets' per-key response shape — metadata only, plus an ENVIRONMENT-type key's own
    (never-anonymized) value, mirroring api/v1/secret.py's `_to_response`."""
    environment = await environments_service.get_environment(session, key.environment_id)
    # VariableType is stored as a plain String column, not a SQLAlchemy Enum type — after any DB
    # round-trip (including the refresh inside create_key/set_value) it comes back as a bare `str`,
    # not a VariableType instance, so `.value` below would raise without this coercion. Same class
    # of gotcha this codebase's CLAUDE.md already documents for ProjectShare.role; harmless
    # everywhere else in the app since every other caller only ever compares it with `==` (which
    # works on the raw string, since VariableType subclasses str) rather than reading `.value`.
    variable_type, ciphertext = await secrets_service.resolve_effective(session, key)
    variable_type = VariableType(variable_type)

    value: str | None = None
    if variable_type == VariableType.ENVIRONMENT and ciphertext is not None:
        value = await secrets_service.reveal_value(session, key)

    source_label: str | None = None
    if key.source_key_id is not None:
        source_key = await secrets_service.get_key_by_id(session, key.source_key_id)
        if source_key is not None:
            source_project = await session.get(Project, source_key.project_id)
            if source_project is not None:
                source_label = f"{source_project.name} / {source_key.name}"

    return {
        "project": project_name,
        "key": key.name,
        "description": key.description,
        "variable_type": variable_type.value,
        "environment": environment.name,
        "is_set": ciphertext is not None,
        "sync_enabled": key.sync_enabled,
        "is_reference": key.source_key_id is not None,
        "source": source_label,
        "value": value,
    }


# ── Discovery ─────────────────────────────────────────────────────────────────
@mcp.tool
async def list_projects() -> list[dict]:
    """List every Project reachable via the presented access key(s) — call this first if you don't
    already know which Project name to pass to find_secrets/read_secret/set_secret_value."""
    grants = _current_grants()
    async with async_session_factory() as session:
        results = []
        for grant in grants:
            project = await session.get(Project, uuid.UUID(grant["project_id"]))
            if project is not None:
                results.append({"project": project.name, "description": project.description})
        return results


@mcp.tool
async def list_environments() -> list[dict]:
    """List every Environment defined in this Nebula Vault instance — Environments are a shared,
    global taxonomy, not scoped to any one Project. Call this if you don't already know which
    Environment name to pass to find_secrets/read_secret/set_secret_value."""
    async with async_session_factory() as session:
        environments = await environments_service.list_environments(session)
        return [{"environment": e.name, "description": e.description} for e in environments]


# ── Finding ───────────────────────────────────────────────────────────────────
@mcp.tool
async def find_secrets(
    project: str,
    query: str | None = None,
    variable_type: str | None = None,
    environment: str | None = None,
) -> list[dict]:
    """Search/list the secrets, environment variables, and certificates in one Project (by name —
    call list_projects first if you don't already know it). Never returns a secret or certificate's
    plaintext — only metadata (description, type, environment, whether a value is set, sync status,
    and, for a reference key, which key it points at). An environment variable's own value IS
    included, unmasked, exactly like Nebula's own UI — call read_secret for a secret/certificate's
    plaintext instead.

    `query` (optional) case-insensitively substring-matches the key's name and description.
    `variable_type` (optional) is one of "secret", "environment", or "certificate". `environment`
    (optional) restricts to keys linked to that one Environment name (case-insensitive).
    """
    grant = await _resolve_grant(project)

    parsed_type: VariableType | None = None
    if variable_type is not None:
        try:
            parsed_type = VariableType(variable_type.strip().lower())
        except ValueError:
            raise ToolError(
                f"Unknown variable_type '{variable_type}' — expected one of: "
                f"{', '.join(t.value for t in VariableType)}"
            )

    async with async_session_factory() as session:
        proj = await _resolve_project_row(session, grant)
        keys = await secrets_service.list_keys(session, proj.id)

        needle = query.strip().lower() if query else None
        results: list[dict] = []
        for key in keys:
            if needle and needle not in key.name.lower() and needle not in (
                key.description or ""
            ).lower():
                continue
            summary = await _key_summary(session, proj.name, key)
            if parsed_type is not None and summary["variable_type"] != parsed_type.value:
                continue
            if environment is not None and summary["environment"].lower() != environment.strip().lower():
                continue
            results.append(summary)

        await _audit(
            session,
            grant,
            action="mcp.search",
            object_type="project",
            object_label=proj.name,
            success=True,
            detail=f"{len(results)} result(s)",
        )
        return results


# ── Reading ───────────────────────────────────────────────────────────────────
@mcp.tool
async def read_secret(project: str, environment: str, key: str) -> dict:
    """Reveal one secret, environment variable, or certificate's plaintext value, by Project +
    Environment + key name (all matched case-insensitively — call list_projects/list_environments/
    find_secrets first if you don't already know them). A reference key transparently resolves to
    its source key's current value, exactly like Nebula's own UI."""
    grant = await _resolve_grant(project)
    async with async_session_factory() as session:
        proj = await _resolve_project_row(session, grant)

        env = await environments_service.get_environment_by_name(session, environment)
        if env is None:
            await _audit(
                session, grant, action="mcp.read", success=False, detail="Unknown environment"
            )
            raise ToolError(f"Unknown environment '{environment}'")

        secret_key = await secrets_service.get_key_by_name(session, proj.id, key)
        if secret_key is None:
            await _audit(session, grant, action="mcp.read", success=False, detail="Unknown key")
            raise ToolError(f"Key '{key}' not found in project '{proj.name}'")

        if secret_key.environment_id != env.id:
            key_env = await environments_service.get_environment(session, secret_key.environment_id)
            await _audit(
                session,
                grant,
                action="mcp.read",
                object_type="secret_key",
                object_id=secret_key.id,
                success=False,
                detail="Environment mismatch",
            )
            raise ToolError(
                f"Key '{key}' exists in project '{proj.name}' but is linked to environment "
                f"'{key_env.name}', not '{environment}'"
            )

        # See _key_summary's comment: coerce, since this comes back as a bare `str` after a DB
        # round-trip, not a VariableType instance.
        variable_type, _ciphertext = await secrets_service.resolve_effective(session, secret_key)
        variable_type = VariableType(variable_type)
        try:
            value = await secrets_service.reveal_value(session, secret_key)
        except secrets_service.SecretValueNotFoundError:
            await _audit(
                session,
                grant,
                action="mcp.read",
                object_type="secret_key",
                object_id=secret_key.id,
                success=False,
                detail="No value set",
            )
            raise ToolError(f"Key '{key}' in project '{proj.name}' has no value set")

        await _audit(
            session,
            grant,
            action="mcp.read",
            object_type="secret_key",
            object_id=secret_key.id,
            object_label=f"{proj.name}/{env.name}/{secret_key.name}",
            success=True,
        )
        return {
            "project": proj.name,
            "environment": env.name,
            "key": secret_key.name,
            "variable_type": variable_type.value,
            "value": value,
        }


# ── Changing ──────────────────────────────────────────────────────────────────
@mcp.tool
async def set_secret_value(project: str, environment: str, key: str, value: str) -> dict:
    """Change the value of an EXISTING secret, environment variable, or certificate, by Project +
    Environment + key name — never creates a new key (use Nebula's own UI/REST API for that).
    Refuses on a reference key: its value can only be changed by editing its SOURCE key, in its own
    Project. Fans out to every enabled GitHub sync target for the Project afterward, exactly like
    every other value-changing surface in Nebula (best-effort — a GitHub outage never fails this
    call)."""
    grant = await _resolve_grant(project)
    async with async_session_factory() as session:
        proj = await _resolve_project_row(session, grant)

        env = await environments_service.get_environment_by_name(session, environment)
        if env is None:
            await _audit(
                session, grant, action="mcp.update", success=False, detail="Unknown environment"
            )
            raise ToolError(f"Unknown environment '{environment}'")

        secret_key = await secrets_service.get_key_by_name(session, proj.id, key)
        if secret_key is None:
            await _audit(session, grant, action="mcp.update", success=False, detail="Unknown key")
            raise ToolError(f"Key '{key}' not found in project '{proj.name}'")

        if secret_key.environment_id != env.id:
            key_env = await environments_service.get_environment(session, secret_key.environment_id)
            await _audit(
                session,
                grant,
                action="mcp.update",
                object_type="secret_key",
                object_id=secret_key.id,
                success=False,
                detail="Environment mismatch",
            )
            raise ToolError(
                f"Key '{key}' exists in project '{proj.name}' but is linked to environment "
                f"'{key_env.name}', not '{environment}'"
            )

        try:
            # rotation_frequency/rotation_unit pass through UNCHANGED — this tool has no concept of
            # a rotation schedule to offer, and set_value's contract otherwise fully REPLACES it on
            # every call (see nebula.secrets.set_value's own docstring; api/v1/vault.py's PUT
            # /secret follows the exact same rule for the exact same reason).
            await secrets_service.set_value(
                session,
                secret_key,
                plaintext=value,
                updated_by=None,
                rotation_frequency=secret_key.rotation_frequency,
                rotation_unit=secret_key.rotation_unit,
            )
        except secrets_service.SecretKeyIsReferenceError:
            await _audit(
                session,
                grant,
                action="mcp.update",
                object_type="secret_key",
                object_id=secret_key.id,
                success=False,
                detail="Key is a reference",
            )
            raise ToolError(
                f"'{key}' is a reference — its value can only be changed in its source project"
            )

        await _audit(
            session,
            grant,
            action="mcp.update",
            object_type="secret_key",
            object_id=secret_key.id,
            object_label=f"{proj.name}/{env.name}/{secret_key.name}",
            success=True,
        )
        await _auto_sync_github(session, grant, proj.id)
        return {"project": proj.name, "environment": env.name, "key": secret_key.name, "updated": True}
