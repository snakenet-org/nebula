#    (c) snakenet.org, All rights reserved
"""github sync PAT reference

Lets a ProjectGithubSync target's personal access token be EITHER a custom token it owns directly
(`pat_ciphertext`, unchanged from before) OR a reference to another SecretKey's own value
(`pat_source_key_id`) — see nebula.github_sync's module docstring for the resolution logic. Adds
`pat_source_key_id` (FK to secret_keys.id, ON DELETE RESTRICT — a referenced key can't be deleted
out from under a sync target that depends on it), relaxes `pat_ciphertext` to nullable, and adds a
CHECK constraint enforcing exactly one of the two is ever set.

Revision ID: 0006_github_sync_pat_reference
Revises: 0005_multi_github_sync
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_github_sync_pat_reference"
down_revision: str | None = "0005_multi_github_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("project_github_syncs", "pat_ciphertext", existing_type=sa.Text(), nullable=True)
    op.add_column(
        "project_github_syncs",
        sa.Column(
            "pat_source_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("secret_keys.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_project_github_syncs_pat_source_key_id", "project_github_syncs", ["pat_source_key_id"]
    )
    op.create_check_constraint(
        "ck_project_github_syncs_pat_xor",
        "project_github_syncs",
        "(pat_ciphertext IS NOT NULL) <> (pat_source_key_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_project_github_syncs_pat_xor", "project_github_syncs", type_="check")
    op.drop_index("ix_project_github_syncs_pat_source_key_id", table_name="project_github_syncs")
    op.drop_column("project_github_syncs", "pat_source_key_id")
    # Best-effort only: any target that was left in "reference" mode has no pat_ciphertext to
    # restore — this pre-reference shape has no way to represent that, same class of lossy downgrade
    # as 0005's own single-column fold-back. Such a row is simply left with a NULL pat_ciphertext,
    # which the OLD schema's NOT NULL constraint being reinstated below would then reject outright —
    # documented here rather than silently worked around, since this is a genuinely destructive
    # downgrade path an operator should notice before relying on it.
    op.alter_column("project_github_syncs", "pat_ciphertext", existing_type=sa.Text(), nullable=False)
