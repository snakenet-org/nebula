#    (c) snakenet.org, All rights reserved
"""audit log

Adds audit_log_entries — an append-only log of every mutating action taken through Nebula, both
by a logged-in human (nebula.audit's ActorType.USER — project/environment/secret CRUD, sharing,
access-key management, login/logout, reveal) and by a Project access key hitting the external
vault retrieval route (ActorType.ACCESS_KEY — the "API calls" tab, `success=False` rows also back
the dashboard's failed-retrieval chart). See nebula.audit and api/v1/audit.py.

Revision ID: 0003_audit_log
Revises: 0002_global_environments
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_audit_log"
down_revision: str | None = "0002_global_environments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_type", sa.String(11), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_label", sa.String(255), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_label", sa.String(255), nullable=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_log_entries_occurred_at", "audit_log_entries", ["occurred_at"])
    op.create_index("ix_audit_log_entries_actor_type", "audit_log_entries", ["actor_type"])
    op.create_index("ix_audit_log_entries_action", "audit_log_entries", ["action"])
    op.create_index("ix_audit_log_entries_project_id", "audit_log_entries", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_entries_project_id", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_action", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_actor_type", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_occurred_at", table_name="audit_log_entries")
    op.drop_table("audit_log_entries")
