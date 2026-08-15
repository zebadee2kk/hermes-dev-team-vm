"""assurance core

Revision ID: 0001_assurance_core
Revises:
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_assurance_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "task_capsules",
        sa.Column("capsule_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("kanban_task_id", sa.String(length=128), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "revision", name="uq_capsule_task_revision"),
    )
    op.create_table(
        "reality_anchors",
        sa.Column("anchor_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("anchor_type", sa.String(length=64), nullable=False),
        sa.Column("claim_ref", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "trust_envelopes",
        sa.Column("envelope_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("content_ref", sa.String(length=512), nullable=False),
        sa.Column("trust", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "inference_deployments",
        sa.Column("deployment_id", sa.String(length=128), primary_key=True),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("account_ref", sa.String(length=255), nullable=True),
        sa.Column("tier", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("credential_binding", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_class", sa.String(length=64), nullable=False),
        sa.Column("accepted_sensitivity", sa.JSON(), nullable=False),
        sa.Column("capability_scores", sa.JSON(), nullable=False),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("latency_score", sa.Float(), nullable=False),
        sa.Column("development_only", sa.Boolean(), nullable=False),
        sa.Column("terms_evidence_ref", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "quota_observations",
        sa.Column("observation_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deployment_id", sa.String(length=128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=128), nullable=True),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("quota_observations")
    op.drop_table("inference_deployments")
    op.drop_table("trust_envelopes")
    op.drop_table("reality_anchors")
    op.drop_table("task_capsules")
    op.drop_table("projects")
