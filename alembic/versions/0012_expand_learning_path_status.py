"""Expand learning_paths.status column length to 64 chars for coverage-aware statuses.

Revision ID: 0012_expand_learning_path_status
Revises: 0011_learning_path_v2_metadata
Create Date: 2026-08-08 18:05:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "0012_expand_learning_path_status"
down_revision = "0011_learning_path_v2_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learning_paths") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=64),
            existing_nullable=False,
            existing_server_default="DRAFT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    result = bind.execute(sa.text("SELECT status FROM learning_paths WHERE LENGTH(status) > 20 LIMIT 1"))
    if result.first() is not None:
        raise RuntimeError("Cannot downgrade: learning_paths table contains status values longer than 20 characters.")
    with op.batch_alter_table("learning_paths") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=64),
            type_=sa.String(length=20),
            existing_nullable=False,
            existing_server_default="DRAFT",
        )
