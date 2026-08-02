import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Course, User, VectorOutbox
from app.security import normalize_email
from scripts.create_admin import main as create_admin_main
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_admin_creation_script(db_session):
    # Test creating admin account
    await create_admin_main()
    admin_email = normalize_email(settings.admin_email)
    user = await db_session.scalar(select(User).where(User.email == admin_email))
    assert user is not None
    assert user.role == "ADMIN"
    assert user.is_active is True

    # Idempotency: run again to verify update behavior
    await create_admin_main()
    user_after = await db_session.scalar(select(User).where(User.email == admin_email))
    assert user_after.id == user.id
    assert user_after.role == "ADMIN"


@pytest.mark.asyncio
async def test_admin_login_redirect(client, admin_user):
    client.cookies.clear()
    login_page = await client.get("/login")
    token = csrf(login_page.text)
    res = await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": token})
    assert res.status_code == 303
    assert res.headers["location"] == "/admin"


@pytest.mark.asyncio
async def test_admin_navigation_link_visibility(client, admin_user, regular_user):
    # 1. Logged out
    client.cookies.clear()
    home_out = await client.get("/")
    assert href_admin(home_out.text) is False

    # 2. Regular user
    client.cookies.clear()
    login_page = await client.get("/login")
    token = csrf(login_page.text)
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": token})
    home_user = await client.get("/")
    assert href_admin(home_user.text) is False

    # 3. Admin user
    client.cookies.clear()
    login_page = await client.get("/login")
    token = csrf(login_page.text)
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": token})
    home_admin = await client.get("/")
    assert href_admin(home_admin.text) is True


def href_admin(html: str) -> bool:
    return '<a href="/admin">Admin</a>' in html or 'href="/admin"' in html


@pytest.mark.asyncio
async def test_admin_authorization_on_every_protected_route(client, db_session, admin_user, regular_user, course):
    outbox = VectorOutbox(course_id=course.id, operation="UPSERT", course_version=course.version, status="FAILED")
    db_session.add(outbox)
    await db_session.commit()

    protected_routes = [
        ("GET", "/admin", None),
        ("GET", "/admin/courses", None),
        ("GET", "/admin/courses/new", None),
        ("POST", "/admin/courses", {"title": "Test Course"}),
        ("GET", f"/admin/courses/{course.id}/edit", None),
        ("POST", f"/admin/courses/{course.id}/edit", {"title": "Test Course"}),
        ("POST", f"/admin/courses/{course.id}/delete", {}),
        ("POST", f"/admin/vector-sync/{outbox.id}/retry", {}),
        ("GET", "/admin/vector-sync", None),
        ("GET", "/admin/events", None),
    ]

    # Unauthenticated check
    client.cookies.clear()
    for method, path, data in protected_routes:
        if method == "GET":
            res = await client.get(path)
        else:
            res = await client.post(path, data=data or {})
        assert res.status_code == 403, f"Unauthenticated access to {method} {path} should return 403"

    # Regular user check
    client.cookies.clear()
    login_page = await client.get("/login")
    token = csrf(login_page.text)
    await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": token})
    for method, path, data in protected_routes:
        if method == "GET":
            res = await client.get(path)
        else:
            res = await client.post(path, data=data or {})
        assert res.status_code == 403, f"Regular user access to {method} {path} should return 403"


@pytest.mark.asyncio
async def test_admin_dashboard_loads(client, admin_user):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    res = await client.get("/admin")
    assert res.status_code == 200
    assert "Admin dashboard" in res.text
    assert "Total users" in res.text
    assert "Active courses" in res.text


@pytest.mark.asyncio
async def test_admin_course_list_loads(client, admin_user, course):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    res = await client.get("/admin/courses")
    assert res.status_code == 200
    assert "Course management" in res.text
    assert course.title in res.text


@pytest.mark.asyncio
async def test_admin_course_create(client, db_session, admin_user):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    form = await client.get("/admin/courses/new")
    token = csrf(form.text)
    response = await client.post(
        "/admin/courses",
        data={
            "csrf_token": token,
            "title": "Secure APIs",
            "short_description": "Build safer API foundations.",
            "description": "A practical course on validation, sessions, and safe API boundaries.",
            "category": "Cybersecurity",
            "tags": "security, api",
            "price": "10",
            "currency": "USD",
            "difficulty": "INTERMEDIATE",
            "instructor": "Admin",
            "duration_minutes": "90",
            "is_active": "on",
        },
    )
    assert response.status_code == 303

    # Verify SQL course creation
    course = await db_session.scalar(select(Course).where(Course.title == "Secure APIs"))
    assert course is not None
    assert course.vector_status == "PENDING"

    # Verify UPSERT outbox job creation
    outbox_entry = await db_session.scalar(select(VectorOutbox).where(VectorOutbox.course_id == course.id))
    assert outbox_entry is not None
    assert outbox_entry.operation == "UPSERT"
    assert outbox_entry.course_version == 1


@pytest.mark.asyncio
async def test_course_update_with_and_without_vector_relevant_changes(client, db_session, admin_user, course):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    edit_page = await client.get(f"/admin/courses/{course.id}/edit")
    token = csrf(edit_page.text)

    outbox_count_before = len((await db_session.execute(select(VectorOutbox))).scalars().all())
    initial_version = course.version

    # Update ONLY non-vector-relevant fields (thumbnail_url, is_featured)
    res_non_vector = await client.post(
        f"/admin/courses/{course.id}/edit",
        data={
            "csrf_token": token,
            "title": course.title,
            "slug": course.slug,
            "short_description": course.short_description,
            "description": course.description,
            "category": course.category,
            "tags": ", ".join(course.tags),
            "price": str(course.price),
            "currency": course.currency,
            "difficulty": course.difficulty,
            "instructor": course.instructor,
            "duration_minutes": str(course.duration_minutes),
            "thumbnail_url": "http://example.com/thumb.jpg",
            "is_featured": "on",
            "is_active": "on",
        },
    )
    assert res_non_vector.status_code == 303
    await db_session.refresh(course)
    outbox_count_after_non_vector = len((await db_session.execute(select(VectorOutbox))).scalars().all())

    # Version and outbox count should NOT change
    assert course.version == initial_version
    assert outbox_count_after_non_vector == outbox_count_before

    # Get fresh edit token
    edit_page_2 = await client.get(f"/admin/courses/{course.id}/edit")
    token_2 = csrf(edit_page_2.text)

    # Now update vector-relevant field (title)
    res_vector = await client.post(
        f"/admin/courses/{course.id}/edit",
        data={
            "csrf_token": token_2,
            "title": "Python Foundations Updated",
            "slug": course.slug,
            "short_description": course.short_description,
            "description": course.description,
            "category": course.category,
            "tags": ", ".join(course.tags),
            "price": str(course.price),
            "currency": course.currency,
            "difficulty": course.difficulty,
            "instructor": course.instructor,
            "duration_minutes": str(course.duration_minutes),
            "thumbnail_url": course.thumbnail_url,
            "is_featured": "on",
            "is_active": "on",
        },
    )
    assert res_vector.status_code == 303
    await db_session.refresh(course)
    outbox_count_after_vector = len((await db_session.execute(select(VectorOutbox))).scalars().all())

    # Version should increment and outbox should receive a new row
    assert course.version == initial_version + 1
    assert course.vector_status == "PENDING"
    assert outbox_count_after_vector == outbox_count_before + 1


@pytest.mark.asyncio
async def test_admin_course_delete(client, db_session, admin_user, course):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    courses_page = await client.get("/admin/courses")
    token = csrf(courses_page.text)

    # Archive/Delete course
    res = await client.post(f"/admin/courses/{course.id}/delete", data={"csrf_token": token})
    assert res.status_code == 303

    await db_session.refresh(course)
    assert course.is_active is False
    assert course.vector_status == "DELETING"

    # Verify DELETE outbox job created
    outbox = await db_session.scalar(select(VectorOutbox).where(VectorOutbox.course_id == course.id, VectorOutbox.operation == "DELETE"))
    assert outbox is not None

    # Verify course disappears from public catalog listing and detail route
    public_catalog = await client.get("/courses")
    assert course.title not in public_catalog.text

    public_detail = await client.get(f"/courses/{course.slug}")
    assert public_detail.status_code == 404


@pytest.mark.asyncio
async def test_admin_invalid_csrf_rejected(client, admin_user, course):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    # POST with invalid CSRF token
    res = await client.post("/admin/courses", data={"title": "No CSRF Course", "csrf_token": "bad_token"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_restore_and_pagination(client, db_session, admin_user):
    for index in range(4):
        db_session.add(Course(title=f"Page Course {index}", slug=f"page-course-{index}", short_description="A useful course description.", description="A sufficiently detailed course description for testing pagination.", category="Python", tags=["python"], price=0, currency="USD", difficulty="BEGINNER", instructor="Teacher", duration_minutes=60, is_active=True, version=1, vector_status="PENDING"))
    await db_session.commit()
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})
    listing = await client.get("/admin/courses?page=2&page_size=2&active=true")
    assert listing.status_code == 200
    assert "Page 2 of" in listing.text
    assert "page_size=2" in listing.text
    item = await db_session.scalar(select(Course).where(Course.slug == "page-course-0"))
    form = await client.get("/admin/courses")
    archive = await client.post(f"/admin/courses/{item.id}/delete", data={"csrf_token": csrf(form.text), "next": "/admin/courses?page=2&page_size=2"})
    assert archive.status_code == 303
    await db_session.refresh(item)
    assert not item.is_active
    restore_page = await client.get("/admin/courses?active=false")
    restored = await client.post(f"/admin/courses/{item.id}/restore", data={"csrf_token": csrf(restore_page.text), "next": "/admin/courses?active=false"})
    assert restored.status_code == 303
    await db_session.refresh(item)
    assert item.is_active and item.vector_status == "PENDING"


@pytest.mark.asyncio
async def test_admin_validation_errors_displayed_with_values(client, admin_user, course):
    client.cookies.clear()
    login = await client.get("/login")
    await client.post("/login", data={"email": admin_user.email, "password": "AdminPass123!", "csrf_token": csrf(login.text)})

    form = await client.get("/admin/courses/new")
    token = csrf(form.text)

    # Attempt to create with an existing slug
    res = await client.post(
        "/admin/courses",
        data={
            "csrf_token": token,
            "title": "Duplicate Slug Course",
            "slug": course.slug,  # Existing slug!
            "short_description": "Custom short description for course.",
            "description": "Custom long description with more than 20 characters.",
            "category": "Testing",
            "tags": "tag1, tag2",
            "price": "25.00",
            "currency": "USD",
            "difficulty": "BEGINNER",
            "instructor": "Teacher",
            "duration_minutes": "45",
            "is_active": "on",
        },
    )
    assert res.status_code == 200
    assert "Slug already exists." in res.text
    # Check that entered field values were preserved
    assert "Duplicate Slug Course" in res.text
    assert "Custom short description for course." in res.text
    assert "25.00" in res.text
