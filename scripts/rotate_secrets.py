#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Standalone process — automatic SecretKey rotation. Ticks once an hour, scans every
  SecretKey across every Project for one whose configured rotation schedule is due, and re-generates
  its value with a fresh 35-character secure random secret.
@ai-context: A separate OS process, not an asyncio task inside main.py's uvicorn process — mirrors
  Gravity's own scheduler.py (a sibling snakeNet app with the same "don't let a background loop's
  crash/hang take the API down with it" reasoning), started alongside main.py by entrypoint.sh and
  killed by its shutdown trap. Uses nebula.database.async_session_factory directly (no FastAPI
  Depends, no Request) since nothing here runs inside a request. The actual due-check/regeneration
  logic lives in nebula.rotation (list_due_for_rotation/rotate_key) — this script is only the
  tick-every-hour loop plus the audit-logging/GitHub-sync fan-out around each rotation.
  Every rotation is recorded to the audit log (nebula.audit) — this is a STANDING RULE for every
  mutating action in this codebase, not optional (see CLAUDE.md). There is no ActorType for an
  automated/system actor (only USER and ACCESS_KEY exist — see nebula.models.tables.ActorType); a
  new third kind would make these rows invisible to both of the Audit Logs page's existing tabs
  (Activity=USER, API calls=ACCESS_KEY), so this attributes rotations to ActorType.USER with
  actor_id=None and actor_label="Automatic rotation" instead — it lands in the "Activity" tab,
  correctly scoped by project_id to that Project's own owner/editors, distinguishable from a real
  human row by its label alone. A rotated key with any enabled GitHub sync target is pushed to it
  too, exactly like any other value change (api/v1/secret.py's `_auto_sync_github`) — best-effort, a
  sync failure is itself audit-logged but never stops rotation from completing or being logged.
@ai-rules:
  - Never log a rotated secret's plaintext value anywhere — console, audit `detail`, or an exception
    message. nebula.rotation.rotate_key's return value (the new plaintext) is deliberately unused
    here.
  - Any new mutating action added to this script must also call nebula.audit.record — see the module
    docstring above.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio], loguru
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-12
"""

import asyncio
import signal
import sys

from loguru import logger

from nebula import audit as audit_service
from nebula import github_sync as github_sync_service
from nebula import rotation as rotation_service
from nebula.config import settings
from nebula.database import async_session_factory
from nebula.models.tables import ActorType, SecretKey

logger.remove()
logger.add(sys.stderr, level=settings.log_level)

TICK_SECONDS = 3600

# Attributed to no real human/UserAccount — see the module docstring for why this is ActorType.USER
# rather than a dedicated (nonexistent) "system" kind.
_SYSTEM_ACTOR_LABEL = "Automatic rotation"

_stop = asyncio.Event()


def _request_stop(*_args: object) -> None:
    _stop.set()


async def _sync_after_rotation(session, key: SecretKey) -> None:
    """Best-effort fan-out to every enabled GitHub sync target after a rotation — same shape as
    api/v1/secret.py's `_auto_sync_github`, just with no human actor/Request to attribute it to."""
    try:
        results = await github_sync_service.sync_all_for_project(session, key.project_id)
    except Exception:
        logger.exception(f"Auto GitHub sync after rotation crashed for project {key.project_id}")
        return
    for result in results:
        detail = result["error"] or (
            f"{result['secrets_synced']} secret(s), {result['variables_synced']} variable(s) across "
            f"{result['environments_synced']} environment(s)"
            + (f"; {len(result['failures'])} failure(s)" if result["failures"] else "")
        )
        await audit_service.record(
            session,
            actor_type=ActorType.USER,
            actor_id=None,
            actor_label=_SYSTEM_ACTOR_LABEL,
            action="github_sync_target.sync",
            object_type="project_github_sync",
            object_id=result["target_id"],
            object_label=result["name"],
            project_id=key.project_id,
            success=result["success"],
            detail=f"Auto-sync after rotation: {detail}",
        )


async def _rotate_one(session, key: SecretKey) -> None:
    frequency, unit = key.rotation_frequency, key.rotation_unit
    try:
        await rotation_service.rotate_key(session, key)
    except Exception:
        logger.exception(f"Failed to rotate secret key {key.id}")
        return
    logger.info(f"Rotated secret key {key.id} (every {frequency} {unit}(s)).")
    await audit_service.record(
        session,
        actor_type=ActorType.USER,
        actor_id=None,
        actor_label=_SYSTEM_ACTOR_LABEL,
        action="secret.rotate",
        object_type="secret_key",
        object_id=key.id,
        object_label=key.name,
        project_id=key.project_id,
        success=True,
        detail=f"Rotated automatically (every {frequency} {unit}(s)).",
    )
    await _sync_after_rotation(session, key)


async def _rotate_due_secrets() -> None:
    async with async_session_factory() as session:
        due = await rotation_service.list_due_for_rotation(session)
        if not due:
            return
        logger.info(f"{len(due)} secret(s) due for automatic rotation.")
        for key in due:
            await _rotate_one(session, key)


async def run() -> None:
    logger.info("Nebula secret-rotation daemon starting — checking every hour.")
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop)

    while not _stop.is_set():
        try:
            await _rotate_due_secrets()
        except Exception:
            logger.exception("Secret-rotation tick failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=TICK_SECONDS)
        except TimeoutError:
            pass

    logger.info("Nebula secret-rotation daemon stopping.")


if __name__ == "__main__":
    asyncio.run(run())
