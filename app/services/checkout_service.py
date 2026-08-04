from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ActivityEvent, CartItem, Course, CourseEntitlement, Order, OrderItem, ShoppingCart
from app.services.payments.demo import DemoPaymentGateway


class CheckoutError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _owned_ids(db: AsyncSession, user_id: str) -> set[str]:
    return set((await db.scalars(select(CourseEntitlement.course_id).where(CourseEntitlement.user_id == user_id, CourseEntitlement.revoked_at.is_(None)))).all())


async def _create_order(db: AsyncSession, *, user_id: str, courses: list[Course]) -> Order:
    if not courses:
        raise CheckoutError("There are no purchasable courses in this order.")
    currencies = {course.currency.upper() for course in courses}
    if len(currencies) != 1:
        raise CheckoutError("All courses in an order must use the same currency.")
    total = sum((Decimal(str(course.price)) for course in courses), Decimal("0.00"))
    order = Order(user_id=user_id, status="PENDING", currency=currencies.pop(), subtotal=total, total=total, payment_mode="demo")
    order.items = [OrderItem(course_id=course.id, course_title_snapshot=course.title, unit_price_snapshot=Decimal(str(course.price)), currency=course.currency.upper()) for course in courses]
    db.add(order)
    await db.flush()
    await db.commit()
    return order


async def create_single_course_order(db: AsyncSession, *, user_id: str, course_slug: str) -> Order:
    course = await db.scalar(select(Course).where(Course.slug == course_slug, Course.is_active.is_(True)))
    if not course:
        raise CheckoutError("This course is not available.")
    if course.price <= 0:
        raise CheckoutError("Free courses can be started directly.")
    if course.id in await _owned_ids(db, user_id):
        raise CheckoutError("You already own this course.")
    pending = await db.scalar(select(Order).join(OrderItem).where(Order.user_id == user_id, Order.status == "PENDING", OrderItem.course_id == course.id).order_by(Order.created_at.desc()).limit(1))
    return pending or await _create_order(db, user_id=user_id, courses=[course])


async def create_cart_order(db: AsyncSession, *, user_id: str) -> Order:
    cart = await db.scalar(select(ShoppingCart).where(ShoppingCart.user_id == user_id))
    if not cart:
        raise CheckoutError("Your cart is empty.")
    items = list((await db.scalars(select(CartItem).options(selectinload(CartItem.course)).where(CartItem.cart_id == cart.id))).all())
    owned = await _owned_ids(db, user_id)
    courses = [item.course for item in items if item.course and item.course.is_active and item.course.price > 0 and item.course.id not in owned]
    return await _create_order(db, user_id=user_id, courses=courses)


async def complete_demo_payment(db: AsyncSession, *, user_id: str, order_id: str) -> Order:
    order = await db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.user_id == user_id))
    if not order:
        raise CheckoutError("Order not found.")
    if order.status == "PAID":
        return order
    if order.status != "PENDING":
        raise CheckoutError("This order cannot be completed.")
    result = await DemoPaymentGateway().create_payment(order_id=order.id, amount=Decimal(str(order.total)), currency=order.currency)
    if not result.succeeded:
        order.status = "FAILED"
        order.failure_code = result.failure_code or "payment_failed"
        await db.commit()
        return order
    now = _now()
    order.status = "PAID"
    order.payment_reference = result.reference
    order.completed_at = now
    for item in order.items:
        entitlement = await db.scalar(select(CourseEntitlement).where(CourseEntitlement.user_id == user_id, CourseEntitlement.course_id == item.course_id))
        if entitlement:
            entitlement.revoked_at = None
            entitlement.source = "PURCHASE"
            entitlement.order_item_id = item.id
            entitlement.granted_at = now
        else:
            db.add(CourseEntitlement(user_id=user_id, course_id=item.course_id, source="PURCHASE", order_item_id=item.id, granted_at=now))
        await db.execute(delete(CartItem).where(CartItem.course_id == item.course_id, CartItem.cart_id.in_(select(ShoppingCart.id).where(ShoppingCart.user_id == user_id))))
    await db.commit()
    try:
        db.add(ActivityEvent(user_id=user_id, session_id="commerce", event_type="COURSE_PURCHASED", metadata_json={"source": "commerce", "order_id": order.id, "currency": order.currency}, occurred_at=now, received_at=now))
        await db.commit()
    except Exception:
        await db.rollback()
    return order
