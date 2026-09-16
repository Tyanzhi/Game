"""create initial world state tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_world_state"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("actors",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False, server_default="state"),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.7"), sa.Column("economic_capacity", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("diplomatic_capacity", sa.Float(), nullable=False, server_default="0.7"), sa.Column("security_capacity", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("domestic_pressure", sa.Float(), nullable=False, server_default="0.3"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("countries", sa.Column("id", sa.String(3), primary_key=True), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("actors.id"), unique=True), sa.Column("region", sa.String(100)))
    op.create_table("relationships", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_actor_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False), sa.Column("target_actor_id", sa.String(64), sa.ForeignKey("actors.id"), nullable=False),
        *[sa.Column(x, sa.Float(), nullable=False, server_default="0") for x in ["diplomatic","economic","military","trade","energy","technology","political","information"]],
        sa.UniqueConstraint("source_actor_id", "target_actor_id", name="uq_relationship_pair"))
    op.create_table("events", sa.Column("id", sa.String(128), primary_key=True), sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""), sa.Column("description", sa.Text()), sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"), sa.Column("status", sa.String(32), nullable=False, server_default="FACT"), sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("event_sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("event_id", sa.String(128), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False), sa.Column("source_url", sa.Text(), nullable=False), sa.Column("source_title", sa.String(500), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False), sa.Column("raw_json", sa.JSON(), nullable=False), sa.UniqueConstraint("event_id", "source_id", name="uq_event_source"))
    op.create_table("simulation_runs", sa.Column("id", sa.String(128), primary_key=True), sa.Column("mode", sa.String(32), nullable=False, server_default="live"),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"), sa.Column("query", sa.String(500)), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("events_ingested", sa.Integer(), nullable=False, server_default="0"), sa.Column("events_new", sa.Integer(), nullable=False, server_default="0"), sa.Column("events_deduplicated", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("simulation_ticks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("simulation_id", sa.String(128), sa.ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False), sa.Column("event_ids", sa.JSON(), nullable=False), sa.Column("state_changes", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("world_snapshots", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tick", sa.Integer(), nullable=False), sa.Column("simulation_id", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False), sa.Column("dataset_version", sa.String(64), nullable=False), sa.Column("random_seed", sa.Integer(), nullable=False), sa.Column("state_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    for table in ["world_snapshots", "simulation_ticks", "simulation_runs", "event_sources", "events", "relationships", "countries", "actors"]:
        op.drop_table(table)
