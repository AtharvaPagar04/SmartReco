import pytest

from tests.conftest import csrf


@pytest.mark.asyncio
async def test_registration_csrf_and_login(client, course):
    register = await client.get("/register")
    token = csrf(register.text)

    # Missing CSRF token rejected
    denied = await client.post("/register", data={"full_name": "Ada Lovelace", "email": "ADA@Example.com", "password": "correct horse", "password_confirm": "correct horse"})
    assert denied.status_code == 403

    # Invalid CSRF token rejected
    bad_token = await client.post("/register", data={"full_name": "Ada Lovelace", "email": "ADA@Example.com", "password": "correct horse", "password_confirm": "correct horse", "csrf_token": "invalid_token"})
    assert bad_token.status_code == 403

    # Valid CSRF token succeeds
    created = await client.post("/register", data={"full_name": "Ada Lovelace", "email": "ADA@Example.com", "password": "correct horse", "password_confirm": "correct horse", "csrf_token": token})
    assert created.status_code == 303

    login = await client.get("/login")
    logged_in = await client.post("/login", data={"email": "ada@example.com", "password": "correct horse", "csrf_token": csrf(login.text), "next": "/account"})
    assert logged_in.status_code == 303
    assert logged_in.headers["location"] == "/account"


@pytest.mark.asyncio
async def test_invalid_login_does_not_authenticate(client):
    response = await client.get("/login")
    result = await client.post("/login", data={"email": "nobody@example.com", "password": "wrong", "csrf_token": csrf(response.text)})
    assert result.status_code == 200
    assert "incorrect" in result.text


@pytest.mark.asyncio
async def test_json_csrf_rejection_and_success(client):
    page = await client.get("/")
    token = csrf(page.text)

    # JSON request missing X-CSRF-Token header
    no_token = await client.post("/api/events/batch", json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert no_token.status_code == 403
    assert no_token.json()["error"]["code"] == "http_error"

    # JSON request with invalid X-CSRF-Token header
    wrong_token = await client.post("/api/events/batch", headers={"X-CSRF-Token": "bad-token"}, json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert wrong_token.status_code == 403
    assert wrong_token.json()["error"]["code"] == "http_error"

    # JSON request with valid X-CSRF-Token header
    valid_res = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert valid_res.status_code == 200
    assert valid_res.json()["accepted"] == 1
