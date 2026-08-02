"""event identity and embedding lineage"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "0002_data_quality"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    activity_columns = {column["name"] for column in inspector.get_columns("activity_events")}
    if "event_id" not in activity_columns:
        op.add_column("activity_events", sa.Column("event_id", sa.String(36), nullable=True))
    if "schema_version" not in activity_columns:
        op.add_column("activity_events", sa.Column("schema_version", sa.Integer(), nullable=True, server_default="1"))
    rows = bind.execute(sa.text("SELECT id FROM activity_events WHERE event_id IS NULL")).all()
    for row in rows:
        bind.execute(sa.text("UPDATE activity_events SET event_id=:event_id, schema_version=1 WHERE id=:id"), {"event_id": str(uuid4()), "id": row.id})
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("activity_events") as batch:
            batch.alter_column("event_id", nullable=False)
            batch.alter_column("schema_version", nullable=False, server_default="1")
    else:
        op.alter_column("activity_events", "event_id", nullable=False)
        op.alter_column("activity_events", "schema_version", nullable=False, server_default="1")
    if "ix_activity_event_id" not in {index["name"] for index in inspector.get_indexes("activity_events") if index["name"]}:
        op.create_index("ix_activity_event_id", "activity_events", ["event_id"], unique=True)

    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    for name, column in (
        ("indexed_embedding_model", sa.String(160)),
        ("indexed_embedding_dimension", sa.Integer()),
        ("indexed_embedding_schema_version", sa.Integer()),
    ):
        if name not in course_columns:
            op.add_column("courses", sa.Column(name, column, nullable=True))

    outbox_columns = {column["name"] for column in inspector.get_columns("vector_outbox")}
    if "embedding_model" not in outbox_columns:
        op.add_column("vector_outbox", sa.Column("embedding_model", sa.String(160), nullable=True))
    if "embedding_dimension" not in outbox_columns:
        op.add_column("vector_outbox", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    if "embedding_schema_version" not in outbox_columns:
        op.add_column("vector_outbox", sa.Column("embedding_schema_version", sa.Integer(), nullable=True))
    bind.execute(sa.text("UPDATE vector_outbox SET embedding_model='openai/text-embedding-3-small', embedding_dimension=1536, embedding_schema_version=1 WHERE embedding_model IS NULL"))
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("vector_outbox") as batch:
            batch.alter_column("embedding_model", nullable=False)
            batch.alter_column("embedding_dimension", nullable=False)
            batch.alter_column("embedding_schema_version", nullable=False)
    else:
        op.alter_column("vector_outbox", "embedding_model", nullable=False)
        op.alter_column("vector_outbox", "embedding_dimension", nullable=False)
        op.alter_column("vector_outbox", "embedding_schema_version", nullable=False)


def downgrade() -> None:
    op.drop_column("vector_outbox", "embedding_schema_version")
    op.drop_column("vector_outbox", "embedding_dimension")
    op.drop_column("vector_outbox", "embedding_model")
    op.drop_column("courses", "indexed_embedding_schema_version")
    op.drop_column("courses", "indexed_embedding_dimension")
    op.drop_column("courses", "indexed_embedding_model")
    op.drop_index("ix_activity_event_id", table_name="activity_events")
    op.drop_column("activity_events", "schema_version")
    op.drop_column("activity_events", "event_id")
