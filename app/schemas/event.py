from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

EVENT_TYPES = {"PAGE_VIEW", "COURSE_IMPRESSION", "COURSE_VIEW", "COURSE_CLICK", "SEARCH", "FILTER_CHANGE", "DWELL", "RECOMMENDATION_IMPRESSION", "RECOMMENDATION_CLICK", "RECOMMENDATION_DISMISS", "RECOMMENDATION_FEEDBACK_OPENED", "RECOMMENDATION_REJECTED", "RECOMMENDATION_REPLACEMENT_SHOWN"}


class EventInput(BaseModel):
    event_id: str | None = Field(default=None, max_length=36)
    schema_version: int = Field(default=1, ge=1, le=10)
    event_type: str
    course_id: str | None = None
    search_query: str | None = Field(default=None, max_length=200)
    page_path: str | None = Field(default=None, max_length=500)
    metadata: dict = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    occurred_at: datetime | None = None

    @field_validator("event_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.upper()
        if value not in EVENT_TYPES:
            raise ValueError("invalid_event_type")
        return value

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(UUID(value))
        except ValueError as exc:
            raise ValueError("invalid_event_id") from exc

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported_schema_version")
        return value

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: dict) -> dict:
        if len(str(value).encode()) > 4096:
            raise ValueError("metadata_too_large")
        return value

    def normalized_time(self) -> datetime:
        value = self.occurred_at or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def normalized_search(self) -> str | None:
        return " ".join(self.search_query.split()) if self.search_query else None


class EventBatch(BaseModel):
    events: list[EventInput] = Field(min_length=1, max_length=50)
