"""Session follow-up tracking for post-session recommendation emails.

Revision ID: 0013_session_followup
Revises: 0012_expand_learning_path_status
Create Date: 2026-08-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_session_followup"
down_revision = "0012_expand_learning_path_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "session_followup_states",
        # Primary key: one row per (user_id, session_id) — enforces idempotency.
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        # Timestamps derived from ActivityEvent
        sa.Column("session_started_at", ts),
        sa.Column("last_activity_at", ts),
        sa.Column("eligible_at", ts),
        # Processing lifecycle
        # PENDING → PROCESSING → (SENT | SKIPPED_LOW_SIGNAL | SKIPPED_NO_RECS | SKIPPED_COOLDOWN | FAILED)
        sa.Column("status", sa.String(40), nullable=False, server_default="PENDING"),
        sa.Column("processing_started_at", ts),
        sa.Column("completed_at", ts),
        # Linkage back to the generated RecommendationRun and delivery
        sa.Column("recommendation_run_id", sa.String(36), sa.ForeignKey("recommendation_runs.id")),
        sa.Column("recommendation_delivery_id", sa.String(36), sa.ForeignKey("recommendation_deliveries.id")),
        # Signal metadata (for observability)
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meaningful_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_signal_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("skip_reason", sa.String(80)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        # Standard timestamps
        sa.Column("created_at", ts, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", ts, nullable=False, server_default=sa.func.now()),
        # One follow-up per session — unique constraint on (user_id, session_id)
        sa.UniqueConstraint("user_id", "session_id", name="uq_session_followup_user_session"),
    )
    op.create_index("ix_session_followup_user", "session_followup_states", ["user_id"])
    op.create_index("ix_session_followup_status_eligible", "session_followup_states", ["status", "eligible_at"])
    op.create_index("ix_session_followup_session", "session_followup_states", ["session_id"])
    # Add session_followup_email_enabled to recommendation_preferences
    with op.batch_alter_table("recommendation_preferences") as batch_op:
        batch_op.add_column(sa.Column(
            "session_followup_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))
    # Add source_session_id to recommendation_runs for lineage tracing
    with op.batch_alter_table("recommendation_runs") as batch_op:
        batch_op.add_column(sa.Column("source_session_id", sa.String(64)))


def downgrade() -> None:
    with op.batch_alter_table("recommendation_runs") as batch_op:
        batch_op.drop_column("source_session_id")
    with op.batch_alter_table("recommendation_preferences") as batch_op:
        batch_op.drop_column("session_followup_email_enabled")
    op.drop_index("ix_session_followup_session", table_name="session_followup_states")
    op.drop_index("ix_session_followup_status_eligible", table_name="session_followup_states")
    op.drop_index("ix_session_followup_user", table_name="session_followup_states")
    op.drop_table("session_followup_states")
