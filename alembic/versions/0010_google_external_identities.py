"""add Google external identities and nullable password hashes"""

from alembic import op
import sqlalchemy as sa


revision = "0010_google_external_identities"
down_revision = "0009_user_profile_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_link_time", sa.String(length=320), nullable=False),
        sa.Column("display_name_at_link_time", sa.String(length=120), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_external_identity_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
    )
    op.create_index("ix_external_identity_user", "external_identities", ["user_id"])
    op.create_index("ix_external_identity_email", "external_identities", ["email_at_link_time"])
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("password_hash", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL")).scalar_one():
        raise RuntimeError("Cannot downgrade while Google-only users have no password hash")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("password_hash", existing_type=sa.Text(), nullable=False)
    op.drop_index("ix_external_identity_email", table_name="external_identities")
    op.drop_index("ix_external_identity_user", table_name="external_identities")
    op.drop_table("external_identities")
