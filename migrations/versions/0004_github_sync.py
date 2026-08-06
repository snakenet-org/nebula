#    (c) snakenet.org, All rights reserved
"""github sync

Adds projects.github_repo_url + projects.github_pat_ciphertext (both optional, set together — see
nebula.github_sync) backing the "Sync to GitHub" feature: pushing a Project's keys/values into a
GitHub repository's per-Environment secrets/variables via the `gh` CLI.

Revision ID: 0004_github_sync
Revises: 0003_audit_log
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_github_sync"
down_revision: str | None = "0003_audit_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("github_repo_url", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("github_pat_ciphertext", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "github_pat_ciphertext")
    op.drop_column("projects", "github_repo_url")
