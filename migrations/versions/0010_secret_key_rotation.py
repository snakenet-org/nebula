#    (c) snakenet.org, All rights reserved
"""secret key rotation schedule

Adds an optional automatic-rotation schedule to secret_keys: `rotation_frequency` (a positive int),
`rotation_unit` (week/month/year — nebula.models.tables.RotationUnit), and `last_rotated_at` (when the
current value was put in place, distinct from the pre-existing `updated_at`, which also moves on a
plain rename/description/environment/sync-toggle edit). Both `rotation_frequency`/`rotation_unit` are
either set together or both null (rotation disabled) — enforced by a CHECK constraint, same
both-or-neither shape as the existing PAT-xor/reference constraints on this table. See
nebula.rotation for the due-check/generation logic and scripts/rotate_secrets.py for the hourly
process that acts on it.

Revision ID: 0010_secret_key_rotation
Revises: 0009_audit_project_label
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_secret_key_rotation"
down_revision: str | None = "0009_audit_project_label"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("secret_keys", sa.Column("rotation_frequency", sa.Integer(), nullable=True))
    op.add_column("secret_keys", sa.Column("rotation_unit", sa.String(5), nullable=True))
    op.add_column("secret_keys", sa.Column("last_rotated_at", sa.DateTime(), nullable=True))
    op.create_check_constraint(
        "ck_secret_keys_rotation_pair",
        "secret_keys",
        "(rotation_frequency IS NULL) = (rotation_unit IS NULL)",
    )
    op.create_check_constraint(
        "ck_secret_keys_rotation_frequency_positive",
        "secret_keys",
        "rotation_frequency IS NULL OR rotation_frequency > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_secret_keys_rotation_frequency_positive", "secret_keys", type_="check")
    op.drop_constraint("ck_secret_keys_rotation_pair", "secret_keys", type_="check")
    op.drop_column("secret_keys", "last_rotated_at")
    op.drop_column("secret_keys", "rotation_unit")
    op.drop_column("secret_keys", "rotation_frequency")
