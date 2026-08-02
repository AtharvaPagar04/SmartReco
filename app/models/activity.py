from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_event_id", "event_id", unique=True),
        Index("ix_activity_user_time", "user_id", "occurred_at"),
        Index("ix_activity_session_time", "session_id", "occurred_at"),
        Index("ix_activity_course_time", "course_id", "occurred_at"),
        Index("ix_activity_type_time", "event_type", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    course_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("courses.id"))
    search_query: Mapped[str | None] = mapped_column(String(200))
    page_path: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="events")
    course = relationship("Course", back_populates="events")
