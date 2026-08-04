import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker
from app.models import User
from app.services.interest_profile_service import build_or_refresh_profile
from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import retrieve_candidates
from app.services.recommendation_service import generate_recommendation


async def main(args) -> None:
    original_key = settings.mesh_api_key
    original_model = settings.mesh_chat_model
    llm_enabled = bool(original_key and original_model)
    if args.no_llm:
        settings.mesh_api_key = ""
        settings.mesh_chat_model = ""
    async with async_session_maker() as db:
        if not await db.scalar(select(User.id).where(User.id == args.user_id)):
            raise SystemExit("User not found")
        profile = await build_or_refresh_profile(db, args.user_id, force=args.force)
        if args.show_profile:
            print(json.dumps(profile.profile_json, indent=2, default=str))
        candidates, semantic, fallback = await retrieve_candidates(db, profile.profile_json)
        ranked = rank_candidates(candidates, profile.profile_json, limit=settings.recommendation_final_count)
        if args.show_candidates:
            print(json.dumps({"semantic": semantic, "sql_fallback": fallback, "candidates": [{"course_id": item.course.id, "title": item.course.title, "score": item.deterministic_score, "evidence": item.evidence} for item in ranked]}, indent=2, default=str))
        if args.dry_run:
            return
        try:
            status, reference, state = await generate_recommendation(db, args.user_id, trigger_type=args.trigger, force=args.force)
            llm_called = bool(state and state.get("llm_called"))
            print(json.dumps({"status": status, "reference": reference, "llm_enabled": llm_enabled and not args.no_llm, "llm_called": llm_called, "llm": llm_called}, indent=2))
        finally:
            settings.mesh_chat_model = original_model
            settings.mesh_api_key = original_key


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--trigger", default="CLI")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--show-profile", action="store_true")
    parser.add_argument("--show-candidates", action="store_true")
    asyncio.run(main(parser.parse_args()))
