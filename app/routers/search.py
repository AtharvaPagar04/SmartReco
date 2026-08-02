from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.courses import get_search_suggestions
from app.repositories.events import recent_searches_for_user
from app.schemas.search import RecentSearchesResponse, SearchSuggestionsResponse
from app.search import normalize_search_query
from app.security import current_user

router = APIRouter(prefix="/api/search")


@router.get("/suggestions", response_model=SearchSuggestionsResponse)
async def suggestions(response: Response, q: str = Query("", max_length=200), limit: int = Query(8), db: AsyncSession = Depends(get_db)):
    query = normalize_search_query(q)
    response.headers["Cache-Control"] = "no-store"
    return {"query": query, "suggestions": await get_search_suggestions(db, query, min(max(limit, 1), 10))}


@router.get("/recent", response_model=RecentSearchesResponse)
async def recent(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    user = await current_user(request, db)
    if not user:
        return {"recent_searches": []}
    return {"recent_searches": await recent_searches_for_user(db, user.id)}
