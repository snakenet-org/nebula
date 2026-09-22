#    (c) snakenet.org, All rights reserved
"""secret key name unique per project+environment, not per project alone

A key name was previously unique per Project regardless of Environment
(uq_secret_keys_project_name_lower on (project_id, lower(name))) — this widens the scope so the
same name can exist more than once in a Project as long as each occurrence sits in a different
Environment. Replaces that index with uq_secret_keys_project_env_name_lower on
(project_id, environment_id, lower(name)).

Revision ID: 0011_key_name_unique_per_env
Revises: 0010_secret_key_rotation
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
# Keep this at or under 32 chars — alembic_version.version_num is a stock VARCHAR(32) column
# (see the 2026-09-22 journal entry: 0006_github_sync_pat_reference was already exactly at the
# limit, and 0011's original longer name broke production migrations with a silent-looking
# StringDataRightTruncationError on the final "UPDATE alembic_version" step).
revision: str = "0011_key_name_unique_per_env"
down_revision: str | None = "0010_secret_key_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX uq_secret_keys_project_name_lower")
    op.execute(
        "CREATE UNIQUE INDEX uq_secret_keys_project_env_name_lower "
        "ON secret_keys (project_id, environment_id, lower(name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_secret_keys_project_env_name_lower")
    op.execute(
        "CREATE UNIQUE INDEX uq_secret_keys_project_name_lower "
        "ON secret_keys (project_id, lower(name))"
    )
