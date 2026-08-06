#    (c) snakenet.org, All rights reserved
"""global environments

Redesigns Environment from project-scoped to a single global taxonomy shared across every
Project, and collapses the old SecretKey/SecretValue many-to-many (one row per key x environment)
down to a strict one-to-one: every SecretKey now carries its own `environment_id` (exactly one
Environment, reassignable but never unset or multi-valued) and its own `ciphertext` directly,
replacing the separate secret_values join table. Also adds SecretKey.variable_type
(environment/secret — see nebula.models.tables.VariableType) since this migration is already
restructuring the same table.

This is a breaking schema change with no meaningful automatic backfill (the old model's "one key,
many per-environment values" has no 1:1 mapping onto the new "one key, one environment" shape) —
confirmed against the live dev database first: projects/environments/secret_keys/secret_values were
all empty (only a single bootstrap admin user_accounts row existed), so this migration truncates
those tables rather than attempting a lossy semantic conversion.

Revision ID: 0002_global_environments
Revises: 0001_baseline
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_global_environments"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No lossy conversion possible from the old per-(key, environment) value model — clear out the
    # rows this migration restructures (confirmed empty in the live dev database before writing this).
    op.execute("TRUNCATE TABLE secret_values, secret_keys, environments RESTART IDENTITY CASCADE")

    op.drop_table("secret_values")

    op.execute("DROP INDEX IF EXISTS uq_environments_project_name_lower")
    op.drop_constraint("environments_project_id_fkey", "environments", type_="foreignkey")
    op.drop_column("environments", "project_id")
    op.add_column("environments", sa.Column("description", sa.Text(), nullable=True))
    op.execute("CREATE UNIQUE INDEX uq_environments_name_lower ON environments (lower(name))")

    op.add_column(
        "secret_keys",
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.add_column(
        "secret_keys",
        sa.Column("variable_type", sa.String(11), nullable=False, server_default="secret"),
    )
    op.add_column("secret_keys", sa.Column("ciphertext", sa.Text(), nullable=True))
    op.add_column(
        "secret_keys",
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_secret_keys_environment_id", "secret_keys", ["environment_id"])


def downgrade() -> None:
    op.drop_index("ix_secret_keys_environment_id", table_name="secret_keys")
    op.drop_column("secret_keys", "updated_by")
    op.drop_column("secret_keys", "ciphertext")
    op.drop_column("secret_keys", "variable_type")
    op.drop_column("secret_keys", "environment_id")

    op.execute("DROP INDEX IF EXISTS uq_environments_name_lower")
    op.drop_column("environments", "description")
    op.add_column(
        "environments",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_environments_project_name_lower "
        "ON environments (project_id, lower(name))"
    )

    op.create_table(
        "secret_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "secret_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("secret_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("secret_key_id", "environment_id", name="uq_secret_values_key_env"),
    )
