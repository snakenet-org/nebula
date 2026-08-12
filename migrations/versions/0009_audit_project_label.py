#    (c) snakenet.org, All rights reserved
"""audit log project label

Adds `project_label` to audit_log_entries — the resolved Project's name, captured as plain text AT
WRITE TIME (same "never re-joined later" convention actor_label/object_label already follow, see
nebula.audit's module docstring) rather than a live join against `projects` through the loose
(SET NULL on delete) `project_id` reference. Populated by nebula.audit.record_access_key_action for
every api/v1/vault.py call (get_access_key already resolves the Project) — backs the Audit Logs
page's "API calls" tab, which needed a column showing which access key made a request AND which
Project it belongs to, distinct from `object_label`'s "project/environment/key" string.

Revision ID: 0009_audit_project_label
Revises: 0008_secret_key_reference
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_audit_project_label"
down_revision: str | None = "0008_secret_key_reference"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_log_entries", sa.Column("project_label", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_log_entries", "project_label")
