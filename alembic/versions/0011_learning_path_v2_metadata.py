"""Add learning-path V2 generation provenance."""

from alembic import op
import sqlalchemy as sa


revision = "0011_learning_path_v2_metadata"
down_revision = "0010_google_external_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("learning_path_generation_runs", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("learning_path_generation_runs", "metadata_json")
