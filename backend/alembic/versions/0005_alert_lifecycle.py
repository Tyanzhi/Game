"""extend operations alert lifecycle

Revision ID: 0005_alert_lifecycle
Revises: 0004_alert_operations
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_alert_lifecycle"
down_revision = "0004_alert_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_states",
        sa.Column("first_seen_tick", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "alert_states",
        sa.Column("last_seen_tick", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "alert_states",
        sa.Column("last_severity", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "alert_states",
        sa.Column("last_title", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "alert_states",
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "alert_states",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_states", "resolved_at")
    op.drop_column("alert_states", "occurrence_count")
    op.drop_column("alert_states", "last_title")
    op.drop_column("alert_states", "last_severity")
    op.drop_column("alert_states", "last_seen_tick")
    op.drop_column("alert_states", "first_seen_tick")
