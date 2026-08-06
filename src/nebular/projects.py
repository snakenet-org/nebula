#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Project CRUD, sharing, and the permission matrix every other feature module builds on.
@ai-context: A nebular-user (non-admin) can only ever see a Project via ownership or an explicit
  ProjectShare row — enforced here in list_projects/get_visible_project (never trusted to the
  caller). Permission helpers all take the already-resolved `actor` UserAccount + `project` +
  (where relevant) the caller's own ProjectShare row, resolved once per request by the router layer
  via get_share():
    - can_view    — owner, admin, or ANY ProjectShare row (either role).
    - can_edit    — owner, admin, or ProjectShare.role == EDITOR. Governs environments/keys/values
                    CRUD and editing the project's own name/description.
    - can_reveal  — owner or admin ONLY, regardless of share role. A shared EDITOR can create/change
                    values but never decrypt one back — see nebular.secrets.reveal_value.
    - can_manage_sharing / can_manage_access_keys / can_delete — owner or admin only.
  These mirror gravity.pulsars' can_edit/can_change_state shape: bare functions taking already-loaded
  objects, no ORM queries of their own, so a router can resolve everything it needs in one pass and
  then just call these as pure checks.
@ai-rules:
  - Every list/get that returns Projects to a caller MUST go through list_projects/
    get_visible_project — never a bare `select(Project)` elsewhere in the codebase.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebular.models.tables import Environment, Project, ProjectShare, SecretKey, ShareRole, UserAccount


class ProjectNotFoundError(Exception):
    """Raised when a Project id doesn't exist or isn't visible to the caller."""


class DuplicateProjectShareError(Exception):
    """Raised when sharing a Project with a user it's already shared with."""


class UnknownShareTargetError(Exception):
    """Raised when sharing a Project with a username that doesn't resolve to a user."""


# ── Permission matrix ────────────────────────────────────────────────────────
def can_view(actor: UserAccount, project: Project, share: ProjectShare | None) -> bool:
    return actor.is_admin or project.owner_id == actor.id or share is not None


def can_edit(actor: UserAccount, project: Project, share: ProjectShare | None) -> bool:
    return (
        actor.is_admin
        or project.owner_id == actor.id
        or (share is not None and share.role == ShareRole.EDITOR)
    )


def can_reveal(actor: UserAccount, project: Project) -> bool:
    return actor.is_admin or project.owner_id == actor.id


def can_manage_sharing(actor: UserAccount, project: Project) -> bool:
    return actor.is_admin or project.owner_id == actor.id


def can_manage_access_keys(actor: UserAccount, project: Project) -> bool:
    return actor.is_admin or project.owner_id == actor.id


def can_delete(actor: UserAccount, project: Project) -> bool:
    return actor.is_admin or project.owner_id == actor.id


# ── Lookups ───────────────────────────────────────────────────────────────────
async def get_share(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectShare | None:
    return await session.get(ProjectShare, {"project_id": project_id, "user_id": user_id})


async def get_visible_project(
    session: AsyncSession, actor: UserAccount, project_id: uuid.UUID
) -> tuple[Project, ProjectShare | None]:
    """Fetch a Project the caller may at least view, or raise ProjectNotFoundError.

    A 404 (not a 403) is deliberate for both "doesn't exist" and "exists but not visible to you" —
    same not-found-vs-forbidden reasoning as every other snakeNet app, so a Project id's existence
    can't be probed by an unrelated caller.
    """
    project = await session.get(Project, project_id)
    share = await get_share(session, project_id, actor.id) if project else None
    if project is None or not can_view(actor, project, share):
        raise ProjectNotFoundError(str(project_id))
    return project, share


async def list_projects(session: AsyncSession, actor: UserAccount) -> list[Project]:
    """Every Project the caller owns, is shared on, or (if admin) every Project that exists."""
    if actor.is_admin:
        result = await session.execute(select(Project).order_by(Project.name))
        return list(result.scalars().all())

    result = await session.execute(
        select(Project)
        .outerjoin(
            ProjectShare,
            (ProjectShare.project_id == Project.id) & (ProjectShare.user_id == actor.id),
        )
        .where(or_(Project.owner_id == actor.id, ProjectShare.user_id == actor.id))
        .order_by(Project.name)
    )
    return list(result.scalars().unique().all())


async def counts_for_project(session: AsyncSession, project_id: uuid.UUID) -> tuple[int, int]:
    """(environment_count, secret_key_count) for a Project — used to populate ProjectResponse."""
    env_count = (
        await session.execute(
            select(func.count()).select_from(Environment).where(Environment.project_id == project_id)
        )
    ).scalar_one()
    key_count = (
        await session.execute(
            select(func.count()).select_from(SecretKey).where(SecretKey.project_id == project_id)
        )
    ).scalar_one()
    return env_count, key_count


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def create_project(
    session: AsyncSession, actor: UserAccount, *, name: str, description: str | None
) -> Project:
    project = Project(name=name, description=description, owner_id=actor.id)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def update_project(
    session: AsyncSession,
    project: Project,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Project:
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)
    await session.commit()


# ── Sharing ───────────────────────────────────────────────────────────────────
async def list_shares(session: AsyncSession, project_id: uuid.UUID) -> list[ProjectShare]:
    result = await session.execute(
        select(ProjectShare).where(ProjectShare.project_id == project_id)
    )
    return list(result.scalars().all())


async def share_project(
    session: AsyncSession, project: Project, *, username: str, role: ShareRole
) -> ProjectShare:
    result = await session.execute(select(UserAccount).where(UserAccount.username == username))
    target = result.scalar_one_or_none()
    if target is None:
        raise UnknownShareTargetError(username)
    if target.id == project.owner_id:
        raise DuplicateProjectShareError(username)

    existing = await get_share(session, project.id, target.id)
    if existing is not None:
        raise DuplicateProjectShareError(username)

    share = ProjectShare(project_id=project.id, user_id=target.id, role=role)
    session.add(share)
    await session.commit()
    return share


async def update_share_role(
    session: AsyncSession, share: ProjectShare, *, role: ShareRole
) -> ProjectShare:
    share.role = role
    await session.commit()
    return share


async def revoke_share(session: AsyncSession, share: ProjectShare) -> None:
    await session.delete(share)
    await session.commit()
