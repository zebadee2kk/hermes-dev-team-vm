"""keep Task Capsule identity stable across revisions

A Task Capsule keeps its capsule_id for its whole life; each checkpoint adds a new revision.
With capsule_id as the sole primary key, revision 2 of the same capsule could never be stored
(it surfaced as a spurious "concurrent revision conflict"). Key rows by (capsule_id, revision).

Revision ID: 0004_capsule_revision_identity
Revises: 0003_governance_denial_state
Create Date: 2026-09-28
"""

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
    # Downgrade is only safe while every capsule has a single revision.
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("task_capsules_pkey", "task_capsules", type_="primary")
        op.create_primary_key("task_capsules_pkey", "task_capsules", ["capsule_id"])
        return
    with op.batch_alter_table("task_capsules", recreate="always") as batch:
        batch.create_primary_key("task_capsules_pkey", ["capsule_id"])
