#    (c) snakenet.org, All rights reserved
"""multi-repo github sync

Replaces the single `projects.github_repo_url`/`github_pat_ciphertext` pair with a new
`project_github_syncs` table so a Project can have MANY simultaneous GitHub sync targets active at
once — see nebula.github_sync's new sync_all_for_project(), called after every secret/variable value
change (not just an explicit "Sync now" click) to push the current state to every enabled target.

Any pre-existing single repo/PAT config is carried forward as that project's first (enabled) sync
target before the old columns are dropped.

Revision ID: 0005_multi_github_sync
Revises: 0004_github_sync
Create Date: 2026-08-06
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_multi_github_sync"
down_revision: str | None = "0004_github_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_projects = sa.table(
    "projects",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("github_repo_url", sa.String),
    sa.column("github_pat_ciphertext", sa.Text),
)
_targets = sa.table(
    "project_github_syncs",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("project_id", postgresql.UUID(as_uuid=True)),
    sa.column("repo_url", sa.String),
    sa.column("pat_ciphertext", sa.Text),
    sa.column("enabled", sa.Boolean),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    op.create_table(
        "project_github_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("repo_url", sa.String(500), nullable=False),
        sa.Column("pat_ciphertext", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_success", sa.Boolean(), nullable=True),
        sa.Column("last_sync_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_project_github_syncs_project_id", "project_github_syncs", ["project_id"])

    bind = op.get_bind()
    existing = bind.execute(
        sa.select(
            _projects.c.id,
            _projects.c.github_repo_url,
            _projects.c.github_pat_ciphertext,
        ).where(_projects.c.github_repo_url.isnot(None))
    ).fetchall()
    for project_id, repo_url, pat_ciphertext in existing:
        bind.execute(
            _targets.insert().values(
                id=uuid.uuid4(),
                project_id=project_id,
                repo_url=repo_url,
                pat_ciphertext=pat_ciphertext,
                enabled=True,
            )
        )

    op.drop_column("projects", "github_pat_ciphertext")
    op.drop_column("projects", "github_repo_url")


def downgrade() -> None:
    op.add_column("projects", sa.Column("github_repo_url", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("github_pat_ciphertext", sa.Text(), nullable=True))

    # Best-effort only: the pre-migration shape has room for exactly one repo/PAT per project, so
    # only the OLDEST sync target per project can be folded back in — any additional targets a
    # multi-sync session created are silently dropped, since they literally cannot be represented
    # in the single-column shape being restored.
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            _targets.c.project_id, _targets.c.repo_url, _targets.c.pat_ciphertext, _targets.c.created_at
        ).order_by(_targets.c.created_at)
    ).fetchall()
    seen: set = set()
    for project_id, repo_url, pat_ciphertext, _created_at in rows:
        if project_id in seen:
            continue
        seen.add(project_id)
        bind.execute(
            _projects.update()
            .where(_projects.c.id == project_id)
            .values(github_repo_url=repo_url, github_pat_ciphertext=pat_ciphertext)
        )

    op.drop_table("project_github_syncs")
