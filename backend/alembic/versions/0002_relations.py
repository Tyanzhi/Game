"""Retain the historical relations revision without recreating base tables.

The countries, relationships and simulation_runs tables already belong to
0001_world_state. Keep this revision ID so existing revision stamps remain valid.
"""

revision = "0002_relations"
down_revision = "0001_world_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    # The base revision owns these tables and removes them on downgrade.
    pass
