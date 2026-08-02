"""phase 1 foundation"""
from alembic import op
import sqlalchemy as sa

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("full_name", sa.String(120), nullable=False), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.Text(), nullable=False), sa.Column("role", sa.String(16), nullable=False, server_default="USER"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_table("courses", sa.Column("id", sa.String(36), primary_key=True), sa.Column("title", sa.String(180), nullable=False), sa.Column("slug", sa.String(200), nullable=False), sa.Column("short_description", sa.String(500), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("category", sa.String(80), nullable=False), sa.Column("tags", sa.JSON(), nullable=False), sa.Column("price", sa.Numeric(10, 2), nullable=False, server_default="0"), sa.Column("currency", sa.String(3), nullable=False, server_default="USD"), sa.Column("difficulty", sa.String(20), nullable=False), sa.Column("instructor", sa.String(120), nullable=False), sa.Column("duration_minutes", sa.Integer(), nullable=False), sa.Column("thumbnail_url", sa.String(500)), sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("vector_status", sa.String(20), nullable=False, server_default="PENDING"), sa.Column("vector_last_synced_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_courses_slug", "courses", ["slug"], unique=True)
    for name, col in (("ix_courses_category", "category"), ("ix_courses_difficulty", "difficulty"), ("ix_courses_is_active", "is_active"), ("ix_courses_vector_status", "vector_status")):
        op.create_index(name, "courses", [col])
    op.create_table("activity_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")), sa.Column("session_id", sa.String(64), nullable=False), sa.Column("event_type", sa.String(40), nullable=False), sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id")), sa.Column("search_query", sa.String(200)), sa.Column("page_path", sa.String(500)), sa.Column("metadata", sa.JSON(), nullable=False), sa.Column("duration_ms", sa.Integer()), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_activity_events_session_id", "activity_events", ["session_id"])
    op.create_index("ix_activity_user_time", "activity_events", ["user_id", "occurred_at"])
    op.create_index("ix_activity_session_time", "activity_events", ["session_id", "occurred_at"])
    op.create_index("ix_activity_course_time", "activity_events", ["course_id", "occurred_at"])
    op.create_index("ix_activity_type_time", "activity_events", ["event_type", "occurred_at"])
    op.create_table("vector_outbox", sa.Column("id", sa.String(36), primary_key=True), sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False), sa.Column("operation", sa.String(10), nullable=False), sa.Column("course_version", sa.Integer(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("processed_at", sa.DateTime(timezone=True)), sa.Column("processing_started_at", sa.DateTime(timezone=True)))
    op.create_index("ix_vector_outbox_status", "vector_outbox", ["status"])
    op.create_index("ix_outbox_status_next", "vector_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_outbox_course", "vector_outbox", ["course_id"])
    op.create_index("ix_outbox_processing", "vector_outbox", ["processing_started_at"])


def downgrade() -> None:
    op.drop_table("vector_outbox")
    op.drop_table("activity_events")
    op.drop_table("courses")
    op.drop_table("users")
