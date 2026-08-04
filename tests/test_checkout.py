from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Course, CourseEntitlement, Order
from app.services.cart_service import add_course_to_cart
from app.services.checkout_service import complete_demo_payment, create_cart_order, create_single_course_order
from tests.conftest import csrf


async def make_paid(db_session):
    course = Course(title="Paid Course", slug="paid-course", short_description="Paid.", description="Paid.", category="Python", tags=[], price=Decimal("19.99"), currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_active=True)
    db_session.add(course)
    await db_session.commit()
    return course


@pytest.mark.asyncio
async def test_direct_purchase_is_decimal_idempotent_and_does_not_enroll(db_session, regular_user):
    course = await make_paid(db_session)
    order = await create_single_course_order(db_session, user_id=regular_user.id, course_slug=course.slug)
    assert order.total == Decimal("19.99")
    assert order.items[0].unit_price_snapshot == Decimal("19.99")
    paid = await complete_demo_payment(db_session, user_id=regular_user.id, order_id=order.id)
    repeat = await complete_demo_payment(db_session, user_id=regular_user.id, order_id=order.id)
    entitlement = await db_session.scalar(select(CourseEntitlement).where(CourseEntitlement.user_id == regular_user.id, CourseEntitlement.course_id == course.id))
    assert paid.status == repeat.status == "PAID"
    assert entitlement is not None
    assert await db_session.scalar(select(Order).where(Order.id == order.id)) is not None


@pytest.mark.asyncio
async def test_cart_purchase_removes_only_purchased_items(db_session, regular_user):
    first = await make_paid(db_session)
    second = Course(title="Second Paid", slug="second-paid", short_description="Paid.", description="Paid.", category="Python", tags=[], price=Decimal("9.99"), currency="USD", difficulty="BEGINNER", instructor="Asha Menon", duration_minutes=60, is_active=True)
    db_session.add(second)
    await db_session.commit()
    await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=first.slug)
    await add_course_to_cart(db_session, user_id=regular_user.id, course_slug=second.slug)
    order = await create_cart_order(db_session, user_id=regular_user.id)
    await complete_demo_payment(db_session, user_id=regular_user.id, order_id=order.id)
    remaining = await db_session.scalar(select(Course.id).where(Course.id == second.id))
    assert remaining == second.id


@pytest.mark.asyncio
async def test_browser_flow_renders_context_actions(client, regular_user, db_session):
    course = await make_paid(db_session)
    login_page = await client.get("/login")
    login = await client.post("/login", data={"email": regular_user.email, "password": "StudentPass123!", "csrf_token": csrf(login_page.text)})
    assert login.status_code == 303
    detail = await client.get(f"/courses/{course.slug}")
    assert "Buy course" in detail.text and "Add to cart" in detail.text
    token = csrf(detail.text)
    added = await client.post(f"/cart/items/{course.slug}", data={"csrf_token": token})
    assert added.status_code == 303
    assert "View cart" in (await client.get(f"/courses/{course.slug}")).text
    token = csrf((await client.get(f"/courses/{course.slug}")).text)
    bought = await client.post(f"/courses/{course.slug}/buy", data={"csrf_token": token})
    assert bought.status_code == 303
    checkout = await client.get(bought.headers["location"])
    completed = await client.post(f"{bought.headers['location']}/complete", data={"csrf_token": csrf(checkout.text)})
    assert completed.status_code == 303
    assert "Start course" in (await client.get(f"/courses/{course.slug}")).text
