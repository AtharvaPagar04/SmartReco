import pytest
from sqlalchemy import select

from app.models import Course
import scripts.seed_data as seed_script


@pytest.mark.asyncio
async def test_all_seeded_courses_have_rich_content(db_session):
    await seed_script.main(reset=True)
    courses = list((await db_session.execute(select(Course).where(Course.is_active.is_(True)))).scalars())
    assert len(courses) == 30

    forbidden_placeholders = {"lorem ipsum", "lesson 1", "lesson 2", "learn more about this topic"}
    thumbnails = [c.thumbnail_url for c in courses]
    assert all(t and t.startswith("/static/images/courses/") for t in thumbnails), "All courses must have static thumbnail image URLs"
    assert len(set(thumbnails)) == 30, "No thumbnail image URL may be repeated across courses"

    for course in courses:
        assert course.what_you_will_learn, f"Course {course.slug} missing what_you_will_learn"
        assert course.prerequisites, f"Course {course.slug} missing prerequisites"
        assert course.target_audience, f"Course {course.slug} missing target_audience"
        assert course.tools_used, f"Course {course.slug} missing tools_used"
        assert course.estimated_effort, f"Course {course.slug} missing estimated_effort"
        assert course.curriculum, f"Course {course.slug} missing curriculum"
        assert course.final_project, f"Course {course.slug} missing final_project"
        assert course.instructor_bio, f"Course {course.slug} missing instructor_bio"
        assert course.faqs, f"Course {course.slug} missing faqs"

        # Assert no generic placeholder text
        full_text = (
            f"{course.description} {' '.join(course.what_you_will_learn)} "
            f"{course.instructor_bio} {course.final_project.get('description', '')}"
        ).lower()
        for placeholder in forbidden_placeholders:
            assert placeholder not in full_text, f"Forbidden placeholder '{placeholder}' found in {course.slug}"

        # Assert curriculum has modules and lessons with valid attributes
        assert len(course.curriculum) >= 2, f"Course {course.slug} should have at least 2 modules"
        for mod in course.curriculum:
            assert "title" in mod and "lessons" in mod
            assert len(mod["lessons"]) >= 2
            for lesson in mod["lessons"]:
                assert "title" in lesson and "duration_minutes" in lesson
                assert lesson["title"].lower() not in forbidden_placeholders


@pytest.mark.asyncio
async def test_course_detail_page_renders_all_sections(client, db_session):
    await seed_script.main(reset=True)

    res = await client.get("/courses/introduction-to-agentic-ai")
    assert res.status_code == 200
    html = res.text

    # 1. Course overview
    assert "Introduction to Agentic AI" in html
    assert "Course Overview" in html

    # 2. What You Will Learn
    assert "What You Will Learn" in html
    assert "Architect single-agent loops" in html

    # 3. Tools & Tech
    assert "Tools &amp; Technologies Used" in html or "Tools & Technologies Used" in html
    assert "LangGraph" in html

    # 4. Structured Curriculum & Modules
    assert "Structured Curriculum" in html
    assert "Module 1: Foundations of Goal-Driven AI" in html
    assert "Agent vs. Simple Completion Models" in html

    # 5. Practical Project
    assert "Practical Project &amp; Capstone Outcome" in html or "Practical Project & Capstone Outcome" in html
    assert "Autonomous Customer Support Triaging Agent" in html

    # 6. Prerequisites & Audience
    assert "Prerequisites" in html
    assert "Intended Audience" in html

    # 7. Instructor Info
    assert "Maya Iyer" in html
    assert "Instructor Information" in html

    # 8. FAQs
    assert "Frequently Asked Questions" in html
    assert "Do I need access to paid LLM API keys" in html

    # 9. Start Course CTA (unauthenticated)
    assert "Sign in to start" in html
    assert "Start exploring" in html


@pytest.mark.asyncio
async def test_course_detail_authenticated_enrollment_states(client, regular_user, db_session):
    await seed_script.main(reset=True)

    # Login regular user with CSRF token
    login_page = await client.get("/login")
    from tests.conftest import csrf
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login_page.text)})

    # Unenrolled course detail page
    detail_res = await client.get("/courses/introduction-to-agentic-ai")
    assert detail_res.status_code == 200
    assert "Start course" in detail_res.text

    # Enroll user in course
    csrf_token = csrf(detail_res.text)
    enroll_res = await client.post("/courses/introduction-to-agentic-ai/enroll", data={"csrf_token": csrf_token}, follow_redirects=True)
    assert enroll_res.status_code == 200

    # Enrolled course detail page now shows Continue course
    enrolled_detail = await client.get("/courses/introduction-to-agentic-ai")
    assert enrolled_detail.status_code == 200
    assert "Continue course" in enrolled_detail.text
    assert "You are enrolled in this course" in enrolled_detail.text
