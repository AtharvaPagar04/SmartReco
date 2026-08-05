from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class LearningPath(TimestampMixin, Base):
    __tablename__ = "learning_paths"
    __table_args__ = (
        Index("ix_learning_path_user_time", "user_id", "created_at"),
        Index("ix_learning_path_status_time", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", server_default="DRAFT", nullable=False)
    primary_domain: Mapped[str] = mapped_column(String(40), nullable=False)
    secondary_domains_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    goal_code: Mapped[str] = mapped_column(String(50), nullable=False)
    level_code: Mapped[str] = mapped_column(String(40), nullable=False)
    learning_preferences_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    target_weeks: Mapped[int | None] = mapped_column(Integer)
    budget_type: Mapped[str] = mapped_column(String(20), nullable=False)
    budget_scope: Mapped[str] = mapped_column(String(10), default="PATH", nullable=False)
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    path_length_preference: Mapped[str] = mapped_column(String(20), nullable=False)
    optional_instruction: Mapped[str | None] = mapped_column(String(500))
    input_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    profile_hash: Mapped[str | None] = mapped_column(String(64))
    used_mesh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    estimated_total_hours: Mapped[int | None] = mapped_column(Integer)
    estimated_weeks: Mapped[int | None] = mapped_column(Integer)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items = relationship("LearningPathItem", back_populates="learning_path", cascade="all, delete-orphan", order_by="LearningPathItem.position")
    generation_runs = relationship("LearningPathGenerationRun", back_populates="learning_path", cascade="all, delete-orphan")


class LearningPathItem(TimestampMixin, Base):
    __tablename__ = "learning_path_items"
    __table_args__ = (
        UniqueConstraint("learning_path_id", "position", name="uq_learning_path_item_position"),
        UniqueConstraint("learning_path_id", "course_id", name="uq_learning_path_item_course"),
        Index("ix_learning_path_item_course", "course_id"),
        Index("ix_learning_path_item_path_position", "learning_path_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    learning_path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_label: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    how_it_prepares_next: Mapped[str] = mapped_column(Text, nullable=False)
    skills_gained_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    estimated_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    learning_path = relationship("LearningPath", back_populates="items")
    course = relationship("Course")


class LearningPathGenerationRun(TimestampMixin, Base):
    __tablename__ = "learning_path_generation_runs"
    __table_args__ = (Index("ix_learning_path_generation_path_time", "learning_path_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    learning_path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    learning_path = relationship("LearningPath", back_populates="generation_runs")
