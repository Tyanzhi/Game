"""add world relationship tables

Revision ID: 0002_relations
Revises: 0001_world_state
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_relations"
down_revision = "0001_world_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "countries",
        sa.Column("id", sa.String(3), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("population", sa.BigInteger()),
        sa.Column("gdp", sa.Float()),
        sa.Column("currency", sa.String(16)),
    )
    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_a_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("actor_b_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False),
        sa.Column("diplomatic", sa.Float(), nullable=False, server_default="0"),
        sa.Column("economic", sa.Float(), nullable=False, server_default="0"),
        sa.Column("military", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trade", sa.Float(), nullable=False, server_default="0"),
        sa.Column("energy", sa.Float(), nullable=False, server_default="0"),
        sa.Column("technology", sa.Float(), nullable=False, server_default="0"),
        sa.Column("political", sa.Float(), nullable=False, server_default="0"),
        sa.Column("information", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_relationships_actor_pair", "relationships", ["actor_a_id", "actor_b_id"], unique=True)
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("mode", sa.String(32), nullable=False, server_default="LIVE"),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("dataset_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("simulation_runs")
    op.drop_index("ix_relationships_actor_pair", table_name="relationships")
    op.drop_table("relationships")
    op.drop_table("countries")
