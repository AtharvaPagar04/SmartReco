from decimal import Decimal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.constants import COURSE_CATEGORIES, DIFFICULTIES


class CourseForm(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    slug: str | None = Field(default=None, max_length=200)
    short_description: str = Field(min_length=10, max_length=500)
    description: str = Field(min_length=20, max_length=10000)
    category: str = Field(min_length=2, max_length=80)
    tags: str = Field(default="", max_length=500)
    price: Decimal = Field(ge=0, le=100000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    difficulty: str
    instructor: str = Field(min_length=2, max_length=120)
    duration_minutes: int = Field(gt=0, le=10000)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    is_featured: bool = False
    is_active: bool = True

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, value: str) -> str:
        value = value.upper()
        if value not in DIFFICULTIES:
            raise ValueError("Choose a valid difficulty")
        return value

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        value = " ".join(value.split())
        if value not in COURSE_CATEGORIES:
            raise ValueError("Choose a valid course category")
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("thumbnail_url")
    @classmethod
    def safe_thumbnail(cls, value: str | None) -> str | None:
        if value and not value.lower().startswith(("https://", "http://")):
            raise ValueError("Thumbnail URL must use HTTP or HTTPS")
        return value

    @field_validator("slug")
    @classmethod
    def clean_slug(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    def tag_list(self) -> list[str]:
        return list(dict.fromkeys(t.strip()[:40] for t in self.tags.split(",") if t.strip()))[:20]
