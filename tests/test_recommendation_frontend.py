from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Course, RecommendationItem, RecommendationRun, User
from app.services.recommendation_view_service import build_recommendation_view
from tests.conftest import csrf


def test_recommendations_template_has_structured_responsive_sections():
    source = (Path(__file__).parents[1] / "app/templates/account/recommendations.html").read_text()
    for class_name in ("recommendations-page", "learning-context-panel", "continue-learning-grid", "recommendation-grid", "recommendation-explanation", "recommendation-benefit", "recommendation-evidence__chips"):
        assert class_name in source
    assert "recommendation.items" not in source
    assert "data-recommendation-click" in source
    assert source.count('name="csrf_token"') >= 1
    assert 'action="/api/recommendations/items/{{ item[\'item_id\'] }}/feedback"' in source
    assert "Why doesn’t this course fit?" in source
    assert "<fieldset" in source and "<legend" in source
    assert "recommendation-feedback-overlay" in source
    assert 'class="recommendation-feedback-overlay"' in source
    assert 'aria-expanded="false"' in source
    assert 'aria-controls="feedback-overlay-' in source
    assert 'role="dialog"' in source
    assert "data-feedback-details" not in source
    assert "feedback-replacement-status" in (Path(__file__).parents[1] / "app/static/js/recommendation-feedback.js").read_text()
    reasons = (Path(__file__).parents[1] / "app/repositories/recommendation_feedback.py").read_text()
    for reason in ("ALREADY_KNOW", "TOO_ADVANCED", "TOO_BASIC", "NOT_INTERESTED_TOPIC", "PREFER_MORE_PRACTICAL", "TOO_EXPENSIVE", "NOT_RELEVANT_NOW", "OTHER"):
        assert reason in reasons
    script = (Path(__file__).parents[1] / "app/static/js/recommendation-feedback.js").read_text()
    css = (Path(__file__).parents[1] / "app/static/css/app.css").read_text()
    assert "overlay.hidden = true" in script
    assert ".recommendation-feedback-overlay[hidden]" in css
    assert ".recommendation-feedback-overlay:not([hidden])" in css
    assert "aria-live" in script
    assert 'name="csrf_token"' in (Path(__file__).parents[1] / "app/templates/catalog/_course_action.html").read_text()


async def login_client(client, user, password="StudentPass123!"):
    login_page = await client.get("/login")
    token = csrf(login_page.text)
    await client.post("/login", data={"email": user.email, "password": password, "csrf_token": token})


@pytest.mark.asyncio
async def test_build_recommendation_view_dict_structure(db_session, regular_user, course):
    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="Test Headline",
        narrative="Test Narrative Explanation",
    )
    db_session.add(run)
    item = RecommendationItem(
        id=str(uuid4()),
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        reason="Test Reason",
        cta_label="Explore",
    )
    item.course = course
    run.items = [item]
    await db_session.commit()

    view = build_recommendation_view(run)
    assert view is not None
    assert isinstance(view, dict)
    assert view["headline"] == "Test Headline"
    assert view["narrative"] == "Test Narrative Explanation"
    assert view["is_fallback"] is False
    assert len(view["items"]) == 1
    assert view["items"][0]["course"]["id"] == course.id
    assert view["items"][0]["reason"] == "Test Reason"


@pytest.mark.asyncio
async def test_recommendations_page_renders_succeeded_run(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="Custom Learning Path Headline",
        narrative="Deep narrative explanation",
    )
    db_session.add(run)
    item = RecommendationItem(
        id=str(uuid4()),
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        reason="Recommended due to Machine Learning interest",
        cta_label="Explore course",
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.get("/recommendations")
    assert res.status_code == 200
    assert "builtin_function_or_method" not in res.text
    assert "Custom Learning Path Headline" in res.text
    assert "Deep narrative explanation" in res.text
    assert course.title in res.text
    assert "Recommended due to Machine Learning interest" in res.text
    assert "data-recommendation-item" in res.text
    assert f'data-recommendation-run-id="{run.id}"' in res.text


@pytest.mark.asyncio
async def test_recommendations_page_renders_fallback_succeeded_run(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="FALLBACK_SUCCEEDED",
        headline="Fallback Learning Path Headline",
        narrative="Fallback explanation",
    )
    db_session.add(run)
    item = RecommendationItem(
        id=str(uuid4()),
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        reason="Popular course fallback",
        cta_label="Explore course",
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.get("/recommendations")
    assert res.status_code == 200
    assert "builtin_function_or_method" not in res.text
    assert "Fallback Learning Path Headline" in res.text
    assert "Built from your recent activity" in res.text
    assert course.title in res.text


@pytest.mark.asyncio
async def test_status_filtering_ignores_running_failed_superseded(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    for status in ["RUNNING", "FAILED", "SUPERSEDED"]:
        run = RecommendationRun(
            id=str(uuid4()),
            user_id=regular_user.id,
            profile_hash="hash123",
            trigger_type="TEST",
            status=status,
            headline=f"Ignore {status}",
            narrative="Should not display",
        )
        db_session.add(run)
    await db_session.commit()

    res = await client.get("/recommendations")
    assert res.status_code == 200
    assert "Ignore RUNNING" not in res.text
    assert "Ignore FAILED" not in res.text
    assert "Ignore SUPERSEDED" not in res.text
    assert "Nothing personalized yet" in res.text
    assert "Generate my recommendations" in res.text


@pytest.mark.asyncio
async def test_empty_state_renders_manual_generate_button(client, regular_user):
    await login_client(client, regular_user)
    res = await client.get("/recommendations")
    assert res.status_code == 200
    assert "Nothing personalized yet" in res.text
    assert "You already have enough learning activity to request a personalized path." in res.text
    assert "Generate my recommendations" in res.text
    assert "Browse courses" in res.text

    refresh_res = await client.post("/api/recommendations/refresh", headers={"X-CSRF-Token": csrf(res.text)})
    assert refresh_res.status_code == 202
    data = refresh_res.json()
    assert data["status"] == "accepted"
    assert data["message"] == "Recommendation refresh queued."


@pytest.mark.asyncio
async def test_authorization_prevents_user_cross_access(client, regular_user, db_session, course):
    other_user = User(
        id=str(uuid4()),
        email="other@example.com",
        full_name="Other User",
        password_hash="hash",
        role="MEMBER",
    )
    db_session.add(other_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=other_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="Secret Other User Path",
        narrative="Private data",
    )
    db_session.add(run)
    await db_session.commit()

    await login_client(client, regular_user)
    res = await client.get("/recommendations")
    assert res.status_code == 200
    assert "Secret Other User Path" not in res.text


@pytest.mark.asyncio
async def test_anonymous_user_redirected_to_login(client):
    client.cookies.clear()
    res = await client.get("/recommendations", follow_redirects=False)
    assert res.status_code in (403, 302, 303, 307)



@pytest.mark.asyncio
async def test_navbar_navigation_links(client, regular_user):
    # Anonymous navbar
    client.cookies.clear()
    res_anon = await client.get("/")
    assert "/recommendations" not in res_anon.text

    # Logged in navbar

    await login_client(client, regular_user)
    res_auth = await client.get("/")
    assert 'href="/recommendations"' in res_auth.text and 'For you' in res_auth.text
    assert 'href="/account"' in res_auth.text and 'Account' in res_auth.text





@pytest.mark.asyncio
async def test_account_page_does_not_render_recommendation_summary(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="Dashboard Machine Learning Focus",
        narrative="Summary narrative for dashboard",
    )
    db_session.add(run)
    await db_session.commit()

    res = await client.get("/account")
    assert res.status_code == 200
    assert "recommendation-panel" not in res.text
    assert "Dashboard Machine Learning Focus" not in res.text


@pytest.mark.asyncio
async def test_api_current_returns_canonical_payload(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="API Recommendation Headline",
        narrative="API Narrative",
    )
    db_session.add(run)
    item = RecommendationItem(
        id=str(uuid4()),
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        reason="API Reason",
        cta_label="Explore API",
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.get("/api/recommendations/current")
    assert res.status_code == 200
    json_data = res.json()
    assert "recommendation" in json_data
    rec = json_data["recommendation"]
    assert rec["run_id"] == run.id
    assert rec["headline"] == "API Recommendation Headline"
    assert rec["items"][0]["course"]["id"] == course.id
    assert "profile_json" not in rec
    assert "cache_key" not in rec


@pytest.mark.asyncio
async def test_dismissal_removes_item_from_view(client, regular_user, db_session, course):
    await login_client(client, regular_user)

    run = RecommendationRun(
        id=str(uuid4()),
        user_id=regular_user.id,
        profile_hash="hash123",
        trigger_type="TEST",
        status="SUCCEEDED",
        headline="Dismissal Test Headline",
        narrative="Testing item dismissal",
    )
    db_session.add(run)
    item = RecommendationItem(
        id=str(uuid4()),
        run_id=run.id,
        user_id=regular_user.id,
        course_id=course.id,
        rank=1,
        reason="Will be dismissed",
        cta_label="Explore",
    )
    db_session.add(item)
    await db_session.commit()

    page_res = await client.get("/recommendations")
    assert course.title in page_res.text

    # Mark item dismissed directly in session
    item_db = await db_session.get(RecommendationItem, item.id)
    item_db.dismissed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db_session.commit()

    after_res = await client.get("/recommendations")
    assert after_res.status_code == 200
    assert course.title not in after_res.text
    assert "Your learning path is being refreshed" in after_res.text
