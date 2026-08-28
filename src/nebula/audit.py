#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Append-only audit log — every mutating action taken through Nebula, by a human or a
  Project access key.
@ai-context: record() is called from the ROUTER layer (api/v1/*.py), right after a mutation
  succeeds (or, for vault.py's external calls, after either outcome) — never from the thin
  service modules (nebula.projects/environments/secrets/access_keys), since only the router has
  both the resolved `actor` and the live `Request` (for ip_address). RULE FOR EVERY FUTURE FEATURE:
  any new mutating route must call record() too — this is not optional, per explicit product
  direction ("for all future features, always add an audit log").
  actor_label/object_label are captured as plain text AT WRITE TIME (never re-joined later) so the
  log stays readable after the underlying user/project/key is renamed or deleted — actor_id/
  object_id/project_id are kept as loose (non-FK, or SET NULL) references for optional filtering
  only, never required for the row to render.
  Two actor kinds partition the log into the two tabs the Audit Logs page shows:
    - ActorType.USER   — a logged-in human (local admin or OIDC) — list_activity().
    - ActorType.ACCESS_KEY — a Project access key hitting api/v1/vault.py — list_api_calls(). Rows
      with success=False here are failed attempts (any non-200 vault.py response, not just a
      lookup miss) — list_failed_retrievals() backs both the Audit Logs page's own "Failed
      retrievals" tab and the Dashboard's "Failed attempts / day" chart (see nebula.dashboard).
  VAULT_ACTIONS enumerates every api/v1/vault.py route's action string ("vault.retrieve" /secret,
  "vault.project" /project, "vault.status" /status) — every one of the three is now audit-logged on
  every call (added 2026-08-07; /status previously logged nothing at all), and list_api_calls/
  list_failed_retrievals/the Dashboard's api_requests+failed_attempts series all aggregate across
  the whole set rather than /secret alone, since "any call to any vault route" is the unit both the
  Audit Logs page and the Dashboard now count.
  EXTRACTION_ACTIONS (2026-08-09) is the narrower "this SecretKey's value actually left the vault"
  pair — "secret.reveal" (a human, api/v1/secret.py's reveal_value) and "vault.retrieve" (a Project
  access key, api/v1/vault.py's get_secret) — backing extraction_counts_by_project/
  extraction_count_for_key, the per-key "how many times has this been extracted" used by
  ProjectView.vue's key-row info/warning icon. Only success=True rows count — a failed reveal/
  retrieve (no value set, wrong environment, ...) never actually extracted anything. vault.py's
  get_secret now sets object_id=secret_key.id on every audit row where the key resolved (previously
  only object_label, a display string), same as secret.py's reveal_value already did — required for
  either action to be attributable to a specific key by id rather than by fragile name matching
  that would break silently across a rename.
  2026-08-12: list_activity/list_api_calls/list_failed_retrievals/daily_counts all gained an optional
  `project_ids` filter (GitHub #4) — a non-admin caller now sees the Audit Logs page and Dashboard
  scoped to only the Projects they own or are an EDITOR share on
  (nebula.projects.list_editable_project_ids), resolved by api/v1/audit.py and api/v1/dashboard.py;
  admins keep passing `project_ids=None` for the unscoped, app-wide view. Scoping by `project_id IN
  (...)` also naturally drops rows with no project at all (global Environment CRUD, auth.login/
  logout/refresh) for a non-admin — intentional, since those aren't "audit logs of a project they
  own or edit."
  2026-08-12 (later same day): list_activity/list_api_calls/list_failed_retrievals now page
  (`page`/`page_size`, capped at MAX_PAGE_SIZE=300 — the Audit Logs page's own hard cap, enforced
  again here as a safety net even though api/v1/audit.py's own Query(le=300) already rejects a
  larger request) and accept an optional `search` string, returned alongside `total` as a
  `(items, total)` tuple rather than a bare list — the log can run to thousands of rows and no
  caller needs (or should be handed) all of them in one response. `search` is a plain
  case-insensitive substring match (`ILIKE %term%`) OR'd across whichever of actor_label/action/
  object_label/project_label a row carries — deliberately not a stored `tsvector`+GIN-index column:
  action strings are short, dot-separated tokens ("vault.retrieve") that Postgres's default text
  search parser doesn't reliably split on a plain substring query, and this table has no volume yet
  that a `LIMIT`-bounded ILIKE scan can't handle. `record_access_key_action` (and now `record`
  itself) also carry a new `project_label` — the resolved Project's name captured at write time,
  same "never re-joined later" reasoning as actor_label/object_label (see
  models.tables.AuditLogEntry.project_label) — backing the "API calls" tab's new Project column
  without a live join through the loose (SET NULL) `project_id` reference.
  2026-08-27: VAULT_ACTIONS gained "vault.update" (api/v1/vault.py's new PUT /vault/secret, a
  project-access-key-authenticated route that CHANGES a key's value rather than reading one) — it
  rolls up into list_api_calls/list_failed_retrievals/the Dashboard's api_requests/failed_attempts
  series alongside the other three exactly like any other vault.py action. Deliberately NOT added to
  EXTRACTION_ACTIONS — setting a value never reveals one, so it must never count toward "how many
  times has this key's plaintext left the vault".
  2026-08-28: new "mcp.search"/"mcp.read"/"mcp.update" — nebula.mcp_server's find_secrets/read_secret/
  set_secret_value, the built-in MCP server's own project-access-key-authenticated tool calls. These
  are a SEPARATE surface from VAULT_ACTIONS on purpose — that tuple is documented above as
  enumerating api/v1/vault.py's own route actions specifically, and folding a second transport into
  it would make that scoping claim false; they still show up in list_api_calls' "API calls" tab for
  free (it filters only on ActorType.ACCESS_KEY, no action allowlist), just not in
  list_failed_retrievals or the Dashboard's vault-specific charts. "mcp.read" IS added to
  EXTRACTION_ACTIONS — a value genuinely left the vault through it, same as "secret.reveal"/
  "vault.retrieve".
@ai-rules:
  - Never put a plaintext secret value in `detail` or any other column.
  - Maintain 100% type-hinting coverage.
@dependencies: sqlalchemy[asyncio]
@version: 1.6.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-28
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from fastapi import Request
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nebula.models.tables import ActorType, AuditLogEntry, UserAccount

# The Audit Logs page's hard per-page cap — re-enforced here, not just at the API/Query layer.
MAX_PAGE_SIZE = 300

# Columns a free-text `search` term is OR'd across — see the module docstring for why this is a
# plain ILIKE match rather than a stored tsvector column.
_SEARCHABLE_COLUMNS = (
    AuditLogEntry.actor_label,
    AuditLogEntry.action,
    AuditLogEntry.object_label,
    AuditLogEntry.project_label,
)

# Every api/v1/vault.py route's action string — see the module docstring above. "vault.update"
# (2026-08-27) is PUT /vault/secret — the one vault.py route that also requires X-Nebula-Token on
# top of the project access key, since it writes a value rather than just reading one.
VAULT_ACTIONS: tuple[str, ...] = ("vault.retrieve", "vault.project", "vault.status", "vault.update")

# nebula.mcp_server's own tool-call actions — the built-in MCP server, a SEPARATE machine-credential
# surface from VAULT_ACTIONS on purpose (see the module docstring's 2026-08-28 entry).
MCP_ACTIONS: tuple[str, ...] = ("mcp.search", "mcp.read", "mcp.update")

# The actions that mean "a SecretKey's value actually left the vault" — see the module docstring.
EXTRACTION_ACTIONS: tuple[str, ...] = ("secret.reveal", "vault.retrieve", "mcp.read")


def _client_ip(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


async def record(
    session: AsyncSession,
    *,
    actor_type: ActorType,
    actor_id: uuid.UUID | None,
    actor_label: str | None,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    project_label: str | None = None,
    success: bool = True,
    detail: str | None = None,
    ip_address: str | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=project_id,
        project_label=project_label,
        success=success,
        detail=detail,
        ip_address=ip_address,
    )
    session.add(entry)
    await session.commit()
    return entry


async def record_user_action(
    session: AsyncSession,
    actor: UserAccount,
    request: Request | None,
    *,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    success: bool = True,
    detail: str | None = None,
) -> AuditLogEntry:
    """Convenience wrapper for the common case — a logged-in human performed `action`."""
    return await record(
        session,
        actor_type=ActorType.USER,
        actor_id=actor.id,
        actor_label=actor.username,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=project_id,
        success=success,
        detail=detail,
        ip_address=_client_ip(request),
    )


async def record_access_key_action(
    session: AsyncSession,
    *,
    access_key_id: uuid.UUID | None,
    access_key_label: str,
    request: Request | None,
    action: str,
    object_type: str | None = None,
    object_id: uuid.UUID | None = None,
    object_label: str | None = None,
    project_id: uuid.UUID | None = None,
    project_label: str | None = None,
    success: bool,
    detail: str | None = None,
) -> AuditLogEntry:
    """Convenience wrapper for the machine-caller case — a Project access key performed `action`."""
    return await record(
        session,
        actor_type=ActorType.ACCESS_KEY,
        actor_id=access_key_id,
        actor_label=access_key_label,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label,
        project_id=project_id,
        project_label=project_label,
        success=success,
        detail=detail,
        ip_address=_client_ip(request),
    )


def _search_condition(search: str | None) -> ColumnElement[bool] | None:
    """OR's a case-insensitive substring match for `search` across _SEARCHABLE_COLUMNS, or None
    (no-op) when `search` is empty/blank — see the module docstring for why this is ILIKE, not a
    stored tsvector column."""
    term = search.strip() if search else ""
    if not term:
        return None
    pattern = f"%{term}%"
    return or_(*(column.ilike(pattern) for column in _SEARCHABLE_COLUMNS))


async def _paginate(
    session: AsyncSession,
    conditions: list[ColumnElement[bool]],
    *,
    page: int,
    page_size: int,
) -> tuple[list[AuditLogEntry], int]:
    """Shared offset/limit pagination for list_activity/list_api_calls/list_failed_retrievals —
    returns (this page's rows newest-first, total matching row count)."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)

    total = (
        await session.execute(select(func.count()).select_from(AuditLogEntry).where(*conditions))
    ).scalar_one()
    result = await session.execute(
        select(AuditLogEntry)
        .where(*conditions)
        .order_by(AuditLogEntry.occurred_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def list_activity(
    session: AsyncSession,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = MAX_PAGE_SIZE,
    project_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[list[AuditLogEntry], int]:
    """Human (ActorType.USER) actions, newest first, paged — the Audit Logs page's "Activity" tab.
    Returns (this page's rows, total matching row count).

    `project_ids=None` (admin) returns every row app-wide. A non-None sequence (a non-admin's
    owned+editor Projects, see nebula.projects.list_editable_project_ids) scopes to only rows whose
    `project_id` is in that set — this also naturally excludes actions with no project at all (global
    Environment CRUD, auth.login/logout/refresh), which is intentional: a non-admin sees audit logs
    OF THEIR PROJECTS, not the whole app's activity. `search`, when given, OR's a substring match
    across actor_label/action/object_label/project_label (see _search_condition).
    """
    conditions: list[ColumnElement[bool]] = [AuditLogEntry.actor_type == ActorType.USER]
    if project_ids is not None:
        conditions.append(AuditLogEntry.project_id.in_(project_ids))
    search_condition = _search_condition(search)
    if search_condition is not None:
        conditions.append(search_condition)
    return await _paginate(session, conditions, page=page, page_size=page_size)


async def list_api_calls(
    session: AsyncSession,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = MAX_PAGE_SIZE,
    project_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[list[AuditLogEntry], int]:
    """Access-key (ActorType.ACCESS_KEY) calls, newest first, paged — the "API calls" tab.
    Returns (this page's rows, total matching row count).

    See list_activity's docstring for what `project_ids=None`/`search` mean — every vault.py call
    already carries a project_id (it's always dispatched against one Project's access key), so
    scoping here never drops a row for a spurious "no project" reason.
    """
    conditions: list[ColumnElement[bool]] = [AuditLogEntry.actor_type == ActorType.ACCESS_KEY]
    if project_ids is not None:
        conditions.append(AuditLogEntry.project_id.in_(project_ids))
    search_condition = _search_condition(search)
    if search_condition is not None:
        conditions.append(search_condition)
    return await _paginate(session, conditions, page=page, page_size=page_size)


async def list_failed_retrievals(
    session: AsyncSession,
    *,
    search: str | None = None,
    page: int = 1,
    page_size: int = MAX_PAGE_SIZE,
    project_ids: Sequence[uuid.UUID] | None = None,
) -> tuple[list[AuditLogEntry], int]:
    """Failed calls to any api/v1/vault.py route, newest first, paged — the "Failed retrievals" tab.
    Returns (this page's rows, total matching row count).

    See list_activity's docstring for what `project_ids=None`/`search` mean.
    """
    conditions: list[ColumnElement[bool]] = [
        AuditLogEntry.action.in_(VAULT_ACTIONS),
        AuditLogEntry.success.is_(False),
    ]
    if project_ids is not None:
        conditions.append(AuditLogEntry.project_id.in_(project_ids))
    search_condition = _search_condition(search)
    if search_condition is not None:
        conditions.append(search_condition)
    return await _paginate(session, conditions, page=page, page_size=page_size)


async def daily_counts(
    session: AsyncSession,
    *,
    action: str | Sequence[str],
    actor_type: ActorType,
    success: bool | None,
    days: int,
    project_ids: Sequence[uuid.UUID] | None = None,
) -> dict[date, int]:
    """Per-day counts of `action` (one action, or any of several) over the trailing `days` — backs
    nebula.dashboard's charts.

    Returns every day in the window (zero-filled), not just days with activity, so a chart never has
    to reconstruct missing dates itself. `project_ids=None` (admin) counts app-wide; a scoped
    sequence (nebula.projects.list_editable_project_ids) restricts to those Projects' rows only —
    see list_activity's docstring for the same admin-vs-scoped shape.
    """
    since = datetime.utcnow() - timedelta(days=days - 1)
    day_expr = func.date_trunc("day", AuditLogEntry.occurred_at)
    action_condition = (
        AuditLogEntry.action.in_(action)
        if isinstance(action, (list, tuple, set))
        else AuditLogEntry.action == action
    )
    conditions = [
        action_condition,
        AuditLogEntry.actor_type == actor_type,
        AuditLogEntry.occurred_at >= since,
    ]
    if success is not None:
        conditions.append(AuditLogEntry.success.is_(success))
    if project_ids is not None:
        conditions.append(AuditLogEntry.project_id.in_(project_ids))

    result = await session.execute(
        select(day_expr, func.count()).where(*conditions).group_by(day_expr)
    )
    counts = {row[0].date(): row[1] for row in result.all()}

    today = datetime.utcnow().date()
    return {
        today - timedelta(days=offset): counts.get(today - timedelta(days=offset), 0)
        for offset in range(days - 1, -1, -1)
    }


async def extraction_counts_by_project(
    session: AsyncSession, project_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """Per-key successful-extraction counts for every SecretKey in `project_id`, one query — backs
    the Project view's per-key info/warning icon. A key with zero extractions is simply absent from
    the returned dict (callers should `.get(key_id, 0)`)."""
    result = await session.execute(
        select(AuditLogEntry.object_id, func.count())
        .where(
            AuditLogEntry.project_id == project_id,
            AuditLogEntry.object_type == "secret_key",
            AuditLogEntry.action.in_(EXTRACTION_ACTIONS),
            AuditLogEntry.success.is_(True),
        )
        .group_by(AuditLogEntry.object_id)
    )
    return {row[0]: row[1] for row in result.all() if row[0] is not None}


async def extraction_count_for_key(session: AsyncSession, key_id: uuid.UUID) -> int:
    """Successful-extraction count for a single key — see extraction_counts_by_project, used instead
    when only one key's response is being built (create/update/set_value), not a whole list."""
    result = await session.execute(
        select(func.count()).where(
            AuditLogEntry.object_id == key_id,
            AuditLogEntry.object_type == "secret_key",
            AuditLogEntry.action.in_(EXTRACTION_ACTIONS),
            AuditLogEntry.success.is_(True),
        )
    )
    return result.scalar_one()
