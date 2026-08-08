#    (c) snakenet.org, All rights reserved
"""secret key reference

Lets a SecretKey's value be a REFERENCE to another SecretKey elsewhere in the vault
(`source_key_id`) instead of always owning its own ciphertext — same "custom vs. reference" shape
0006 already gave ProjectGithubSync.pat_source_key_id, generalized to ordinary secrets/variables.
Adds `source_key_id` (FK to secret_keys.id, ON DELETE RESTRICT — a key can't be deleted out from
under another key that references it), plus two CHECK constraints: a reference row never also owns
a ciphertext directly, and a key can never reference itself.

Revision ID: 0008_secret_key_reference
Revises: 0007_secret_key_sync_enabled
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_secret_key_reference"
down_revision: str | None = "0007_secret_key_sync_enabled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "secret_keys",
        sa.Column(
            "source_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("secret_keys.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_secret_keys_source_key_id", "secret_keys", ["source_key_id"])
    op.create_check_constraint(
        "ck_secret_keys_reference_no_own_value",
        "secret_keys",
        "source_key_id IS NULL OR ciphertext IS NULL",
    )
    op.create_check_constraint(
        "ck_secret_keys_reference_not_self", "secret_keys", "source_key_id IS NULL OR source_key_id <> id"
    )


def downgrade() -> None:
    op.drop_constraint("ck_secret_keys_reference_not_self", "secret_keys", type_="check")
    op.drop_constraint("ck_secret_keys_reference_no_own_value", "secret_keys", type_="check")
    op.drop_index("ix_secret_keys_source_key_id", table_name="secret_keys")
    op.drop_column("secret_keys", "source_key_id")
