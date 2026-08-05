"""user profile details columns"""

from alembic import op
import sqlalchemy as sa


revision = "0009_user_profile_details"
down_revision = "0008_learning_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("headline", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("location", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("primary_domain", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "primary_domain")
    op.drop_column("users", "location")
    op.drop_column("users", "bio")
    op.drop_column("users", "headline")
