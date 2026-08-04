import pytest
from sqlalchemy import select

from app.models import CartItem, Course, CourseEntitlement
from app.services.cart_service import CartError, add_course_to_cart
from app.repositories.cart import get_cart_view


async def paid_course(db_session, *, slug="paid-python", price=25):
    course = Course(title="Paid Python", slug=slug, short_description="Paid.", description="Paid.", category="Python", tags=["python"], price=price, currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_active=True)
    db_session.add(course)
    await db_session.commit()
    return course


@pytest.mark.asyncio
async def test_cart_add_is_idempotent_and_uses_current_price(db_session, regular_user):
    course = await paid_course(db_session)
    first = await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=course.slug)
    second = await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=course.slug)
    view = await get_cart_view(db_session, user_id=regular_user.id)
    assert first.added is True
    assert second.added is False
    assert len(view.items) == 1
    course.price = 31
    await db_session.commit()
    assert view.subtotal == 25
    assert (await get_cart_view(db_session, user_id=regular_user.id)).subtotal == 31


@pytest.mark.asyncio
async def test_free_and_owned_courses_are_rejected(db_session, regular_user, course):
    with pytest.raises(CartError):
        await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=course.slug)
    paid = await paid_course(db_session, slug="owned-python")
    db_session.add(CourseEntitlement(user_id=regular_user.id, course_id=paid.id, source="PURCHASE", granted_at=paid.created_at))
    await db_session.commit()
    with pytest.raises(CartError):
        await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=paid.slug)
