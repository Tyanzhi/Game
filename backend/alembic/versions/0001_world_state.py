"""create initial world state tables

Revision ID: 0001_world_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_world_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False, server_default="state"),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("economic_capacity", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("diplomatic_capacity", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("security_capacity", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("domestic_pressure", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="FACT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "world_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("simulation_id", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("world_snapshots")
    op.drop_table("events")
    op.drop_table("actors")
