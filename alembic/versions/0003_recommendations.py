"""recommendation workflow persistence"""

from alembic import op
import sqlalchemy as sa

revision = "0003_recommendations"
down_revision = "0002_data_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "user_interest_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("source_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_event_max_occurred_at", timestamp),
        sa.Column("window_started_at", timestamp, nullable=False),
        sa.Column("window_ended_at", timestamp, nullable=False),
        sa.Column("generated_at", timestamp, nullable=False),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_interest_profile_user", "user_interest_profiles", ["user_id"])
    op.create_index("ix_interest_profile_hash", "user_interest_profiles", ["profile_hash"])
    op.create_table(
        "recommendation_states",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("dirty_since", timestamp), sa.Column("last_profiled_event_at", timestamp),
        sa.Column("last_recommendation_at", timestamp), sa.Column("last_profile_hash", sa.String(64)),
        sa.Column("cooldown_until", timestamp), sa.Column("active_run_id", sa.String(36)),
        sa.Column("lease_expires_at", timestamp), sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", timestamp), sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    for name, column in (("ix_recommendation_state_dirty", "dirty_since"), ("ix_recommendation_state_cooldown", "cooldown_until"), ("ix_recommendation_state_retry", "next_retry_at")):
        op.create_index(name, "recommendation_states", [column])
    op.create_table(
        "recommendation_runs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("user_interest_profiles.id")), sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("profile_hash", sa.String(64), nullable=False), sa.Column("trigger_type", sa.String(30), nullable=False), sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("workflow_version", sa.String(40), nullable=False, server_default="1"), sa.Column("prompt_version", sa.String(40), nullable=False, server_default="1"),
        sa.Column("model_name", sa.String(160)), sa.Column("embedding_model", sa.String(160)), sa.Column("started_at", timestamp), sa.Column("completed_at", timestamp),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("refinement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_semantic_retrieval", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("used_sql_fallback", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("used_llm_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trace_id", sa.String(200)), sa.Column("cache_key", sa.String(128)), sa.Column("error_code", sa.String(80)), sa.Column("error_message", sa.Text()),
        sa.Column("headline", sa.String(200)), sa.Column("narrative", sa.Text()), sa.Column("disclaimer", sa.String(300)), sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()), sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    for name, columns in (("ix_recommendation_run_user_time", ["user_id", "created_at"]), ("ix_recommendation_run_status_time", ["status", "created_at"]), ("ix_recommendation_run_profile_hash", ["profile_hash"]), ("ix_recommendation_run_cache_key", ["cache_key"])):
        op.create_index(name, "recommendation_runs", columns)
    op.create_table(
        "recommendation_items",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("recommendation_runs.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False), sa.Column("deterministic_score", sa.Float(), nullable=False, server_default="0"), sa.Column("semantic_score", sa.Float()), sa.Column("agent_selected", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("retrieval_sources", sa.JSON(), nullable=False), sa.Column("evidence_json", sa.JSON(), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("cta_label", sa.String(80), nullable=False, server_default="Explore the course"), sa.Column("impressed_at", timestamp), sa.Column("clicked_at", timestamp), sa.Column("dismissed_at", timestamp), sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()), sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "course_id", name="uq_recommendation_item_run_course"), sa.UniqueConstraint("run_id", "rank", name="uq_recommendation_item_run_rank"),
    )
    for name, columns in (("ix_recommendation_item_user_time", ["user_id", "created_at"]), ("ix_recommendation_item_course", ["course_id"]), ("ix_recommendation_item_run_rank", ["run_id", "rank"])):
        op.create_index(name, "recommendation_items", columns)
    op.create_table(
        "recommendation_preferences",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True), sa.Column("recommendations_enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("email_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"), sa.Column("digest_hour_local", sa.Integer(), nullable=False, server_default="15"), sa.Column("maximum_items", sa.Integer(), nullable=False, server_default="3"), sa.Column("last_digest_local_date", sa.String(10)), sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()), sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "recommendation_deliveries",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("recommendation_runs.id"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("channel", sa.String(30), nullable=False, server_default="email"), sa.Column("recipient", sa.String(320), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"), sa.Column("scheduled_for", timestamp, nullable=False), sa.Column("sent_at", timestamp), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("next_attempt_at", timestamp), sa.Column("provider_message_id", sa.String(200)), sa.Column("error_code", sa.String(80)), sa.Column("error_message", sa.Text()), sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()), sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_recommendation_delivery_status_time", "recommendation_deliveries", ["status", "scheduled_for"])
    op.create_index("ix_recommendation_delivery_user_time", "recommendation_deliveries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("recommendation_deliveries")
    op.drop_table("recommendation_preferences")
    for name in ("ix_recommendation_item_run_rank", "ix_recommendation_item_course", "ix_recommendation_item_user_time"):
        op.drop_index(name, table_name="recommendation_items")
    op.drop_table("recommendation_items")
    for name in ("ix_recommendation_run_cache_key", "ix_recommendation_run_profile_hash", "ix_recommendation_run_status_time", "ix_recommendation_run_user_time"):
        op.drop_index(name, table_name="recommendation_runs")
    op.drop_table("recommendation_runs")
    for name in ("ix_recommendation_state_retry", "ix_recommendation_state_cooldown", "ix_recommendation_state_dirty"):
        op.drop_index(name, table_name="recommendation_states")
    op.drop_table("recommendation_states")
    op.drop_index("ix_interest_profile_hash", table_name="user_interest_profiles")
    op.drop_index("ix_interest_profile_user", table_name="user_interest_profiles")
    op.drop_table("user_interest_profiles")
