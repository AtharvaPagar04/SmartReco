"""course enrollments"""

from alembic import op
import sqlalchemy as sa

revision = "0004_enrollments"
down_revision = "0003_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),
    )
    op.create_index("ix_enrollment_user_id", "enrollments", ["user_id"])
    op.create_index("ix_enrollment_course_id", "enrollments", ["course_id"])
    op.create_index("ix_enrollment_user_status", "enrollments", ["user_id", "status"])
    op.create_index("ix_enrollment_user_accessed", "enrollments", ["user_id", "last_accessed_at"])


def downgrade() -> None:
    op.drop_index("ix_enrollment_user_accessed", table_name="enrollments", if_exists=True)
    op.drop_index("ix_enrollment_user_status", table_name="enrollments", if_exists=True)
    op.drop_index("ix_enrollment_course_id", table_name="enrollments", if_exists=True)
    op.drop_index("ix_enrollment_user_id", table_name="enrollments", if_exists=True)
    op.drop_table("enrollments")
