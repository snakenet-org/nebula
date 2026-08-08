#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Push a Project's keys/values into MANY simultaneously-linked GitHub repositories, via
  the `gh` CLI.
@ai-context: Since the 2026-08-06 multi-repo redesign, a Project may have any number of
  ProjectGithubSync rows ("sync targets"), each carrying its own `repo_url` + encrypted
  `pat_ciphertext` + `enabled` flag + last-run status (nebula.models.tables.ProjectGithubSync) — the
  old single github_repo_url/github_pat_ciphertext columns on Project are gone. sync_to_github()
  pushes ONE target: authenticates by setting `GH_TOKEN` in the `gh` subprocess's environment (never
  `gh auth login` — that would persist a credential to disk; `GH_TOKEN` is a one-shot,
  in-memory-only override per gh's own docs) and first runs `gh repo view` as the "does this token
  actually work against this repo" gate the product ask calls "if the connection works" — a non-zero
  exit there raises GitHubAuthError before touching anything. Every SecretKey with a value set is
  then pushed into a GitHub Environment named exactly like the Nebula Environment it's linked to
  (`gh api -X PUT .../environments/<name>` first ensures that GitHub Environment exists, matching
  gh's own idempotent-PUT semantics) — variable_type SECRET goes through `gh secret set`,
  variable_type ENVIRONMENT goes through `gh variable set`. Best-effort per key: one key's `gh`
  failure is collected into `failures` and does not abort the rest of that target's sync (a
  transient GitHub API hiccup on one key shouldn't block 50 other keys from syncing). The target's
  own `last_synced_at`/`last_sync_success`/`last_sync_detail` are updated at the end of every
  sync_to_github call, success or failure, so the Project Settings page can show each target's last
  run without a separate audit-log query.
  sync_all_for_project() is the fan-out entry point — every OTHER target's failure never blocks the
  rest (each target's GitHubSyncError is caught and turned into its own failed result), used by BOTH
  the "Sync all now" button (api/v1/project.py) AND — this is the actual point of the multi-repo
  redesign — api/v1/secret.py's create/update/delete/set_value/bulk_create routes, called after
  every value-affecting mutation so every linked-and-enabled repository stays current automatically,
  not just when someone remembers to click Sync.
  The plaintext value is ALWAYS piped via stdin, never passed as a CLI argument — `gh secret set`/
  `gh variable set` both read the value from stdin when neither `--body` nor `-f` is given, and a
  CLI arg would otherwise be briefly visible to any other process on the host via `ps`.
  Since 2026-08-08, a target's PAT can ALSO be a reference to another SecretKey elsewhere in the
  vault (`pat_source_key_id`) instead of a copy it owns (`pat_ciphertext`) — see
  nebula.models.tables.ProjectGithubSync's class docstring for the full invariant (exactly one of
  the two is ever set, enforced by a DB CHECK constraint too). create_sync_target/update_sync_target
  take BOTH `pat`/`pat_source_key_id` params and keep that XOR true on every write; permission-
  checking that the caller may actually reference the source key (nebula.projects.can_reveal on ITS
  Project, resolved via nebula.secrets.get_key_by_id) is the API router's job
  (api/v1/project.py), same as every other cross-cutting permission check in this app — this module
  only ever validates shape, never re-derives who's allowed to do what. `_resolve_token` is where
  the actual live lookup happens, called fresh by sync_to_github on every single sync — nothing
  about a reference is ever cached, which is the entire point: rotating the referenced key's value
  anywhere in the vault takes effect on this target's very next sync with zero extra plumbing.
  Since 2026-08-08, sync_to_github also skips any SecretKey with `sync_enabled=False` (a per-key
  toggle, nebula.secrets/nebula.models.tables.SecretKey) — same as a key with no value set: it's
  simply excluded from `by_environment` before any GitHub Environment/secret/variable push, so
  toggling a key off never removes it from a repo it was already pushed to, only stops future pushes.
@ai-rules:
  - Never pass a plaintext secret/PAT as a subprocess argv element — stdin only.
  - Never log a plaintext value, PAT, or full `gh` stderr verbatim if it could echo one back
    (`gh`'s own error messages don't echo secret values, so surfacing stderr text is safe here).
  - A failure syncing one target (or one key within a target) must never raise out of
    sync_all_for_project — the caller (especially the auto-sync-on-change hook) must always get a
    complete per-target result list back, never an exception.
  - create_sync_target/update_sync_target must never leave a row with both or neither of
    pat_ciphertext/pat_source_key_id set — raise InvalidPatConfigurationError instead.
  - Maintain 100% type-hinting coverage.
@dependencies: nebula.crypto
@version: 3.1.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-08
"""

import asyncio
import os
import re
import uuid
from datetime import datetime
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula import environments as environments_service
from nebula import secrets as secrets_service
from nebula.crypto import decrypt_value, encrypt_value
from nebula.models.tables import Project, ProjectGithubSync, SecretKey, VariableType

_REPO_URL_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$"
)


class GitHubSyncError(Exception):
    """Base class for every sync failure."""


class InvalidRepoUrlError(GitHubSyncError):
    """Raised when a target's repo_url doesn't parse into an owner/repo pair."""


class GitHubAuthError(GitHubSyncError):
    """Raised when `gh repo view` fails — bad PAT, wrong repo, or `gh` itself unavailable."""


class GitHubSyncTargetNotFoundError(Exception):
    """Raised when a sync target id doesn't exist (or belongs to a different Project)."""


class InvalidPatConfigurationError(Exception):
    """Raised when create/update would leave a target's PAT config as something other than exactly
    one of a custom `pat` or a `pat_source_key_id` — the app-level side of
    ck_project_github_syncs_pat_xor."""


class PatSourceKeyNotFoundError(Exception):
    """Raised when a `pat_source_key_id` doesn't resolve to an existing SecretKey. The API router
    should normally have already caught this via a permission-checked lookup before calling in here
    — this is a defense-in-depth backstop, e.g. against a TOCTOU race where the key was deleted
    between that check and this commit."""


class PatSourceUnavailableError(GitHubSyncError):
    """Raised at sync time when a target is in "reference" mode but the referenced SecretKey is
    gone or has no value set — surfaces as a normal failed sync (recorded on the target, caught by
    sync_all_for_project) rather than a crash."""


class SyncResult(TypedDict):
    target_id: uuid.UUID
    name: str
    repo_url: str
    success: bool
    error: str | None
    environments_synced: int
    secrets_synced: int
    variables_synced: int
    failures: list[str]


def parse_owner_repo(url: str) -> tuple[str, str]:
    match = _REPO_URL_RE.match(url.strip())
    if not match:
        raise InvalidRepoUrlError(url)
    return match.group(1), match.group(2)


def target_display_name(target: ProjectGithubSync) -> str:
    if target.name:
        return target.name
    try:
        owner, repo = parse_owner_repo(target.repo_url)
        return f"{owner}/{repo}"
    except InvalidRepoUrlError:
        return target.repo_url


# ── Sync target CRUD ────────────────────────────────────────────────────────
async def list_sync_targets(session: AsyncSession, project_id: uuid.UUID) -> list[ProjectGithubSync]:
    result = await session.execute(
        select(ProjectGithubSync)
        .where(ProjectGithubSync.project_id == project_id)
        .order_by(ProjectGithubSync.created_at)
    )
    return list(result.scalars().all())


async def get_sync_target(
    session: AsyncSession, project_id: uuid.UUID, target_id: uuid.UUID
) -> ProjectGithubSync:
    target = await session.get(ProjectGithubSync, target_id)
    if target is None or target.project_id != project_id:
        raise GitHubSyncTargetNotFoundError(str(target_id))
    return target


async def create_sync_target(
    session: AsyncSession,
    project: Project,
    *,
    repo_url: str,
    pat: str | None = None,
    pat_source_key_id: uuid.UUID | None = None,
    name: str | None = None,
) -> ProjectGithubSync:
    """Exactly one of `pat` (a custom token this target will own its own ciphertext for) or
    `pat_source_key_id` (a reference — see the module docstring) must be given. The caller
    (api/v1/project.py) is responsible for having already permission-checked `pat_source_key_id`
    (nebula.projects.can_reveal on ITS Project) before calling in here — this function only
    validates shape, plus a defense-in-depth existence check."""
    if bool(pat) == bool(pat_source_key_id):
        raise InvalidPatConfigurationError(
            "Provide exactly one of a personal access token or a referenced secret."
        )
    parse_owner_repo(repo_url)  # raises InvalidRepoUrlError before anything is persisted
    if pat_source_key_id is not None and await session.get(SecretKey, pat_source_key_id) is None:
        raise PatSourceKeyNotFoundError(str(pat_source_key_id))
    target = ProjectGithubSync(
        project_id=project.id,
        name=name.strip() if name and name.strip() else None,
        repo_url=repo_url.strip(),
        pat_ciphertext=encrypt_value(pat) if pat else None,
        pat_source_key_id=pat_source_key_id,
    )
    session.add(target)
    await session.commit()
    await session.refresh(target)
    return target


async def update_sync_target(
    session: AsyncSession,
    target: ProjectGithubSync,
    *,
    name: str | None = None,
    repo_url: str | None = None,
    pat: str | None = None,
    pat_source_key_id: uuid.UUID | None = None,
    enabled: bool | None = None,
) -> ProjectGithubSync:
    """Blank/omitted `pat` AND omitted `pat_source_key_id` leaves the current PAT config (whichever
    mode it's in) untouched — the frontend never echoes a stored PAT back, so there's nothing for a
    blank field to legitimately overwrite with (same shape as the pre-multi-repo
    update_github_config). Providing `pat` switches (or stays) the target to "custom" mode;
    providing `pat_source_key_id` switches (or stays) it to "reference" mode — providing BOTH in the
    same call is rejected, since only one can ever win."""
    if pat and pat_source_key_id is not None:
        raise InvalidPatConfigurationError(
            "Provide at most one of a personal access token or a referenced secret."
        )
    if repo_url is not None:
        parse_owner_repo(repo_url)  # raises InvalidRepoUrlError before anything is persisted
        target.repo_url = repo_url.strip()
    if name is not None:
        target.name = name.strip() or None
    if pat:
        target.pat_ciphertext = encrypt_value(pat)
        target.pat_source_key_id = None
    elif pat_source_key_id is not None:
        if await session.get(SecretKey, pat_source_key_id) is None:
            raise PatSourceKeyNotFoundError(str(pat_source_key_id))
        target.pat_source_key_id = pat_source_key_id
        target.pat_ciphertext = None
    if enabled is not None:
        target.enabled = enabled
    await session.commit()
    await session.refresh(target)
    return target


async def delete_sync_target(session: AsyncSession, target: ProjectGithubSync) -> None:
    await session.delete(target)
    await session.commit()


# ── Syncing ───────────────────────────────────────────────────────────────────
async def _run_gh(
    args: list[str], *, token: str, input_data: str | None = None
) -> tuple[int, str, str]:
    env = {**os.environ, "GH_TOKEN": token, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            env=env,
            stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise GitHubAuthError("The `gh` CLI is not installed on the Nebula server.") from exc

    stdin_bytes = input_data.encode() if input_data is not None else None
    stdout, stderr = await proc.communicate(stdin_bytes)
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _record_target_status(
    session: AsyncSession, target: ProjectGithubSync, *, success: bool, detail: str
) -> None:
    target.last_synced_at = datetime.utcnow()
    target.last_sync_success = success
    target.last_sync_detail = detail
    await session.commit()


async def _resolve_token(session: AsyncSession, target: ProjectGithubSync) -> str:
    """The live PAT for this target: its own ciphertext in "custom" mode, or a fresh decrypt of the
    referenced SecretKey's CURRENT ciphertext in "reference" mode — never cached, so a value
    rotated anywhere in the vault is picked up on the target's very next sync. Raises
    PatSourceUnavailableError (a GitHubSyncError) rather than a KeyError/TypeError so
    sync_all_for_project's existing `except GitHubSyncError` handling covers this for free."""
    if target.pat_source_key_id is not None:
        source_key = await session.get(SecretKey, target.pat_source_key_id)
        if source_key is None or source_key.ciphertext is None:
            raise PatSourceUnavailableError(
                "The referenced secret is missing or no longer has a value set."
            )
        return decrypt_value(source_key.ciphertext)
    if target.pat_ciphertext is None:
        raise PatSourceUnavailableError("No personal access token is configured.")
    return decrypt_value(target.pat_ciphertext)


async def sync_to_github(session: AsyncSession, target: ProjectGithubSync) -> dict:
    """Push ONE sync target. Raises InvalidRepoUrlError/GitHubAuthError/PatSourceUnavailableError on
    outright failure to connect (nothing was touched); otherwise always returns the per-key results
    dict, recording per-key failures inside it rather than raising. Either way, the target's own
    last_synced_at/last_sync_success/last_sync_detail are updated before returning/raising."""
    try:
        owner, repo = parse_owner_repo(target.repo_url)
    except InvalidRepoUrlError:
        await _record_target_status(session, target, success=False, detail="Invalid repository URL")
        raise

    try:
        token = await _resolve_token(session, target)
    except PatSourceUnavailableError as exc:
        await _record_target_status(session, target, success=False, detail=str(exc))
        raise

    returncode, _stdout, stderr = await _run_gh(
        ["repo", "view", f"{owner}/{repo}", "--json", "name"], token=token
    )
    if returncode != 0:
        detail = stderr.strip() or "gh could not authenticate against the given repository"
        await _record_target_status(session, target, success=False, detail=detail)
        raise GitHubAuthError(detail)

    keys = await secrets_service.list_keys(session, target.project_id)
    by_environment: dict[uuid.UUID, list[SecretKey]] = {}
    for key in keys:
        if key.ciphertext is None or not key.sync_enabled:
            continue
        by_environment.setdefault(key.environment_id, []).append(key)

    environments_synced = 0
    secrets_synced = 0
    variables_synced = 0
    failures: list[str] = []

    for environment_id, env_keys in by_environment.items():
        environment = await environments_service.get_environment(session, environment_id)
        returncode, _stdout, stderr = await _run_gh(
            ["api", "-X", "PUT", f"repos/{owner}/{repo}/environments/{environment.name}"],
            token=token,
        )
        if returncode != 0:
            failures.append(f"environment '{environment.name}': {stderr.strip()}")
            continue
        environments_synced += 1

        for key in env_keys:
            plaintext = decrypt_value(key.ciphertext or "")
            is_secret = key.variable_type == VariableType.SECRET
            verb = "secret" if is_secret else "variable"
            returncode, _stdout, stderr = await _run_gh(
                [verb, "set", key.name, "--repo", f"{owner}/{repo}", "--env", environment.name],
                token=token,
                input_data=plaintext,
            )
            if returncode != 0:
                failures.append(f"{verb} '{key.name}' ({environment.name}): {stderr.strip()}")
                continue
            if is_secret:
                secrets_synced += 1
            else:
                variables_synced += 1

    result = {
        "environments_synced": environments_synced,
        "secrets_synced": secrets_synced,
        "variables_synced": variables_synced,
        "failures": failures,
    }
    summary = (
        f"{secrets_synced} secret(s), {variables_synced} variable(s) across "
        f"{environments_synced} environment(s)"
        + (f"; {len(failures)} failure(s)" if failures else "")
    )
    await _record_target_status(session, target, success=not failures, detail=summary)
    return result


async def sync_all_for_project(
    session: AsyncSession, project_id: uuid.UUID, *, enabled_only: bool = True
) -> list[SyncResult]:
    """Push every (by default: enabled) sync target for a Project — one target's failure never
    stops another's. This is the fan-out both the "Sync all now" button AND the automatic
    on-value-change hook (api/v1/secret.py) call — never raises."""
    targets = await list_sync_targets(session, project_id)
    if enabled_only:
        targets = [t for t in targets if t.enabled]

    results: list[SyncResult] = []
    for target in targets:
        try:
            outcome = await sync_to_github(session, target)
            results.append(
                SyncResult(
                    target_id=target.id,
                    name=target_display_name(target),
                    repo_url=target.repo_url,
                    success=not outcome["failures"],
                    error=None,
                    environments_synced=outcome["environments_synced"],
                    secrets_synced=outcome["secrets_synced"],
                    variables_synced=outcome["variables_synced"],
                    failures=outcome["failures"],
                )
            )
        except GitHubSyncError as exc:
            results.append(
                SyncResult(
                    target_id=target.id,
                    name=target_display_name(target),
                    repo_url=target.repo_url,
                    success=False,
                    error=str(exc),
                    environments_synced=0,
                    secrets_synced=0,
                    variables_synced=0,
                    failures=[],
                )
            )
    return results
