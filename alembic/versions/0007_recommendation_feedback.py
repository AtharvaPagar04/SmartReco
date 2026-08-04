"""store structured recommendation rejection feedback"""

from alembic import op
import sqlalchemy as sa


revision = "0007_recommendation_feedback"
down_revision = "0006_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recommendation_run_id", sa.String(36), sa.ForeignKey("recommendation_runs.id"), nullable=False),
        sa.Column("recommendation_item_id", sa.String(36), sa.ForeignKey("recommendation_items.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("optional_comment", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "recommendation_item_id", name="uq_recommendation_feedback_user_item"),
    )
    op.create_index("ix_recommendation_feedback_user_time", "recommendation_feedback", ["user_id", "created_at"])
    op.create_index("ix_recommendation_feedback_course_reason", "recommendation_feedback", ["course_id", "reason_code"])
    op.create_index("ix_recommendation_feedback_item", "recommendation_feedback", ["recommendation_item_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_item", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_course_reason", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_user_time", table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
