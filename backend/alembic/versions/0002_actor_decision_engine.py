"""add strategic actor parameters and decision/action tables"""
from alembic import op
import sqlalchemy as sa

revision = "0002_actor_decision_engine"
down_revision = "0001_world_state"
branch_labels = None
depends_on = None

def upgrade() -> None:
    for name, default in [("risk_tolerance", "0.5"), ("strategic_patience", "0.5"), ("escalation_threshold", "0.6"), ("information_quality", "0.65")]:
        op.add_column("actors", sa.Column(name, sa.Float(), nullable=False, server_default=default))
    op.create_table("decisions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("simulation_id", sa.String(128), sa.ForeignKey("simulation_runs.id")),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("selected_action", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning_factors", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("information_state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("actions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("decision_id", sa.String(128), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="proposed"),
        sa.Column("effects", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))

def downgrade() -> None:
    op.drop_table("actions")
    op.drop_table("decisions")
    for name in ["information_quality", "escalation_threshold", "strategic_patience", "risk_tolerance"]:
        op.drop_column("actors", name)
