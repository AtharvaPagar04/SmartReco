from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import CourseEntitlement, Enrollment
from app.services.course_action_service import action_for_course


@pytest.mark.asyncio
async def test_free_start_state_and_purchase_states(course, regular_user):
    assert action_for_course(course, authenticated=True).state == "FREE_AVAILABLE"
    assert action_for_course(course, authenticated=True, entitled=True).state == "PURCHASED"
    enrollment = Enrollment(user_id=regular_user.id, course_id=course.id, started_at=datetime.utcnow(), last_accessed_at=datetime.utcnow())
    assert action_for_course(course, authenticated=True, enrollment=enrollment).primary_label == "Continue course"
    enrollment.completed_at = datetime.utcnow()
    assert action_for_course(course, authenticated=True, enrollment=enrollment).primary_label == "Review course"
