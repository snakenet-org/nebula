#    (c) snakenet.org, All rights reserved
"""secret key sync enabled

Adds `secret_keys.sync_enabled` (Boolean, NOT NULL, default true) — a per-key on/off toggle for
GitHub sync. When false, nebula.github_sync.sync_to_github skips this key entirely (never pushed to
any linked repository, and never removed from one either — see that module for why). Defaults to
true so every pre-existing key keeps syncing exactly as it did before this column existed.

Revision ID: 0007_secret_key_sync_enabled
Revises: 0006_github_sync_pat_reference
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_secret_key_sync_enabled"
down_revision: str | None = "0006_github_sync_pat_reference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "secret_keys",
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("secret_keys", "sync_enabled")
