from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CartItem, Course, CourseEntitlement, Enrollment, ShoppingCart


@dataclass(frozen=True)
class CourseActionState:
    state: str
    primary_label: str
    primary_url: str
    primary_method: str
    secondary_label: str | None = None
    secondary_url: str | None = None
    secondary_method: str | None = None
    is_in_cart: bool = False
    is_entitled: bool = False
    is_enrolled: bool = False


async def user_access_course_ids(db: AsyncSession, user_id: str) -> set[str]:
    enrolled = set((await db.scalars(select(Enrollment.course_id).where(Enrollment.user_id == user_id))).all())
    entitled = set((await db.scalars(select(CourseEntitlement.course_id).where(CourseEntitlement.user_id == user_id, CourseEntitlement.revoked_at.is_(None)))).all())
    return enrolled | entitled


def _login(course: Course, label: str) -> CourseActionState:
    return CourseActionState("ANONYMOUS_FREE" if course.price <= 0 else "ANONYMOUS_PAID", label, f"/login?next=/courses/{course.slug}", "GET")


def action_for_course(course: Course, *, authenticated: bool, in_cart: bool = False, entitled: bool = False, enrollment: Enrollment | None = None) -> CourseActionState:
    if not authenticated:
        return _login(course, "Sign in to start" if course.price <= 0 else "Sign in to buy")
    if enrollment and (enrollment.completed_at or enrollment.status == "COMPLETED"):
        return CourseActionState("COMPLETED", "Review course", f"/courses/{course.slug}", "GET", is_entitled=entitled, is_enrolled=True)
    if enrollment:
        return CourseActionState("IN_PROGRESS", "Continue course", f"/courses/{course.slug}", "GET", is_entitled=entitled, is_enrolled=True)
    if entitled:
        return CourseActionState("PURCHASED", "Start course", f"/courses/{course.slug}/enroll", "POST", is_entitled=True)
    if course.price <= 0:
        return CourseActionState("FREE_AVAILABLE", "Start course", f"/courses/{course.slug}/enroll", "POST")
    if in_cart:
        return CourseActionState("IN_CART", "Buy course", f"/courses/{course.slug}/buy", "POST", "View cart", "/cart", "GET", True)
    return CourseActionState("PAID_AVAILABLE", "Buy course", f"/courses/{course.slug}/buy", "POST", "Add to cart", f"/cart/items/{course.slug}", "POST")


async def load_course_actions(db: AsyncSession, courses: list[Course], user_id: str | None) -> dict[str, CourseActionState]:
    if not user_id:
        return {course.id: action_for_course(course, authenticated=False) for course in courses}
    ids = {course.id for course in courses}
    enrollments = {row.course_id: row for row in (await db.scalars(select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id.in_(ids)))).all()}
    entitlements = set((await db.scalars(select(CourseEntitlement.course_id).where(CourseEntitlement.user_id == user_id, CourseEntitlement.course_id.in_(ids), CourseEntitlement.revoked_at.is_(None)))).all())
    cart_ids = set((await db.scalars(select(CartItem.course_id).join(ShoppingCart, ShoppingCart.id == CartItem.cart_id).where(ShoppingCart.user_id == user_id, CartItem.course_id.in_(ids)))).all())
    return {course.id: action_for_course(course, authenticated=True, in_cart=course.id in cart_ids, entitled=course.id in entitlements, enrollment=enrollments.get(course.id)) for course in courses}
