"""add persistent operations alert state

Revision ID: 0004_alert_operations
Revises: 0003_runtime_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_alert_operations"
down_revision = "0003_runtime_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_states",
        sa.Column("alert_id", sa.String(length=128), nullable=False),
        sa.Column("simulation_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="open", nullable=False),
        sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("alert_id"),
    )
    op.create_index(
        op.f("ix_alert_states_simulation_id"),
        "alert_states",
        ["simulation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_states_status"),
        "alert_states",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_states_status"), table_name="alert_states")
    op.drop_index(op.f("ix_alert_states_simulation_id"), table_name="alert_states")
    op.drop_table("alert_states")
