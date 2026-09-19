"""Merge historical heads and add persistent simulation state.

Both historical branches are retained; missing runtime fields are added without
replacing existing tables or deleting world data.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_runtime_state"
down_revision = ("0002_actor_decision_engine", "0002_relations")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('actors', sa.Column('energy_security', sa.Float(), server_default=sa.text('0.7'), nullable=False))
    op.add_column('actors', sa.Column('trade_resilience', sa.Float(), server_default=sa.text('0.7'), nullable=False))
    op.add_column('actors', sa.Column('technological_capacity', sa.Float(), server_default=sa.text('0.7'), nullable=False))
    op.add_column('simulation_runs', sa.Column('ticks', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('simulation_ticks', sa.Column('seed', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('simulation_ticks', sa.Column('phase_log', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.create_table('actor_perceptions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('simulation_id', sa.String(length=100), nullable=False),
    sa.Column('tick', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=False),
    sa.Column('facts_json', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_actor_perceptions_simulation_id'), 'actor_perceptions', ['simulation_id'], unique=False)
    op.create_index(op.f('ix_actor_perceptions_actor_id'), 'actor_perceptions', ['actor_id'], unique=False)
    op.create_table('effects',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('simulation_id', sa.String(length=100), nullable=False),
    sa.Column('tick', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=100), nullable=False),
    sa.Column('target', sa.String(length=64), nullable=False),
    sa.Column('field', sa.String(length=100), nullable=False),
    sa.Column('delta', sa.Float(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('depth', sa.Integer(), nullable=False),
    sa.Column('mechanism', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_effects_simulation_id'), 'effects', ['simulation_id'], unique=False)
    op.create_table('forecasts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('simulation_id', sa.String(length=100), nullable=False),
    sa.Column('tick', sa.Integer(), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('horizon', sa.Integer(), nullable=False),
    sa.Column('expected', sa.Float(), nullable=False),
    sa.Column('lower', sa.Float(), nullable=False),
    sa.Column('upper', sa.Float(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('drivers', sa.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_forecasts_simulation_id'), 'forecasts', ['simulation_id'], unique=False)
    op.create_table('ingestion_queue',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('dedupe_key', sa.String(length=128), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('error', sa.String(length=2000), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ingestion_queue_status'), 'ingestion_queue', ['status'], unique=False)
    op.create_index(op.f('ix_ingestion_queue_dedupe_key'), 'ingestion_queue', ['dedupe_key'], unique=True)
    op.create_table('world_state_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('simulation_id', sa.String(length=100), nullable=False),
    sa.Column('tick', sa.Integer(), nullable=False),
    sa.Column('state_hash', sa.String(length=128), nullable=False),
    sa.Column('parent_hash', sa.String(length=128), nullable=True),
    sa.Column('dataset_version', sa.String(length=100), nullable=False),
    sa.Column('state_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('simulation_id', 'tick', name='uq_world_state_version')
    )
    op.create_index(op.f('ix_world_state_versions_simulation_id'), 'world_state_versions', ['simulation_id'], unique=False)
    op.create_index(op.f('ix_world_state_versions_state_hash'), 'world_state_versions', ['state_hash'], unique=False)


def downgrade() -> None:
    op.drop_table('world_state_versions')
    op.drop_table('ingestion_queue')
    op.drop_table('forecasts')
    op.drop_table('effects')
    op.drop_table('actor_perceptions')
    op.drop_column('simulation_ticks', 'phase_log')
    op.drop_column('simulation_ticks', 'seed')
    op.drop_column('simulation_runs', 'ticks')
    op.drop_column('actors', 'technological_capacity')
    op.drop_column('actors', 'trade_resilience')
    op.drop_column('actors', 'energy_security')
