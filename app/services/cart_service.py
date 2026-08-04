from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CartItem, Course, CourseEntitlement, ShoppingCart
from app.repositories.cart import get_or_create_cart, get_cart_view, remove_cart_item


class CartError(ValueError):
    pass


@dataclass(frozen=True)
class CartResult:
    added: bool
    message: str


async def add_course_to_cart(db: AsyncSession, *, user_id: str, course_slug: str) -> CartResult:
    course = await db.scalar(select(Course).where(Course.slug == course_slug))
    if not course or not course.is_active:
        raise CartError("This course is not available.")
    if course.price <= 0:
        raise CartError("Free courses can be started directly.")
    owned = await db.scalar(select(CourseEntitlement.id).where(CourseEntitlement.user_id == user_id, CourseEntitlement.course_id == course.id, CourseEntitlement.revoked_at.is_(None)))
    if owned:
        raise CartError("You already own this course.")
    cart = await get_or_create_cart(db, user_id=user_id)
    count = await db.scalar(select(func.count()).select_from(CartItem).where(CartItem.cart_id == cart.id))
    existing = await db.scalar(select(CartItem.id).where(CartItem.cart_id == cart.id, CartItem.course_id == course.id))
    if existing:
        return CartResult(False, "Course is already in your cart.")
    if count >= settings.cart_max_items:
        raise CartError("Your cart is full.")
    db.add(CartItem(cart_id=cart.id, course_id=course.id))
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        return CartResult(False, "Course is already in your cart.")
    return CartResult(True, "Course added to your cart.")


async def remove_course_from_cart(db: AsyncSession, *, user_id: str, course_slug: str) -> bool:
    course = await db.scalar(select(Course.id).where(Course.slug == course_slug))
    return bool(course and await remove_cart_item(db, user_id=user_id, course_id=course))


__all__ = ["CartError", "CartResult", "add_course_to_cart", "get_cart_view", "remove_course_from_cart"]
