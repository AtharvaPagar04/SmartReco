from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.models.base import Base, TimestampMixin


class UserInterestProfile(TimestampMixin, Base):
    __tablename__ = "user_interest_profiles"
    __table_args__ = (
        Index("ix_interest_profile_user", "user_id"),
        Index("ix_interest_profile_hash", "profile_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_event_max_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecommendationState(TimestampMixin, Base):
    __tablename__ = "recommendation_states"
    __table_args__ = (
        Index("ix_recommendation_state_dirty", "dirty_since"),
        Index("ix_recommendation_state_cooldown", "cooldown_until"),
        Index("ix_recommendation_state_retry", "next_retry_at"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    dirty_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_profiled_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_recommendation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_profile_hash: Mapped[str | None] = mapped_column(String(64))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_run_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecommendationRun(TimestampMixin, Base):
    __tablename__ = "recommendation_runs"
    __table_args__ = (
        Index("ix_recommendation_run_user_time", "user_id", "created_at"),
        Index("ix_recommendation_run_status_time", "status", "created_at"),
        Index("ix_recommendation_run_profile_hash", "profile_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user_interest_profiles.id"))
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160))
    embedding_model: Mapped[str | None] = mapped_column(String(160))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refinement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_semantic_retrieval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_sql_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_llm_fallback: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(200))
    cache_key: Mapped[str | None] = mapped_column(String(128), index=True)
    source_session_id: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(String(200))
    narrative: Mapped[str | None] = mapped_column(Text)
    disclaimer: Mapped[str | None] = mapped_column(String(300))

    items = relationship("RecommendationItem", back_populates="run", cascade="all, delete-orphan")


class RecommendationItem(TimestampMixin, Base):
    __tablename__ = "recommendation_items"
    __table_args__ = (
        UniqueConstraint("run_id", "course_id", name="uq_recommendation_item_run_course"),
        UniqueConstraint("run_id", "rank", name="uq_recommendation_item_run_rank"),
        Index("ix_recommendation_item_user_time", "user_id", "created_at"),
        Index("ix_recommendation_item_course", "course_id"),
        Index("ix_recommendation_item_run_rank", "run_id", "rank"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendation_runs.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    deterministic_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    semantic_score: Mapped[float | None] = mapped_column(Float)
    agent_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrieval_sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    cta_label: Mapped[str] = mapped_column(String(80), default="Explore the course", nullable=False)
    impressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run = relationship("RecommendationRun", back_populates="items")
    course = relationship("Course")


class RecommendationFeedback(TimestampMixin, Base):
    __tablename__ = "recommendation_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_item_id", name="uq_recommendation_feedback_user_item"),
        Index("ix_recommendation_feedback_user_time", "user_id", "created_at"),
        Index("ix_recommendation_feedback_course_reason", "course_id", "reason_code"),
        Index("ix_recommendation_feedback_item", "recommendation_item_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    recommendation_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendation_runs.id"), nullable=False)
    recommendation_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendation_items.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    optional_comment: Mapped[str | None] = mapped_column(String(200))

    course = relationship("Course")


class RecommendationPreference(TimestampMixin, Base):
    __tablename__ = "recommendation_preferences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    recommendations_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session_followup_email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    digest_hour_local: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    maximum_items: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_digest_local_date: Mapped[str | None] = mapped_column(String(10))


class RecommendationDelivery(TimestampMixin, Base):
    __tablename__ = "recommendation_deliveries"
    __table_args__ = (
        Index("ix_recommendation_delivery_status_time", "status", "scheduled_for"),
        Index("ix_recommendation_delivery_user_time", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendation_runs.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="email", nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class SessionFollowupState(TimestampMixin, Base):
    """Tracks post-session recommendation email lifecycle. One row per (user_id, session_id)."""

    __tablename__ = "session_followup_states"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_followup_user_session"),
        Index("ix_session_followup_user", "user_id"),
        Index("ix_session_followup_status_eligible", "status", "eligible_at"),
        Index("ix_session_followup_session", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)

    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lifecycle: PENDING -> PROCESSING -> SENT|SKIPPED_LOW_SIGNAL|SKIPPED_NO_RECS|SKIPPED_COOLDOWN|FAILED
    status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recommendation_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("recommendation_runs.id"))
    recommendation_delivery_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("recommendation_deliveries.id"))

    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meaningful_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    session_signal_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    skip_reason: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
