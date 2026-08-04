from datetime import datetime, timezone
import pytest
from types import SimpleNamespace
from sqlalchemy import select

from app.services.recommendation_ranking_service import rank_candidates
from app.services.recommendation_retrieval_service import RecommendationCandidate


def test_feedback_adjustments_prefer_practical_lower_cost_next_steps():
    advanced = SimpleNamespace(id="advanced", title="Advanced Agents", category="AI", tags=["agents"], difficulty="ADVANCED", price=80, is_featured=False, tools_used=[], what_you_will_learn=["theory"], final_project=None, curriculum=[])
    practical = SimpleNamespace(id="practical", title="Practical Agents", category="AI", tags=["agents"], difficulty="INTERMEDIATE", price=0, is_featured=False, tools_used=["Python"], what_you_will_learn=["project"], final_project=None, curriculum=[])
    profile = {"recommendation_feedback": {"preferred_difficulty_shift": -1, "prefers_practical": True, "price_sensitivity": 1.0}, "top_categories": [{"name": "AI"}], "top_tags": [], "top_search_terms": [], "completed_courses": [], "enrolled_courses": [], "recently_viewed_courses": [], "signal_summary": {}}
    ranked = rank_candidates([RecommendationCandidate(course=advanced, semantic_score=.8), RecommendationCandidate(course=practical, semantic_score=.8)], profile, limit=2)
    assert ranked[0].course.id == "practical"


def test_feedback_is_a_bounded_refinement_of_the_base_profile_score():
    course = SimpleNamespace(id="course", title="Applied AI", category="AI", tags=["agents"], difficulty="INTERMEDIATE", price=0, is_featured=False, tools_used=["Python"], what_you_will_learn=["project"], final_project=None, curriculum=[])
    profile = {"recommendation_feedback": {"preferred_difficulty_shift": 1, "prefers_practical": True}, "top_categories": [{"name": "AI"}], "top_tags": [], "top_search_terms": [], "completed_courses": [{"course_id": "foundation", "title": "Python", "category": "AI", "difficulty": "BEGINNER", "tags": ["agents"]}], "enrolled_courses": [], "recently_viewed_courses": [], "signal_summary": {}}
    candidate = RecommendationCandidate(course=course, semantic_score=.7)
    rank_candidates([candidate], profile, limit=1)
    assert candidate.base_personalized_score > 0
    assert abs(candidate.deterministic_score - candidate.base_personalized_score) <= .0625


def test_topic_rejection_keeps_other_profile_interests_in_contention():
    web = SimpleNamespace(id="web", title="Web Development", category="Web", tags=["frontend"], difficulty="INTERMEDIATE", price=0, is_featured=False, tools_used=["HTML"], what_you_will_learn=["project"], final_project=None, curriculum=[])
    ml = SimpleNamespace(id="ml", title="Applied Machine Learning", category="Machine Learning", tags=["python"], difficulty="INTERMEDIATE", price=0, is_featured=False, tools_used=["Python"], what_you_will_learn=["project"], final_project=None, curriculum=[])
    profile = {"recommendation_feedback": {"disliked_categories": {"web": 1.0}, "disliked_tags": {"frontend": 1.0}}, "top_categories": [{"name": "Machine Learning", "score": 1.0}], "top_tags": [{"name": "python", "score": 1.0}], "top_search_terms": [], "completed_courses": [], "enrolled_courses": [], "recently_viewed_courses": [], "signal_summary": {}}
    ranked = rank_candidates([RecommendationCandidate(course=web, semantic_score=.7), RecommendationCandidate(course=ml, semantic_score=.7)], profile, limit=2)
    assert ranked[0].course.id == "ml"


def test_mesh_two_results_backfilled_to_three():
    from app.services.recommendation_copy_service import RecommendationOutput, RecommendationOutputItem, validate_recommendation
    c1 = SimpleNamespace(id="c1", title="C1", category="AI", difficulty="BEGINNER", tags=["a"], price=0, is_featured=False, tools_used=[], what_you_will_learn=[], final_project=None, curriculum=[])
    c2 = SimpleNamespace(id="c2", title="C2", category="AI", difficulty="BEGINNER", tags=["b"], price=0, is_featured=False, tools_used=[], what_you_will_learn=[], final_project=None, curriculum=[])
    c3 = SimpleNamespace(id="c3", title="C3", category="AI", difficulty="BEGINNER", tags=["c"], price=0, is_featured=False, tools_used=[], what_you_will_learn=[], final_project=None, curriculum=[])

    cand1 = RecommendationCandidate(course=c1, evidence={"evidence": [{"evidence_id": "ev1", "type": "ENGAGED_CATEGORY", "label": "AI"}]})
    cand2 = RecommendationCandidate(course=c2, evidence={"evidence": [{"evidence_id": "ev2", "type": "ENGAGED_CATEGORY", "label": "AI"}]})
    cand3 = RecommendationCandidate(course=c3, evidence={"evidence": [{"evidence_id": "ev3", "type": "ENGAGED_CATEGORY", "label": "AI"}]})

    # Mesh returns only 2 valid items
    mesh_output = RecommendationOutput(
        headline="Mesh Output",
        narrative="This narrative is long enough to pass validation for RecommendationOutput schema.",
        learning_direction="AI",
        recommendations=[
            RecommendationOutputItem(course_id="c1", reason="This reason is long enough to pass validation 1", evidence=["ev1"]),
            RecommendationOutputItem(course_id="c2", reason="This reason is long enough to pass validation 2", evidence=["ev2"]),
        ],
    )

    validated = validate_recommendation(mesh_output, [cand1, cand2, cand3], max_items=3)
    assert len(validated.recommendations) == 3
    assert [item.course_id for item in validated.recommendations] == ["c1", "c2", "c3"]


def test_view_service_maintains_three_slots_on_enrolled_filtering():
    from app.models import Course, RecommendationItem, RecommendationRun
    from app.services.recommendation_view_service import build_recommendation_view

    run = RecommendationRun(id="run1", headline="Headline", narrative="Narrative")
    c1 = Course(id="c1", title="C1", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c1")
    c2 = Course(id="c2", title="C2", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c2")
    c3 = Course(id="c3", title="C3", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c3")

    item1 = RecommendationItem(id="i1", run_id="run1", course_id="c1", rank=1, reason="Reason 1", course=c1)
    item2 = RecommendationItem(id="i2", run_id="run1", course_id="c2", rank=2, reason="Reason 2", course=c2)
    item3 = RecommendationItem(id="i3", run_id="run1", course_id="c3", rank=3, reason="Reason 3", course=c3)
    run.items = [item1, item2, item3]

    # Course c2 is enrolled/excluded
    view = build_recommendation_view(run, excluded_course_ids={"c2"})
    assert len(view["recommendation_slots"]) == 3
    assert view["recommendation_slots"][0]["state"] == "ACTIVE"
    assert view["recommendation_slots"][0]["rank"] == 1
    assert view["recommendation_slots"][1]["state"] == "REPLACEMENT_PENDING"
    assert view["recommendation_slots"][1]["rank"] == 2
    assert view["recommendation_slots"][2]["state"] == "ACTIVE"
    assert view["recommendation_slots"][2]["rank"] == 3


def test_view_service_handles_limited_catalog_with_unavailable_slot():
    from app.models import Course, RecommendationItem, RecommendationRun
    from app.services.recommendation_view_service import build_recommendation_view

    run = RecommendationRun(id="run1", headline="Headline", narrative="Narrative")
    c1 = Course(id="c1", title="C1", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c1")
    c2 = Course(id="c2", title="C2", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c2")

    item1 = RecommendationItem(id="i1", run_id="run1", course_id="c1", rank=1, reason="Reason 1", course=c1)
    item2 = RecommendationItem(id="i2", run_id="run1", course_id="c2", rank=2, reason="Reason 2", course=c2)
    run.items = [item1, item2]

    view = build_recommendation_view(run, total_eligible_courses=2)
    assert len(view["recommendation_slots"]) == 3
    assert view["recommendation_slots"][0]["state"] == "ACTIVE"
    assert view["recommendation_slots"][1]["state"] == "ACTIVE"
    assert view["recommendation_slots"][2]["state"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_create_feedback_replacement_backfills_legacy_two_item_run(db_session, regular_user, course):
    import uuid
    from app.models import Course, RecommendationItem, RecommendationRun, UserInterestProfile
    from app.services.recommendation_replacement_service import create_feedback_replacement

    # Create profile
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    profile = UserInterestProfile(user_id=regular_user.id, profile_json={"learning_direction": "practical learning"}, profile_hash="hash123", window_started_at=now, window_ended_at=now, generated_at=now)
    db_session.add(profile)

    # Create additional active catalog courses
    c2 = Course(id=str(uuid.uuid4()), title="Course 2", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c2", short_description="Short desc 2", description="Full desc 2", instructor="Instructor 2", duration_minutes=60)
    c3 = Course(id=str(uuid.uuid4()), title="Course 3", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c3", short_description="Short desc 3", description="Full desc 3", instructor="Instructor 3", duration_minutes=60)
    c4 = Course(id=str(uuid.uuid4()), title="Course 4", category="AI", difficulty="BEGINNER", price=0, currency="USD", is_active=True, slug="c4", short_description="Short desc 4", description="Full desc 4", instructor="Instructor 4", duration_minutes=60)
    db_session.add_all([c2, c3, c4])
    await db_session.commit()

    # Legacy 2-item run
    run = RecommendationRun(id=str(uuid.uuid4()), user_id=regular_user.id, profile_hash="hash123", trigger_type="TEST", status="SUCCEEDED", headline="Legacy Run", narrative="Legacy Narrative for recommendation output")
    db_session.add(run)
    item1 = RecommendationItem(id=str(uuid.uuid4()), run_id=run.id, user_id=regular_user.id, course_id=course.id, rank=1, reason="Reason 1 for legacy item 1", cta_label="Explore")
    item2 = RecommendationItem(id=str(uuid.uuid4()), run_id=run.id, user_id=regular_user.id, course_id=c2.id, rank=2, reason="Reason 2 for legacy item 2", cta_label="Explore")
    db_session.add_all([item1, item2])
    await db_session.commit()

    new_run = await create_feedback_replacement(db_session, regular_user.id, item2.id)
    assert new_run is not None
    items = (await db_session.scalars(select(RecommendationItem).where(RecommendationItem.run_id == new_run.id))).all()
    assert len(items) == 3
    assert [i.rank for i in sorted(items, key=lambda x: x.rank)] == [1, 2, 3]


