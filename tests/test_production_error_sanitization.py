import pytest
from fastapi import Request
from app.main import app
from app.exception_handlers import unhandled_exception_handler


@pytest.mark.asyncio
async def test_unhandled_exception_handler_sanitizes_html_response():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/learning-paths/test",
        "headers": [(b"accept", b"text/html")],
        "session": {},
        "app": app,
    }
    request = Request(scope)
    exc = RuntimeError("SQLAlchemy asyncpg exception SELECT * FROM secret_table WHERE password='123'")

    response = await unhandled_exception_handler(request, exc)

    assert response.status_code == 500
    text = response.body.decode("utf-8").lower()
    assert "traceback" not in text
    assert "select * from" not in text
    assert "asyncpg" not in text
    assert "sqlalchemy" not in text
    assert "site-packages" not in text
    assert "password='123'" not in text
    assert "we hit a snag" in text or "something went wrong" in text


@pytest.mark.asyncio
async def test_unhandled_exception_handler_sanitizes_json_response():
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/learning-paths",
        "headers": [(b"accept", b"application/json")],
        "session": {},
        "app": app,
    }
    request = Request(scope)
    exc = RuntimeError("SQLAlchemy asyncpg exception SELECT * FROM secret_table WHERE password='123'")

    response = await unhandled_exception_handler(request, exc)

    assert response.status_code == 500
    text = response.body.decode("utf-8").lower()
    assert "traceback" not in text
    assert "select * from" not in text
    assert "asyncpg" not in text
    assert "sqlalchemy" not in text
    assert "site-packages" not in text
    assert "password='123'" not in text
    assert "something went wrong" in text
