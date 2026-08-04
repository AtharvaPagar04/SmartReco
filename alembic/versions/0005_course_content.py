"""course content and curriculum details"""

from alembic import op
import sqlalchemy as sa

revision = "0005_course_content"
down_revision = "0004_enrollments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("what_you_will_learn", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("prerequisites", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("target_audience", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("tools_used", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("estimated_effort", sa.String(120), nullable=True))
    op.add_column("courses", sa.Column("curriculum", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("courses", sa.Column("final_project", sa.JSON(), nullable=True))
    op.add_column("courses", sa.Column("instructor_bio", sa.Text(), nullable=True))
    op.add_column("courses", sa.Column("faqs", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("courses", "faqs")
    op.drop_column("courses", "instructor_bio")
    op.drop_column("courses", "final_project")
    op.drop_column("courses", "curriculum")
    op.drop_column("courses", "estimated_effort")
    op.drop_column("courses", "tools_used")
    op.drop_column("courses", "target_audience")
    op.drop_column("courses", "prerequisites")
    op.drop_column("courses", "what_you_will_learn")
