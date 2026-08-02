import pytest
from uuid import uuid4
from sqlalchemy import select

from app.models import ActivityEvent
from tests.conftest import csrf


@pytest.mark.asyncio
async def test_event_batch_validation_and_partial_acceptance(client, db_session, course):
    page = await client.get("/")
    token = csrf(page.text)

    # Batch with 3 events:
    # 0: valid COURSE_VIEW
    # 1: invalid event_type
    # 2: valid schema, non-existent course_id
    payload = {
        "events": [
            {"event_type": "COURSE_VIEW", "course_id": course.id},
            {"event_type": "INVALID_TYPE", "course_id": course.id},
            {"event_type": "COURSE_VIEW", "course_id": "00000000-0000-0000-0000-000000000000"},
        ]
    }

    response = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["accepted"] == 1
    assert data["rejected"] == 2

    # Check that error positions match original indices 1 and 2
    error_map = {err["index"]: err["code"] for err in data["errors"]}
    assert 1 in error_map
    assert 2 in error_map

    events_in_db = list((await db_session.execute(select(ActivityEvent))).scalars().all())
    assert len(events_in_db) == 1
    assert events_in_db[0].course_id == course.id


@pytest.mark.asyncio
async def test_event_batch_and_metadata_limits(client, db_session, course):
    page = await client.get("/")
    token = csrf(page.text)

    # 1. Batch size exceeding max limit (51 > 50)
    too_many = [{"event_type": "PAGE_VIEW"} for _ in range(51)]
    res_large_batch = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": too_many})
    assert res_large_batch.status_code == 422
    assert "1 to 50" in res_large_batch.json()["error"]["message"]

    # 2. Metadata exceeding 4096 bytes
    large_metadata = {"key": "x" * 5000}
    res_metadata = await client.post(
        "/api/events/batch",
        headers={"X-CSRF-Token": token},
        json={"events": [{"event_type": "PAGE_VIEW", "metadata": large_metadata}]},
    )
    assert res_metadata.status_code == 200
    data_meta = res_metadata.json()
    assert data_meta["accepted"] == 0
    assert data_meta["rejected"] == 1
    assert data_meta["errors"][0]["code"] == "metadata_too_large"

    # 3. Payload size exceeding 256KB
    huge_json_str = '{"events": [' + ','.join(['{"event_type": "PAGE_VIEW"}' for _ in range(15000)]) + ']}'
    res_payload = await client.post(
        "/api/events/batch",
        headers={"X-CSRF-Token": token, "Content-Type": "application/json"},
        content=huge_json_str,
    )
    assert res_payload.status_code == 413
    assert "too large" in res_payload.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_beacon_rejects_cross_origin(client):
    # Cross-origin Origin header
    res_origin = await client.post("/api/events/beacon", headers={"origin": "https://evil.example"}, json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert res_origin.status_code == 403
    assert res_origin.json()["error"]["code"] == "http_error"

    # Cross-origin Referer header
    res_referer = await client.post("/api/events/beacon", headers={"referer": "https://evil.example/malicious"}, json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert res_referer.status_code == 403
    assert res_referer.json()["error"]["code"] == "http_error"

    # Same-origin request
    res_valid = await client.post("/api/events/beacon", headers={"origin": "http://testserver", "host": "testserver"}, json={"events": [{"event_type": "PAGE_VIEW"}]})
    assert res_valid.status_code == 200
    assert res_valid.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_event_idempotency_and_schema_version(client, db_session):
    token = csrf((await client.get("/")).text)
    event_id = str(uuid4())
    payload = {"events": [{"event_id": event_id, "schema_version": 1, "event_type": "PAGE_VIEW", "page_path": "/courses"}]}
    first = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json=payload)
    second = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json=payload)
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1
    assert len((await db_session.execute(select(ActivityEvent))).scalars().all()) == 1

    duplicate_batch = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": [payload["events"][0], payload["events"][0]]})
    assert duplicate_batch.json()["duplicates"] == 2
    unsupported = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": [{"schema_version": 2, "event_type": "PAGE_VIEW"}]})
    assert unsupported.json()["errors"][0]["code"] == "unsupported_schema_version"


@pytest.mark.asyncio
async def test_course_dwell_requires_course_id_on_detail(client, course):
    token = csrf((await client.get("/")).text)
    missing = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": [{"event_type": "DWELL", "page_path": "/courses/python-foundations", "duration_ms": 5000}]})
    assert missing.json()["errors"][0]["code"] == "course_id_required"
    valid = await client.post("/api/events/batch", headers={"X-CSRF-Token": token}, json={"events": [{"event_type": "DWELL", "course_id": course.id, "page_path": "/courses/python-foundations", "duration_ms": 5000}]})
    assert valid.json()["accepted"] == 1
