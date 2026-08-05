"""guided personalized learning paths"""

from alembic import op
import sqlalchemy as sa


revision = "0008_learning_paths"
down_revision = "0007_recommendation_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "learning_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("primary_domain", sa.String(40), nullable=False),
        sa.Column("secondary_domains_json", sa.JSON(), nullable=False),
        sa.Column("goal_code", sa.String(50), nullable=False),
        sa.Column("level_code", sa.String(40), nullable=False),
        sa.Column("learning_preferences_json", sa.JSON(), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=False),
        sa.Column("target_weeks", sa.Integer()),
        sa.Column("budget_type", sa.String(20), nullable=False),
        sa.Column("budget_scope", sa.String(10), nullable=False, server_default="PATH"),
        sa.Column("budget_amount", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("path_length_preference", sa.String(20), nullable=False),
        sa.Column("optional_instruction", sa.String(500)),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_version", sa.String(40), nullable=False, server_default="1"),
        sa.Column("profile_hash", sa.String(64)),
        sa.Column("used_mesh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("estimated_total_hours", sa.Integer()),
        sa.Column("estimated_weeks", sa.Integer()),
        sa.Column("total_price", sa.Numeric(12, 2)),
        sa.Column("generated_at", timestamp),
        sa.Column("archived_at", timestamp),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_path_user_time", "learning_paths", ["user_id", "created_at"])
    op.create_index("ix_learning_path_status_time", "learning_paths", ["status", "created_at"])
    op.create_table(
        "learning_path_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learning_path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage_label", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("how_it_prepares_next", sa.Text(), nullable=False),
        sa.Column("skills_gained_json", sa.JSON(), nullable=False),
        sa.Column("estimated_hours", sa.Integer(), nullable=False),
        sa.Column("price_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("learning_path_id", "position", name="uq_learning_path_item_position"),
        sa.UniqueConstraint("learning_path_id", "course_id", name="uq_learning_path_item_course"),
    )
    op.create_index("ix_learning_path_item_course", "learning_path_items", ["course_id"])
    op.create_index("ix_learning_path_item_path_position", "learning_path_items", ["learning_path_id", "position"])
    op.create_table(
        "learning_path_generation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("learning_path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_fallback", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("started_at", timestamp),
        sa.Column("completed_at", timestamp),
        sa.Column("created_at", timestamp, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", timestamp, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_path_generation_path_time", "learning_path_generation_runs", ["learning_path_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_learning_path_generation_path_time", table_name="learning_path_generation_runs")
    op.drop_table("learning_path_generation_runs")
    op.drop_index("ix_learning_path_item_path_position", table_name="learning_path_items")
    op.drop_index("ix_learning_path_item_course", table_name="learning_path_items")
    op.drop_table("learning_path_items")
    op.drop_index("ix_learning_path_status_time", table_name="learning_paths")
    op.drop_index("ix_learning_path_user_time", table_name="learning_paths")
    op.drop_table("learning_paths")
