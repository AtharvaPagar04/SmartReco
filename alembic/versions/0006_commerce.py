"""course commerce and entitlements"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0006_commerce"
down_revision = "0005_course_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_carts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_shopping_cart_user"),
    )
    op.create_table(
        "cart_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("shopping_carts.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cart_id", "course_id", name="uq_cart_item_course"),
    )
    op.create_index("ix_cart_item_cart_id", "cart_items", ["cart_id"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_mode", sa.String(20), nullable=False, server_default="demo"),
        sa.Column("payment_reference", sa.String(160)),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_order_user_created", "orders", ["user_id", "created_at"])
    op.create_index("ix_order_user_status", "orders", ["user_id", "status"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("course_title_snapshot", sa.String(180), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "course_id", name="uq_order_item_course"),
    )
    op.create_index("ix_order_item_order_id", "order_items", ["order_id"])
    op.create_table(
        "course_entitlements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("course_id", sa.String(36), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("order_item_id", sa.String(36), sa.ForeignKey("order_items.id")),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "course_id", name="uq_entitlement_user_course"),
    )
    op.create_index("ix_entitlement_user_id", "course_entitlements", ["user_id"])
    op.create_index("ix_entitlement_course_id", "course_entitlements", ["course_id"])
    op.create_index("ix_entitlement_user_revoked", "course_entitlements", ["user_id", "revoked_at"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT user_id, course_id, started_at FROM enrollments")).mappings()
    for row in rows:
        exists = conn.execute(
            sa.text("SELECT 1 FROM course_entitlements WHERE user_id = :user_id AND course_id = :course_id"),
            {"user_id": row["user_id"], "course_id": row["course_id"]},
        ).first()
        if not exists:
            conn.execute(
                sa.text("INSERT INTO course_entitlements (id, user_id, course_id, source, granted_at) VALUES (:id, :user_id, :course_id, 'LEGACY_ENROLLMENT', :granted_at)"),
                {"id": str(uuid4()), "user_id": row["user_id"], "course_id": row["course_id"], "granted_at": row["started_at"]},
            )


def downgrade() -> None:
    op.drop_index("ix_entitlement_user_revoked", table_name="course_entitlements")
    op.drop_index("ix_entitlement_course_id", table_name="course_entitlements")
    op.drop_index("ix_entitlement_user_id", table_name="course_entitlements")
    op.drop_table("course_entitlements")
    op.drop_index("ix_order_item_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_order_user_status", table_name="orders")
    op.drop_index("ix_order_user_created", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_cart_item_cart_id", table_name="cart_items")
    op.drop_table("cart_items")
    op.drop_table("shopping_carts")
