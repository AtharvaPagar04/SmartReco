from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    short_description: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    instructor: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    vector_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    vector_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_embedding_model: Mapped[str | None] = mapped_column(String(160))
    indexed_embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    indexed_embedding_schema_version: Mapped[int | None] = mapped_column(Integer)

    # Detailed Course Content
    what_you_will_learn: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    prerequisites: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target_audience: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tools_used: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    estimated_effort: Mapped[str | None] = mapped_column(String(120))
    curriculum: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    final_project: Mapped[dict | None] = mapped_column(JSON)
    instructor_bio: Mapped[str | None] = mapped_column(Text)
    faqs: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)

    @property
    def total_lessons_count(self) -> int:
        if not self.curriculum:
            return 0
        return sum(len(module.get("lessons", [])) for module in self.curriculum if isinstance(module, dict))

    @property
    def total_curriculum_minutes(self) -> int:
        if not self.curriculum:
            return self.duration_minutes
        total = 0
        for module in self.curriculum:
            if isinstance(module, dict):
                for lesson in module.get("lessons", []):
                    if isinstance(lesson, dict):
                        total += int(lesson.get("duration_minutes", 0))
        return total or self.duration_minutes

    events = relationship("ActivityEvent", back_populates="course")
    outbox_rows = relationship("VectorOutbox", back_populates="course")

    def vector_payload(self, *, lineage: dict | None = None) -> dict:
        payload = {
            "course_id": self.id, "title": self.title, "slug": self.slug,
            "category": self.category, "difficulty": self.difficulty,
            "price": float(self.price), "currency": self.currency, "tags": self.tags,
            "instructor": self.instructor, "duration_minutes": self.duration_minutes,
            "is_active": self.is_active, "version": self.version,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if lineage:
            payload.update(lineage)
        return payload

    def embedding_text(self) -> str:
        return (f"Title: {self.title}\nCategory: {self.category}\nDifficulty: {self.difficulty}\n"
                f"Instructor: {self.instructor}\nDuration: {self.duration_minutes} minutes\n"
                f"Tags: {', '.join(self.tags)}\nShort description: {self.short_description}\n"
                f"Description: {self.description}")
