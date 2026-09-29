"""keep Task Capsule identity stable across revisions

A Task Capsule keeps its capsule_id for its whole life; each checkpoint adds a new revision.
With capsule_id as the sole primary key, revision 2 of the same capsule could never be stored
(it surfaced as a spurious "concurrent revision conflict"). Key rows by (capsule_id, revision).

Revision ID: 0004_capsule_revision_identity
Revises: 0003_governance_denial_state
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_capsule_revision_identity"
down_revision = "0003_governance_denial_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("task_capsules_pkey", "task_capsules", type_="primary")
        op.create_primary_key("task_capsules_pkey", "task_capsules", ["capsule_id", "revision"])
        return
    with op.batch_alter_table("task_capsules", recreate="always") as batch:
        batch.create_primary_key("task_capsules_pkey", ["capsule_id", "revision"])


def downgrade() -> None:
    # capsule_id alone cannot key rows once a capsule has several revisions. Refuse before any
    # DDL rather than delete revision history; pruning history would be data loss.
    bind = op.get_bind()
    duplicated = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM (SELECT capsule_id FROM task_capsules "
            "GROUP BY capsule_id HAVING COUNT(*) > 1) AS multi"
        )
    ).scalar()
    if duplicated:
        raise RuntimeError(
            f"refusing downgrade: {duplicated} Task Capsule(s) have multiple revisions; "
            "export and resolve them explicitly before downgrading"
        )
    if bind.dialect.name == "postgresql":
        op.drop_constraint("task_capsules_pkey", "task_capsules", type_="primary")
        op.create_primary_key("task_capsules_pkey", "task_capsules", ["capsule_id"])
        return
    with op.batch_alter_table("task_capsules", recreate="always") as batch:
        batch.create_primary_key("task_capsules_pkey", ["capsule_id"])
