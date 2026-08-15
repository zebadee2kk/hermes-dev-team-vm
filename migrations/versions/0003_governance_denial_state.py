"""persist governance denial recurrence

Revision ID: 0003_governance_denial_state
Revises: 0002_assurance_expansion
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_governance_denial_state"
down_revision = "0002_assurance_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_denial_states",
        sa.Column("state_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("signature", sa.String(length=255), nullable=False),
        sa.Column("consecutive", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column("last_denied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "project_id",
            "task_id",
            "signature",
            name="uq_governance_denial_scope",
        ),
    )
    op.create_index(
        "ix_governance_denial_states_project_id",
        "governance_denial_states",
        ["project_id"],
    )
    op.create_index(
        "ix_governance_denial_states_task_id",
        "governance_denial_states",
        ["task_id"],
    )
    op.create_index(
        "ix_governance_denial_states_signature",
        "governance_denial_states",
        ["signature"],
    )


def downgrade() -> None:
    op.drop_index("ix_governance_denial_states_signature", table_name="governance_denial_states")
    op.drop_index("ix_governance_denial_states_task_id", table_name="governance_denial_states")
    op.drop_index("ix_governance_denial_states_project_id", table_name="governance_denial_states")
    op.drop_table("governance_denial_states")
