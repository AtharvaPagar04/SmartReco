import pytest
from app.models import Course


@pytest.mark.asyncio
async def test_home_and_catalog(client, course):
    home = await client.get("/")
    assert home.status_code == 200
    assert "Python Foundations" in home.text

    listing = await client.get("/courses?q=python&category=Python")
    assert listing.status_code == 200
    assert "Python Foundations" in listing.text

    detail = await client.get("/courses/python-foundations")
    assert detail.status_code == 200
    assert "Start exploring" in detail.text


@pytest.mark.asyncio
async def test_catalog_pagination_preserves_filters(client, db_session):
    # Add multiple Python courses to trigger pagination
    for i in range(5):
        db_session.add(
            Course(
                title=f"Python Advanced {i}",
                slug=f"python-advanced-{i}",
                short_description="Advanced Python course.",
                description="Deep dive into Python internals and performance.",
                category="Python",
                tags=["python", "advanced"],
                price=50,
                currency="USD",
                difficulty="ADVANCED",
                instructor="Ravi Shah",
                duration_minutes=120,
                is_featured=False,
                is_active=True,
                version=1,
            )
        )
    await db_session.commit()

    # Request page 1 with page size 2 and active filters
    res = await client.get("/courses?q=python&category=Python&difficulty=ADVANCED&price=paid&sort=title&page=1&size=2")
    assert res.status_code == 200
    html = res.text

    # Check that Next page link preserves all filter query parameters
    assert 'q=python' in html
    assert 'category=Python' in html
    assert 'difficulty=ADVANCED' in html
    assert 'price=paid' in html
    assert 'sort=title' in html
    assert 'page=2' in html


@pytest.mark.asyncio
async def test_html_versus_json_exception_responses(client):
    # 1. Non-API 404 request returns HTML error page
    html_404 = await client.get("/courses/no-such-course", headers={"Accept": "text/html"})
    assert html_404.status_code == 404
    assert "text/html" in html_404.headers["content-type"]
    assert "<!DOCTYPE html>" in html_404.text or "<html" in html_404.text
    assert "Nothing here yet" in html_404.text

    # 2. Non-API request with Accept: application/json returns JSON error
    json_404 = await client.get("/courses/no-such-course", headers={"Accept": "application/json"})
    assert json_404.status_code == 404
    assert "application/json" in json_404.headers["content-type"]
    assert json_404.json() == {"error": {"code": "http_error", "message": "The requested page was not found."}}

    # 3. API endpoint 404 request returns JSON error response
    api_404 = await client.get("/api/events/non-existent-route")
    assert api_404.status_code == 404
    assert "application/json" in api_404.headers["content-type"]
    assert api_404.json() == {"error": {"code": "http_error", "message": "The requested page was not found."}}
