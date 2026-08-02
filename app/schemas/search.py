from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SearchSuggestion(BaseModel):
    type: Literal["course", "category", "tag", "instructor"]
    label: str
    value: str
    course_slug: str | None = None
    category: str | None = None


class SearchSuggestionsResponse(BaseModel):
    query: str
    suggestions: list[SearchSuggestion]


class RecentSearchItem(BaseModel):
    query: str
    searched_at: datetime


class RecentSearchesResponse(BaseModel):
    recent_searches: list[RecentSearchItem]
