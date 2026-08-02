from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.config import settings


class VectorOutbox(TimestampMixin, Base):
    __tablename__ = "vector_outbox"
    __table_args__ = (
        Index("ix_outbox_status_next", "status", "next_attempt_at"),
        Index("ix_outbox_course", "course_id"),
        Index("ix_outbox_processing", "processing_started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    course_version: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(160), default=lambda: settings.mesh_embedding_model, nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=lambda: settings.vector_size, nullable=False)
    embedding_schema_version: Mapped[int] = mapped_column(Integer, default=lambda: settings.embedding_schema_version, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course = relationship("Course", back_populates="outbox_rows")
