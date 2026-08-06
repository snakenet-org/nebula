#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Push a Project's keys/values into a GitHub repository, via the `gh` CLI.
@ai-context: A Project may optionally carry a `github_repo_url` + an encrypted `github_pat_
  ciphertext` (nebula.models.tables.Project, set together via update_github_config — a PAT is a
  credential like any secret value, encrypted the same way via nebula.crypto.encrypt_value, never
  returned from any API response). sync_to_github() is the actual push: authenticates by setting
  `GH_TOKEN` in the `gh` subprocess's environment (never `gh auth login` — that would persist a
  credential to disk; `GH_TOKEN` is a one-shot, in-memory-only override per gh's own docs) and first
  runs `gh repo view` as the "does this token actually work against this repo" gate the product ask
  calls "if the connection works" — a non-zero exit there raises GitHubAuthError before touching
  anything. Every SecretKey with a value set is then pushed into a GitHub Environment named exactly
  like the Nebula Environment it's linked to (`gh api -X PUT .../environments/<name>` first ensures
  that GitHub Environment exists, matching gh's own idempotent-PUT semantics) — variable_type SECRET
  goes through `gh secret set`, variable_type ENVIRONMENT goes through `gh variable set`. Best-effort
  per key: one key's `gh` failure is collected into `failures` and does not abort the rest of the
  sync (a transient GitHub API hiccup on one key shouldn't block 50 other keys from syncing).
  The plaintext value is ALWAYS piped via stdin, never passed as a CLI argument — `gh secret set`/
  `gh variable set` both read the value from stdin when neither `--body` nor `-f` is given, and a
  CLI arg would otherwise be briefly visible to any other process on the host via `ps`.
@ai-rules:
  - Never pass a plaintext secret/PAT as a subprocess argv element — stdin only.
  - Never log a plaintext value, PAT, or full `gh` stderr verbatim if it could echo one back
    (`gh`'s own error messages don't echo secret values, so surfacing stderr text is safe here).
  - Maintain 100% type-hinting coverage.
@dependencies: nebula.crypto
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-06
"""

import asyncio
import os
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from nebula import environments as environments_service
from nebula import secrets as secrets_service
from nebula.crypto import decrypt_value, encrypt_value
from nebula.models.tables import Project, SecretKey, VariableType

_REPO_URL_RE = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$"
)


class GitHubSyncError(Exception):
    """Base class for every sync failure."""


class InvalidRepoUrlError(GitHubSyncError):
    """Raised when github_repo_url doesn't parse into an owner/repo pair."""


class GitHubAuthError(GitHubSyncError):
    """Raised when `gh repo view` fails — bad PAT, wrong repo, or `gh` itself unavailable."""


class GitHubNotConfiguredError(GitHubSyncError):
    """Raised when sync is attempted on a Project with no repo_url/PAT set."""


def parse_owner_repo(url: str) -> tuple[str, str]:
    match = _REPO_URL_RE.match(url.strip())
    if not match:
        raise InvalidRepoUrlError(url)
    return match.group(1), match.group(2)


def has_github_config(project: Project) -> bool:
    return bool(project.github_repo_url and project.github_pat_ciphertext)


async def update_github_config(
    session: AsyncSession, project: Project, *, repo_url: str | None, pat: str | None
) -> Project:
    """Set the repo URL (always) and, only if a non-empty PAT was actually provided, re-encrypt it.

    An omitted/empty `pat` leaves the previously-stored one untouched (same "blank means keep the
    current value" shape as every sibling app's own M2M-credential edit form) — the frontend never
    echoes a stored PAT back, so there's nothing for a blank field to legitimately overwrite with.
    """
    if repo_url is not None:
        project.github_repo_url = repo_url.strip() or None
    if pat:
        project.github_pat_ciphertext = encrypt_value(pat)
    await session.commit()
    await session.refresh(project)
    return project


async def clear_github_config(session: AsyncSession, project: Project) -> Project:
    project.github_repo_url = None
    project.github_pat_ciphertext = None
    await session.commit()
    await session.refresh(project)
    return project


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


async def sync_to_github(session: AsyncSession, project: Project) -> dict:
    if not has_github_config(project):
        raise GitHubNotConfiguredError(str(project.id))

    owner, repo = parse_owner_repo(project.github_repo_url or "")
    token = decrypt_value(project.github_pat_ciphertext or "")

    returncode, _stdout, stderr = await _run_gh(
        ["repo", "view", f"{owner}/{repo}", "--json", "name"], token=token
    )
    if returncode != 0:
        raise GitHubAuthError(stderr.strip() or "gh could not authenticate against the given repository")

    keys = await secrets_service.list_keys(session, project.id)
    by_environment: dict[uuid.UUID, list[SecretKey]] = {}
    for key in keys:
        if key.ciphertext is None:
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

    return {
        "environments_synced": environments_synced,
        "secrets_synced": secrets_synced,
        "variables_synced": variables_synced,
        "failures": failures,
    }
